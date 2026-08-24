"""The pipeline engine.

myogait is a chain: normalize -> angles -> events -> cycles -> analysis,
where each step mutates and returns the pivot dict. Driving that chain
from a slider is what makes the app a workbench rather than a viewer, and
it only feels like one if changing the *last* parameter does not re-run
the *first* stage.

So the configuration is split per stage into frozen dataclasses, and each
stage is memoised on the identity of everything upstream of it. Moving
the cycle duration bound reuses the cached angles and events; moving the
Butterworth cutoff invalidates everything below it, and nothing above.

The engine also captures per-stage timings and errors instead of letting
an exception escape, so the interface can say which stage broke and why.
"""

from __future__ import annotations

import copy
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Callable

#: Stage names, in execution order.
#:
#: ``bias`` sits after ``cycles`` and not with the other angle
#: corrections because the LASSO bias models are indexed by gait-cycle
#: phase: they need the segmentation to exist before they can be applied.
STAGES = ("normalize", "angles", "events", "cycles", "bias", "analysis")


# ── Configuration ────────────────────────────────────────────────────


@dataclass(frozen=True)
class NormalizeConfig:
    """Signal conditioning, applied to landmarks before anything else."""

    #: Applied in order. Names come from myogait.normalize.NORMALIZE_STEPS.
    filters: tuple[str, ...] = ("butterworth",)
    butterworth_cutoff: float = 4.0
    butterworth_order: int = 2
    center: bool = False
    align: bool = False
    correct_limbs: bool = False
    gap_max_frames: int = 10
    #: Drop landmarks below this detection confidence. None disables.
    confidence_threshold: float | None = None
    #: Interpolate points beyond this many SD from the local trend.
    outlier_z: float | None = None
    #: Score per-frame biomechanical coherence and attach it to the data.
    coherence: bool = True


@dataclass(frozen=True)
class AnglesConfig:
    """Joint kinematics, plus the corrections that need only the angles."""

    method: str = "sagittal_vertical_axis"
    correction_factor: float = 0.8
    calibrate: bool = True
    calibration_frames: int = 30
    #: When the first calibration_frames of a joint show no meaningful
    #: motion (angle std below calibration_min_std_deg), fall back to the
    #: median of all valid frames of that joint instead of that static
    #: window -- otherwise a patient who begins standing in a pathological
    #: or asymmetric pose silently shifts the whole cycle by that offset.
    #: Ankle is myogait's default calibrated joint, so this is exactly what
    #: separates a genuine measurement ceiling from a calibration artefact
    #: when validating ankle angles: rule this out before concluding the
    #: former.
    calibration_dynamic_fallback: bool = True
    calibration_min_std_deg: float = 1.0
    correct_ankle_sliding: bool = True
    apply_aspect_ratio: bool = True
    #: Maximum plausible magnitude (degrees) for a neutral-calibration
    #: offset (myogait >= 0.8.0). Above this, compute_angles skips
    #: calibration for that joint with a warning instead of shifting the
    #: whole cycle by an implausible amount -- the guard against a clip
    #: whose "neutral" window actually caught mid-gait motion.
    calibration_max_offset_deg: float = 25.0
    #: Enforces a flexion-positive sagittal convention independent of
    #: walking direction (myogait >= 0.8.0). Without it, two recordings of
    #: the same subject walking in opposite directions -- or a video
    #: compared against its C3D reference -- can disagree in sign. On by
    #: default: this is a correctness fix, not a stylistic choice.
    canonicalize_signs: bool = True
    #: Frontal-plane angles, only meaningful when depth data is present.
    frontal: bool = False
    #: M1 projection correction for hip and knee. Zero-parameter pure
    #: geometry, derived from segment lengths in this very recording, so
    #: it carries no assumption about the population and is safe on any
    #: gait. The hip and knee bias models below expect it to have run.
    perspective: bool = False
    #: Removes the slow angular drift a fixed camera introduces over a
    #: long walk. Applied after the perspective correction.
    detrend: bool = False


@dataclass(frozen=True)
class BiasConfig:
    """The frozen LASSO bias corrections. Off by default, deliberately.

    myogait ships these as models fitted on *healthy young adults* against
    a Vicon reference, and its own documentation is blunt about the
    consequence: they re-inject a healthy curve at exactly the phases
    where neuromuscular disease shows itself -- swing knee flexion peak in
    DMD and CMT, ankle push-off in drop foot, end-stance hip extension in
    hip weakness.

    They belong in a benchmarking workflow against a healthy reference,
    not in the clinical reading of a patient. The interface states this at
    the point of use; the default here is the safe one.
    """

    ankle: bool = False
    hip: bool = False
    knee: bool = False
    model: str = "v1"

    @property
    def any_enabled(self) -> bool:
        return self.ankle or self.hip or self.knee

    @property
    def needs_perspective(self) -> bool:
        """Hip and knee models were fitted on M1-corrected residuals.

        Applying them to un-corrected angles double-counts part of the
        projection correction, so the interface requires the perspective
        step whenever either is on. The ankle model was fitted on the raw
        signal and carries no such constraint.
        """
        return self.hip or self.knee


@dataclass(frozen=True)
class EventsConfig:
    """Heel-strike and toe-off detection."""

    method: str = "zeni"
    min_cycle_duration: float = 0.4
    cutoff_freq: float = 6.0
    adaptive: bool = False
    femur_length_mm: float = 400.0
    trim_standstill: bool = True
    #: When non-empty, consensus voting replaces the single method above.
    consensus_methods: tuple[str, ...] = ()
    consensus_tolerance: int = 3

    @property
    def is_consensus(self) -> bool:
        return len(self.consensus_methods) > 1


@dataclass(frozen=True)
class CyclesConfig:
    """Cycle segmentation and time normalisation."""

    n_points: int = 101
    min_duration: float = 0.4
    max_duration: float = 2.5
    #: Reject a cycle whose mean landmark confidence falls below this
    #: (myogait >= 0.8.1). None disables the gate. Rejections are counted
    #: in cycles["summary"]["n_rejected_quality"].
    min_confidence: float | None = None
    #: Reject a cycle whose mean frame-coherence score falls below this
    #: (myogait >= 0.8.1, needs NormalizeConfig.coherence enabled upstream
    #: for a coherence score to exist at all). None disables the gate.
    min_coherence: float | None = None


#: myogait's own femur-to-height ratio (Drillis, Contini & Bluestein,
#: Artif Limbs 1964), used internally by step_length()/walking_speed() to
#: derive a femur length from height_m. calibration_height_m below solves
#: this ratio in reverse, so passing it back into height_m makes myogait
#: calibrate from the *measured* femur instead of the population estimate.
FEMUR_TO_HEIGHT_RATIO = 0.245


@dataclass(frozen=True)
class SubjectConfig:
    """Subject metadata. Height unlocks calibrated step length and speed.

    The five ``*_length_mm`` fields are directly measured segment lengths,
    not part of myogait's own subject schema. femur_length_mm doubles as
    the app's preferred source for pixel/metre calibration -- see
    ``calibration_height_m`` -- and all five feed the app's own
    cross-check panel (``myogait_app.calibration``) against myogait's
    figures.
    """

    age: int | None = None
    sex: str | None = None
    height_m: float | None = None
    weight_kg: float | None = None
    pathology: str | None = None
    femur_length_mm: float | None = None
    tibia_length_mm: float | None = None
    upper_arm_length_mm: float | None = None
    forearm_length_mm: float | None = None
    trunk_length_mm: float | None = None
    #: Heel to longest toe. Feeds analyze_gait's native foot_mm parameter
    #: (myogait >= 0.7.0) -- averaged with femur_length_mm when both are
    #: set, for the tightest calibration myogait documents. Not part of
    #: the calibration.py cross-check panel (that compares against
    #: myogait.segment_lengths(), which has no foot entry).
    foot_length_mm: float | None = None

    @property
    def is_empty(self) -> bool:
        return all(
            getattr(self, f) in (None, "")
            for f in (
                "age", "sex", "height_m", "weight_kg", "pathology",
                "femur_length_mm", "tibia_length_mm", "upper_arm_length_mm",
                "forearm_length_mm", "trunk_length_mm", "foot_length_mm",
            )
        )

    @property
    def calibration_height_m(self) -> float | None:
        """The height_m fallback for myogait < 0.7.0 (no native femur_mm/foot_mm).

        Older myogait's step_length()/walking_speed() derive their
        pixel/metre scale from ``height_m x 0.245`` alone -- a population
        femur-to-height ratio, not a per-subject measurement. When the
        femur was measured directly, this returns the height that makes
        that same internal formula reproduce the *real* femur instead of
        the population estimate. From myogait 0.7.0, ``PipelineRunner.
        _analyze`` calls ``analyze_gait`` with ``femur_mm``/``foot_mm``
        directly instead and this property is not used for that path --
        see ``Runtime.native_anthropometric_calibration``.
        """
        if self.femur_length_mm:
            return (self.femur_length_mm / 1000.0) / FEMUR_TO_HEIGHT_RATIO
        return self.height_m

    @property
    def measured_segments_mm(self) -> dict[str, float]:
        """App-facing segment key -> measured length (mm), only those set."""
        mapping = {
            "femur": self.femur_length_mm,
            "tibia": self.tibia_length_mm,
            "upper_arm": self.upper_arm_length_mm,
            "forearm": self.forearm_length_mm,
            "trunk": self.trunk_length_mm,
        }
        return {k: v for k, v in mapping.items() if v}


@dataclass(frozen=True)
class PipelineConfig:
    """Everything the pipeline needs, downstream of extraction."""

    normalize: NormalizeConfig = field(default_factory=NormalizeConfig)
    angles: AnglesConfig = field(default_factory=AnglesConfig)
    events: EventsConfig = field(default_factory=EventsConfig)
    cycles: CyclesConfig = field(default_factory=CyclesConfig)
    bias: BiasConfig = field(default_factory=BiasConfig)
    subject: SubjectConfig = field(default_factory=SubjectConfig)

    def with_stage(self, stage: str, value: Any) -> "PipelineConfig":
        return replace(self, **{stage: value})

    def to_dict(self) -> dict:
        return asdict(self)


# ── Results ──────────────────────────────────────────────────────────


@dataclass
class StageOutcome:
    """What happened in one stage."""

    name: str
    ok: bool
    seconds: float = 0.0
    error: str = ""
    cached: bool = False
    note: str = ""


@dataclass
class PipelineResult:
    """The end state of a run, successful or not."""

    data: dict | None = None
    cycles: dict | None = None
    stats: dict | None = None
    outcomes: list[StageOutcome] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(outcome.ok for outcome in self.outcomes)

    @property
    def failed_stage(self) -> StageOutcome | None:
        for outcome in self.outcomes:
            if not outcome.ok:
                return outcome
        return None

    @property
    def total_seconds(self) -> float:
        return sum(outcome.seconds for outcome in self.outcomes)

    def outcome(self, name: str) -> StageOutcome | None:
        for entry in self.outcomes:
            if entry.name == name:
                return entry
        return None

    @property
    def n_cycles(self) -> int:
        if not self.cycles:
            return 0
        return len(self.cycles.get("cycles", []))

    def n_cycles_side(self, side: str) -> int:
        if not self.cycles:
            return 0
        return sum(1 for c in self.cycles.get("cycles", []) if c.get("side") == side)


# ── Stage implementations ────────────────────────────────────────────


def _apply_normalize(data: dict, cfg: NormalizeConfig) -> dict:
    from myogait import (
        confidence_filter,
        detect_outliers,
        frame_coherence_score,
        normalize,
    )

    # Quality gates run before filtering: smoothing a bad landmark makes
    # it look plausible, which is worse than dropping it.
    if cfg.confidence_threshold is not None:
        data = confidence_filter(data, threshold=cfg.confidence_threshold)
    if cfg.outlier_z is not None:
        data = detect_outliers(data, z_thresh=cfg.outlier_z)

    data = normalize(
        data,
        filters=list(cfg.filters),
        butterworth_cutoff=cfg.butterworth_cutoff,
        butterworth_order=cfg.butterworth_order,
        center=cfg.center,
        align=cfg.align,
        correct_limbs=cfg.correct_limbs,
        gap_max_frames=cfg.gap_max_frames,
    )

    if cfg.coherence:
        # Non-fatal: coherence is diagnostic, not required downstream.
        try:
            data = frame_coherence_score(data)
        except Exception:
            pass
    return data


def _correction(name: str, module: str = "myogait.corrections"):
    """Resolve *name* from *module* by path rather than the package root.

    These functions were promoted to the top-level namespace at different
    versions (``apply_linear_detrend`` only from 0.6.1, ``canonicalize_
    angle_signs`` only from 0.8.0), and the module path is the form the
    myogait documentation itself uses.
    """
    import importlib

    resolved = importlib.import_module(module)
    func = getattr(resolved, name, None)
    if func is None:
        raise RuntimeError(
            f"{module}.{name} does not exist in the installed myogait. "
            "Upgrade, or turn this correction off."
        )
    return func


def _apply_angles(data: dict, cfg: AnglesConfig) -> dict:
    from myogait import compute_angles

    angles_kwargs = dict(
        method=cfg.method,
        correction_factor=cfg.correction_factor,
        calibrate=cfg.calibrate,
        calibration_frames=cfg.calibration_frames,
        calibration_dynamic_fallback=cfg.calibration_dynamic_fallback,
        calibration_min_std_deg=cfg.calibration_min_std_deg,
        correct_ankle_sliding=cfg.correct_ankle_sliding,
        apply_aspect_ratio=cfg.apply_aspect_ratio,
    )
    # calibration_max_offset_deg only exists from myogait 0.8.0 -- passing
    # it to an older compute_angles would raise TypeError, so it is added
    # conditionally rather than gating the whole call on runtime.has().
    if _accepts(compute_angles, "calibration_max_offset_deg"):
        angles_kwargs["calibration_max_offset_deg"] = cfg.calibration_max_offset_deg
    data = compute_angles(data, **angles_kwargs)

    # Sign convention first: every correction below (perspective, drift,
    # bias) assumes a flexion-positive signal, and canonicalize_angle_signs
    # is what makes that true regardless of walking direction.
    if cfg.canonicalize_signs:
        data = _correction("canonicalize_angle_signs", "myogait.angles")(data)

    if cfg.frontal:
        from myogait.angles import compute_frontal_angles

        data = compute_frontal_angles(data)

    # Order is prescribed by the package: the projection correction first,
    # then the drift removal on top of the corrected trace.
    if cfg.perspective:
        data = _correction("apply_perspective_correction")(data)
    if cfg.detrend:
        data = _correction("apply_linear_detrend")(data)
    return data


def _accepts(func, param_name: str) -> bool:
    """True when *func* declares a parameter named *param_name*.

    Several myogait functions gained new keyword arguments in later
    versions (``compute_angles(calibration_max_offset_deg=)`` in 0.8.0,
    ``segment_cycles(min_confidence=, min_coherence=)`` in 0.8.1). Passing
    one to an older installation raises ``TypeError``, so each is added to
    the call conditionally instead of gating the whole call on a version
    check the way ``OPTIONAL_FEATURES`` gates a missing *function*.
    """
    import inspect

    return param_name in inspect.signature(func).parameters


def _apply_bias(
    data: dict, cycles: dict, cfg: BiasConfig, cycles_cfg: CyclesConfig
) -> tuple[dict, dict]:
    """Apply the phase-indexed bias corrections and re-segment.

    Returns the corrected data together with a *fresh* segmentation. The
    corrections rewrite ``data["angles"]["frames"]`` in place, which
    leaves the cycles that were just computed describing the previous
    curves; handing those back would silently show corrected kinematics
    alongside uncorrected cycle statistics.
    """
    if not cfg.any_enabled:
        return data, cycles

    for enabled, func_name in (
        (cfg.ankle, "apply_ankle_bias_correction"),
        (cfg.hip, "apply_hip_bias_correction"),
        (cfg.knee, "apply_knee_bias_correction"),
    ):
        if enabled:
            data = _correction(func_name)(data, cycles, model=cfg.model)

    return data, _apply_cycles(data, cycles_cfg)


def _apply_events(data: dict, cfg: EventsConfig) -> dict:
    if cfg.is_consensus:
        from myogait import event_consensus

        return event_consensus(
            data,
            methods=list(cfg.consensus_methods),
            tolerance=cfg.consensus_tolerance,
            min_cycle_duration=cfg.min_cycle_duration,
            cutoff_freq=cfg.cutoff_freq,
            femur_length_mm=cfg.femur_length_mm,
        )

    from myogait import detect_events

    return detect_events(
        data,
        method=cfg.method,
        min_cycle_duration=cfg.min_cycle_duration,
        cutoff_freq=cfg.cutoff_freq,
        adaptive=cfg.adaptive,
        femur_length_mm=cfg.femur_length_mm,
        trim_standstill=cfg.trim_standstill,
    )


def _apply_cycles(data: dict, cfg: CyclesConfig) -> dict:
    from myogait import segment_cycles

    cycles_kwargs = dict(
        n_points=cfg.n_points,
        min_duration=cfg.min_duration,
        max_duration=cfg.max_duration,
    )
    if cfg.min_confidence is not None and _accepts(segment_cycles, "min_confidence"):
        cycles_kwargs["min_confidence"] = cfg.min_confidence

    source = data
    if cfg.min_coherence is not None and _accepts(segment_cycles, "min_coherence"):
        cycles_kwargs["min_coherence"] = cfg.min_coherence
        # segment_cycles(min_coherence=) does float(frame["coherence"]),
        # but frame_coherence_score() (NormalizeConfig.coherence, run
        # upstream in _apply_normalize) attaches the breakdown dict
        # {"score", "segment_stability", "velocity", "angular_continuity"}
        # there instead -- a shape mismatch between two myogait functions,
        # not this app. Flatten to the scalar score on a copy so the gate
        # can run instead of raising TypeError.
        source = copy.deepcopy(data)
        for frame in source.get("frames", []):
            coherence = frame.get("coherence")
            if isinstance(coherence, dict):
                frame["coherence"] = coherence.get("score")

    return segment_cycles(source, **cycles_kwargs)


def _apply_subject(data: dict, cfg: SubjectConfig) -> dict:
    if cfg.is_empty:
        return data
    from myogait import set_subject

    return set_subject(
        data,
        age=cfg.age,
        sex=cfg.sex,
        height_m=cfg.height_m,
        weight_kg=cfg.weight_kg,
        pathology=cfg.pathology,
    )


# ── Engine ───────────────────────────────────────────────────────────


class PipelineRunner:
    """Runs the chain for one source dataset, caching every stage.

    One runner owns one extraction. Its cache is keyed by the tuple of
    stage configs upstream of each stage, so two configurations that
    share a prefix share the work for that prefix.
    """

    def __init__(self, source: dict, source_key: str, max_entries: int = 24) -> None:
        #: Never handed out directly -- every stage works on a copy so a
        #: myogait in-place mutation cannot corrupt the cached upstream.
        self._source = source
        self.source_key = source_key
        self._cache: OrderedDict[tuple, Any] = OrderedDict()
        self._max_entries = max_entries
        self._hits = 0
        self._misses = 0

    # cache plumbing ------------------------------------------------

    def _memo(self, key: tuple, produce: Callable[[], Any]) -> tuple[Any, bool]:
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key], True
        self._misses += 1
        value = produce()
        self._cache[key] = value
        self._cache.move_to_end(key)
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)
        return value, False

    @property
    def cache_stats(self) -> dict:
        return {
            "hits": self._hits,
            "misses": self._misses,
            "entries": len(self._cache),
        }

    def clear_cache(self) -> None:
        self._cache.clear()

    # execution -----------------------------------------------------

    def run(self, config: PipelineConfig, upto: str = "analysis") -> PipelineResult:
        """Execute the chain up to and including *upto*.

        Failures stop the chain: a stage whose input never materialised
        is not attempted, and the result reports which one broke.
        """
        if upto not in STAGES:
            raise ValueError(f"Unknown stage {upto!r}; expected one of {STAGES}")
        limit = STAGES.index(upto)

        result = PipelineResult()
        base = (self.source_key, config.subject)

        # normalize ---------------------------------------------------
        key_norm = base + ("normalize", config.normalize)
        data, outcome = self._stage(
            "normalize",
            key_norm,
            lambda: _apply_normalize(
                _apply_subject(copy.deepcopy(self._source), config.subject),
                config.normalize,
            ),
        )
        result.outcomes.append(outcome)
        if not outcome.ok:
            return result
        result.data = data
        if limit == 0:
            return result

        # angles ------------------------------------------------------
        key_angles = key_norm + ("angles", config.angles)
        data, outcome = self._stage(
            "angles",
            key_angles,
            lambda: _apply_angles(copy.deepcopy(self._cache[key_norm]), config.angles),
        )
        result.outcomes.append(outcome)
        if not outcome.ok:
            return result
        result.data = data
        if limit == 1:
            return result

        # events ------------------------------------------------------
        key_events = key_angles + ("events", config.events)
        data, outcome = self._stage(
            "events",
            key_events,
            lambda: _apply_events(
                copy.deepcopy(self._cache[key_angles]), config.events
            ),
        )
        result.outcomes.append(outcome)
        if not outcome.ok:
            return result
        result.data = data
        if limit == 2:
            return result

        # cycles ------------------------------------------------------
        key_cycles = key_events + ("cycles", config.cycles)
        cycles, outcome = self._stage(
            "cycles",
            key_cycles,
            lambda: _apply_cycles(
                copy.deepcopy(self._cache[key_events]), config.cycles
            ),
        )
        result.outcomes.append(outcome)
        if not outcome.ok:
            return result
        result.cycles = cycles
        if cycles is not None and not cycles.get("cycles"):
            outcome.note = (
                "No cycle survived segmentation. Widen the duration bounds, "
                "or check the detected events."
            )
        if limit == 3:
            return result

        # bias --------------------------------------------------------
        # Skipped entirely when nothing is enabled, so the common case
        # costs neither a cache entry nor a re-segmentation.
        key_final = key_cycles
        if config.bias.any_enabled:
            key_bias = key_cycles + ("bias", config.bias)
            pair, outcome = self._stage(
                "bias",
                key_bias,
                lambda: _apply_bias(
                    copy.deepcopy(self._cache[key_events]),
                    self._cache[key_cycles],
                    config.bias,
                    config.cycles,
                ),
            )
            result.outcomes.append(outcome)
            if not outcome.ok:
                return result
            data, cycles = pair
            result.data = data
            result.cycles = cycles
            key_final = key_bias
        if limit == 4:
            return result

        # analysis ----------------------------------------------------
        # config.subject as a whole is already part of every key above
        # (it seeds `base`), so this is a documentation key, not what
        # makes a subject change invalidate the cache: it names exactly
        # the three fields analyze_gait's calibration actually reads,
        # whichever of the two calibration paths below is taken.
        subj = config.subject
        key_stats = key_final + (
            "analysis",
            (subj.height_m, subj.femur_length_mm, subj.foot_length_mm),
        )

        def _run_analysis() -> dict:
            cached = self._cache[key_final]
            # The bias stage caches a (data, cycles) pair; every other
            # upstream stage caches the data dict alone.
            if isinstance(cached, tuple):
                source_data, source_cycles = cached
            else:
                source_data, source_cycles = self._cache[key_events], cached
            return self._analyze(source_data, source_cycles, config)

        stats, outcome = self._stage("analysis", key_stats, _run_analysis)
        result.outcomes.append(outcome)
        result.stats = stats if outcome.ok else None
        return result

    @staticmethod
    def _analyze(data: dict, cycles: dict, config: PipelineConfig) -> dict:
        from myogait import analyze_gait

        subj = config.subject
        kwargs: dict[str, float] = {}
        if _accepts(analyze_gait, "femur_mm"):
            # Native anthropometric calibration (myogait >= 0.7.0): pass
            # the measured segments directly. myogait's own priority order
            # (femur+foot > femur alone > foot alone > height_m fallback)
            # decides which one actually drives the scale, so all three
            # can be passed together.
            if subj.height_m:
                kwargs["height_m"] = subj.height_m
            if subj.femur_length_mm:
                kwargs["femur_mm"] = subj.femur_length_mm
            if subj.foot_length_mm:
                kwargs["foot_mm"] = subj.foot_length_mm
        else:
            # Older myogait: invert the population femur-to-height ratio
            # so height_m x 0.245 reproduces the measured femur instead.
            kwargs["height_m"] = subj.calibration_height_m

        return analyze_gait(copy.deepcopy(data), cycles, **kwargs)

    def _stage(
        self, name: str, key: tuple, produce: Callable[[], Any]
    ) -> tuple[Any, StageOutcome]:
        started = time.perf_counter()
        try:
            value, cached = self._memo(key, produce)
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            return None, StageOutcome(
                name=name,
                ok=False,
                seconds=time.perf_counter() - started,
                error=f"{type(exc).__name__}: {exc}",
            )
        return value, StageOutcome(
            name=name,
            ok=True,
            seconds=time.perf_counter() - started,
            cached=cached,
        )
