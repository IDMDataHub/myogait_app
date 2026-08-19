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
    correct_ankle_sliding: bool = True
    apply_aspect_ratio: bool = True
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


@dataclass(frozen=True)
class SubjectConfig:
    """Subject metadata. Height unlocks calibrated step length and speed."""

    age: int | None = None
    sex: str | None = None
    height_m: float | None = None
    weight_kg: float | None = None
    pathology: str | None = None

    @property
    def is_empty(self) -> bool:
        return all(
            getattr(self, f) in (None, "")
            for f in ("age", "sex", "height_m", "weight_kg", "pathology")
        )


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


def _correction(name: str):
    """Resolve a correction from ``myogait.corrections``.

    Imported by module path rather than from the package root: these
    functions were promoted to the top-level namespace at different
    versions (``apply_linear_detrend`` only from 0.6.1), and the module
    path is the form the myogait documentation itself uses.
    """
    import importlib

    module = importlib.import_module("myogait.corrections")
    func = getattr(module, name, None)
    if func is None:
        raise RuntimeError(
            f"myogait.corrections.{name} does not exist in the installed "
            "myogait. Upgrade to 0.6.1 or later, or turn this correction off."
        )
    return func


def _apply_angles(data: dict, cfg: AnglesConfig) -> dict:
    from myogait import compute_angles

    data = compute_angles(
        data,
        method=cfg.method,
        correction_factor=cfg.correction_factor,
        calibrate=cfg.calibrate,
        calibration_frames=cfg.calibration_frames,
        correct_ankle_sliding=cfg.correct_ankle_sliding,
        apply_aspect_ratio=cfg.apply_aspect_ratio,
    )

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

    return segment_cycles(
        data,
        n_points=cfg.n_points,
        min_duration=cfg.min_duration,
        max_duration=cfg.max_duration,
    )


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
        key_stats = key_final + ("analysis", config.subject.height_m)

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

        return analyze_gait(
            copy.deepcopy(data), cycles, height_m=config.subject.height_m
        )

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
