"""Pool many pivot JSONs and aggregate them by study condition.

Streamlit-free and testable. Each output JSON carries the identifiers the
Data page wrote into it (``data["study"]`` = patient / run / group /
condition; see ``page_data._study_form``). This module loads a batch of
those pivots, runs the same downstream pipeline the rest of the app uses,
and groups the per-run results by condition so a whole study can be read
at once -- roughly the analyses of the validation report, per condition,
with the individual runs still reachable underneath.

The per-condition charts reuse the app's own kinematics figures
(``charts.kinematics``): those read ``cycles["cycles"]`` and
``cycles["summary"]``, so :func:`pool_cycles` merges the runs' cycles and
recomputes the per-side summary in exactly that shape.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from numbers import Real
from pathlib import Path
from typing import Iterable

import numpy as np

from .agreement import curve_metrics, summarize_agreement
from .clinical import clinical_scores, select_stratum
from .pipeline import PipelineConfig, PipelineRunner, SubjectConfig
from .step_length import STEP_LENGTH_M_RANGE, step_length_m_from_markers

#: The sagittal joints every figure and summary is built around.
SAGITTAL_JOINTS = ("hip", "knee", "ankle")

#: Study key used to group; falls back to this when a JSON has no
#: condition recorded (e.g. an older export, or a C3D import not yet
#: tagged). Kept explicit so the UI can say what "unspecified" means.
UNSPECIFIED = "unspecified"


def _finite_number(value: object) -> bool:
    """Whether a value can safely contribute to a clinical aggregate."""
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


@dataclass
class RunResult:
    """One recording after the downstream pipeline has run on it."""

    name: str
    study: dict
    ok: bool
    kind: str = "video"           # "video" | "vicon" (marker-based reference)
    duration_s: float | None = None
    cycles: dict | None = None
    stats: dict | None = None
    error: str = ""
    #: Short rationale for the auto-detected pipeline recipe, shown in the UI
    #: so the reader knows what config produced these cycles.
    config_note: str = ""
    #: Metric step length (m) read straight off 3-D markers, when the pivot
    #: carries them -- a real length that needs no pixel calibration.
    marker_step_length_m: float | None = None

    def _s(self, key: str, default: str = "") -> str:
        value = self.study.get(key)
        return str(value) if value not in (None, "") else default

    @property
    def condition(self) -> str:
        return self._s("condition", UNSPECIFIED)

    @property
    def patient(self) -> str:
        return self._s("patient_id", "?")

    @property
    def run(self) -> str:
        return self._s("run", self.name)

    @property
    def group(self) -> str:
        return self._s("group")

    @property
    def is_reference(self) -> bool:
        """True for a marker-based (Vicon) trial that can ground truth."""
        return self.kind == "vicon"

    @property
    def pair_key(self) -> tuple[str, str]:
        """Identity a video run and its marker reference share."""
        return (self.patient, self.run)

    @property
    def n_cycles(self) -> int:
        return len((self.cycles or {}).get("cycles", []))


def _detect_kind(data: dict) -> str:
    """A pivot carrying 3-D marker trajectories is a marker-based reference.

    ``load_c3d`` keeps the raw 3-D markers under ``c3d_markers_3d``; a video
    extraction never has them. The study block may also state it explicitly.
    """
    if data.get("c3d_markers_3d"):
        return "vicon"
    source = str((data.get("study") or {}).get("source") or "").lower()
    if source in ("c3d", "vicon"):
        return "vicon"
    if str((data.get("meta") or {}).get("source") or "").lower() == "c3d":
        return "vicon"
    return "video"


def _duration_s(data: dict) -> float | None:
    """Recording duration in seconds, from the frame count and fps."""
    meta = data.get("meta") or {}
    frames = data.get("frames") or []
    fps = meta.get("fps")
    if _finite_number(meta.get("duration_s")) and meta["duration_s"] >= 0:
        return float(meta["duration_s"])
    if _finite_number(fps) and fps > 0 and frames:
        return len(frames) / float(fps)
    return None


def _apply_study_subject(config: PipelineConfig, study: dict) -> PipelineConfig:
    """A subject height in the study block calibrates step length to metres."""
    height = study.get("height_m")
    try:
        height = float(height) if height not in (None, "") else None
    except (TypeError, ValueError):
        height = None
    if height is None or not math.isfinite(height) or height <= 0:
        return config
    return replace(config, subject=SubjectConfig(height_m=height))


def load_run(path, config: PipelineConfig | None = None) -> RunResult:
    """Load one pivot JSON and run the pipeline, capturing any failure.

    Never raises: a bad file becomes an ``ok=False`` result carrying the
    reason, so one unreadable recording does not abort a whole batch.
    """
    from myogait import load_json

    # Keep ``config`` possibly None: that is the signal to auto-detect the
    # recipe below. ``base`` handles the default for the subject-height merge.
    name = Path(path).name
    try:
        data = load_json(str(path))
    except Exception as exc:  # noqa: BLE001 - reported per-run, not raised
        return RunResult(name=name, study={}, ok=False, error=f"read: {exc}")

    # kind and duration come from the pivot itself, so they are known even
    # if the downstream pipeline later fails.
    study = dict(data.get("study") or {})
    kind = _detect_kind(data)
    duration_s = _duration_s(data)
    # A subject height in the study block makes step length metric (unit "m").
    base = _apply_study_subject(config or PipelineConfig(), study)

    note = ""
    try:
        if config is None:
            # No explicit config: pick the recipe from the recording itself
            # (marker vs video, standing vs mid-stride start, there-and-back)
            # and fall back to the overground recipe if it finds no cycle.
            from .autoconfig import run_auto

            result, _used, reasons = run_auto(data, str(path), base)
            note = "; ".join(reasons)
        else:
            result = PipelineRunner(data, source_key=str(path)).run(base)
    except Exception as exc:  # noqa: BLE001
        return RunResult(
            name=name, study=study, ok=False, kind=kind, duration_s=duration_s,
            error=f"pipeline: {exc}",
        )

    if not result.ok:
        failed = result.failed_stage
        reason = f"{failed.name}: {failed.error}" if failed else "pipeline failed"
        return RunResult(
            name=name, study=study, ok=False, kind=kind, duration_s=duration_s,
            error=reason, config_note=note,
        )

    marker_step_length_m = step_length_m_from_markers(data.get("c3d_markers_3d") or {})

    return RunResult(
        name=name, study=study, ok=True, kind=kind, duration_s=duration_s,
        cycles=result.cycles, stats=result.stats, config_note=note,
        marker_step_length_m=marker_step_length_m,
    )


def load_runs(paths: Iterable, config: PipelineConfig | None = None) -> list[RunResult]:
    """Load and run a batch of pivots, preserving order."""
    return [load_run(p, config) for p in paths]


def group_by_condition(runs: Iterable[RunResult]) -> dict[str, list[RunResult]]:
    """Group the successful runs by their study condition (sorted by name)."""
    groups: dict[str, list[RunResult]] = {}
    for run in runs:
        if run.ok:
            groups.setdefault(run.condition, []).append(run)
    return dict(sorted(groups.items()))


def pool_cycles(runs: Iterable[RunResult]) -> dict:
    """Merge several runs' cycles into one figure-ready ``cycles`` dict.

    Concatenates every cycle and recomputes the per-side ``summary`` (mean
    and SD curve per joint, plus ``n_cycles``) over the pooled set, so the
    condition-level figures show the aggregate rather than any single run.
    """
    merged: list[dict] = []
    for index, run in enumerate(runs):
        for cycle in (run.cycles or {}).get("cycles", []):
            copy = dict(cycle)
            # Namespace the id so cycles from different runs stay distinct.
            copy["cycle_id"] = f"{index}:{cycle.get('cycle_id')}"
            merged.append(copy)

    summary: dict[str, dict] = {}
    for side in ("left", "right"):
        side_cycles = [c for c in merged if c.get("side") == side]
        entry: dict = {"n_cycles": len(side_cycles)}
        for joint in SAGITTAL_JOINTS:
            curves = [
                c["angles_normalized"][joint]
                for c in side_cycles
                if (c.get("angles_normalized") or {}).get(joint) is not None
                and len(c["angles_normalized"][joint]) == 101
            ]
            if curves:
                arr = np.asarray(curves, dtype=float)
                entry[f"{joint}_mean"] = arr.mean(axis=0).tolist()
                entry[f"{joint}_std"] = arr.std(axis=0).tolist()
        summary[side] = entry

    return {"cycles": merged, "summary": summary}


def _spatiotemporal(run: RunResult) -> dict:
    return (run.stats or {}).get("spatiotemporal") or {}


def _mean_metric_step_length(runs: list[RunResult]) -> float | None:
    """Mean step length in metres, marker-derived first, else calibrated video.

    A marker (C3D) run carries a real metric step length read straight off the
    3-D markers -- no pixel calibration, so it is trusted first. Video runs
    contribute their calibrated ``step_length`` only when its unit is metres
    and the value is physiologically plausible.
    """
    lo, hi = STEP_LENGTH_M_RANGE

    # 1) Markers: a real length, preferred whenever any run has one.
    marker_values = [
        run.marker_step_length_m for run in runs
        if _finite_number(run.marker_step_length_m)
        and lo <= run.marker_step_length_m <= hi
    ]
    if marker_values:
        return float(np.mean(marker_values))

    # 2) Otherwise fall back to the calibrated video estimate.
    values: list[float] = []
    for run in runs:
        step = (run.stats or {}).get("step_length") or {}
        if step.get("unit") != "m":
            continue
        for side in ("step_length_left", "step_length_right"):
            value = step.get(side)
            if _finite_number(value) and lo <= value <= hi:
                values.append(float(value))
    return float(np.mean(values)) if values else None


def _first_age(runs: list[RunResult]) -> float | None:
    for run in runs:
        age = run.study.get("age")
        try:
            if age not in (None, ""):
                value = float(age)
                if math.isfinite(value) and value >= 0:
                    return value
        except (TypeError, ValueError):
            continue
    return None


def condition_summary(runs: list[RunResult]) -> dict:
    """Aggregate figures for one condition: counts, spatiotemporal, ROM.

    Spatiotemporal metrics are averaged over runs (any numeric key present
    in at least one run's ``stats["spatiotemporal"]``). ROM per joint is
    the range of the pooled mean curve, so it matches the figures.
    """
    runs = list(runs)
    pooled = pool_cycles(runs)

    # Mean over runs of every numeric spatiotemporal metric.
    keys: list[str] = []
    for run in runs:
        for key in _spatiotemporal(run):
            if key not in keys:
                keys.append(key)
    spatiotemporal: dict[str, float] = {}
    for key in keys:
        values = [
            float(_spatiotemporal(run)[key])
            for run in runs
            if _finite_number(_spatiotemporal(run).get(key))
        ]
        if values:
            spatiotemporal[key] = float(np.mean(values))

    rom: dict[str, float] = {}
    for joint in SAGITTAL_JOINTS:
        spans = []
        for side in ("left", "right"):
            mean = (pooled["summary"].get(side) or {}).get(f"{joint}_mean")
            if mean:
                spans.append(float(np.nanmax(mean) - np.nanmin(mean)))
        if spans:
            rom[joint] = float(np.mean(spans))

    # Metric step length only when calibrated (a subject height was provided);
    # analyze_gait puts it top-level with unit "m", not in spatiotemporal.
    step_length_m = _mean_metric_step_length(runs)

    stratum = select_stratum(_first_age(runs))
    scores = clinical_scores(pooled, stratum=stratum)

    return {
        "n_runs": len(runs),
        "n_patients": len({run.patient for run in runs}),
        "n_cycles": len(pooled["cycles"]),
        "n_video": sum(1 for r in runs if not r.is_reference),
        "n_reference": sum(1 for r in runs if r.is_reference),
        "duration_s": _mean_or_none([r.duration_s for r in runs]),
        "step_length_m": step_length_m,
        "spatiotemporal": spatiotemporal,
        "rom_deg": rom,
        "scores": scores,
        "stratum": stratum,
        "cycles": pooled,
    }


def _mean_or_none(values):
    nums = [float(v) for v in values if _finite_number(v)]
    return float(np.mean(nums)) if nums else None


def condition_agreement(runs: list[RunResult]) -> dict | None:
    """Accuracy of the markerless runs against the marker reference, if any.

    Only meaningful when a condition holds both markerless (video) and
    marker-based (vicon) recordings: the reference is what turns variability
    into accuracy. Pools each kind's mean cycle curve per joint/side and
    compares them with :func:`agreement.curve_metrics`. Returns ``None`` when
    one of the two kinds is absent (video alone -> variability only).
    """
    video_runs = [r for r in runs if r.ok and not r.is_reference]
    vicon_runs = [r for r in runs if r.ok and r.is_reference]
    if not video_runs or not vicon_runs:
        return None

    per_joint_side = _paired_curve_metrics(video_runs, vicon_runs)
    return {
        "n_video": len(video_runs),
        "n_reference": len(vicon_runs),
        "per_joint_side": per_joint_side,
        "by_joint": summarize_agreement(per_joint_side),
    }


def _paired_curve_metrics(video_runs: list, vicon_runs: list) -> list[dict]:
    """Per joint/side agreement between two pooled sets of runs."""
    video_pooled = pool_cycles(video_runs)
    vicon_pooled = pool_cycles(vicon_runs)

    per_joint_side: list[dict] = []
    for side in ("left", "right"):
        v_side = video_pooled["summary"].get(side) or {}
        c_side = vicon_pooled["summary"].get(side) or {}
        for joint in SAGITTAL_JOINTS:
            video_curve = v_side.get(f"{joint}_mean")
            reference_curve = c_side.get(f"{joint}_mean")
            if not video_curve or not reference_curve:
                continue
            metrics = curve_metrics(video_curve, reference_curve)
            if metrics:
                metrics.update(joint=joint, side=side)
                per_joint_side.append(metrics)
    return per_joint_side


def overall_agreement(runs: list[RunResult]) -> dict | None:
    """Accuracy vs the marker reference, paired automatically by patient.

    Unlike :func:`condition_agreement` (which needs the markerless and marker
    recordings to share a *condition*), this pairs them by ``patient_id`` alone:
    for every patient that has both a markerless and a marker recording, the
    two mean cycle curves are compared, and the per-joint battery is averaged
    over all such patients. So dropping a batch of videos plus that subject's
    Vicon C3D into the Cohort surfaces accuracy on its own, with no condition
    tagging. Returns ``None`` when no patient has both kinds.
    """
    by_patient: dict[str, list[RunResult]] = {}
    for run in runs:
        if run.ok:
            by_patient.setdefault(run.patient, []).append(run)

    per_joint_side: list[dict] = []
    n_patients = n_video = n_reference = 0
    for patient_runs in by_patient.values():
        videos = [r for r in patient_runs if not r.is_reference]
        vicons = [r for r in patient_runs if r.is_reference]
        if not videos or not vicons:
            continue
        n_patients += 1
        n_video += len(videos)
        n_reference += len(vicons)
        per_joint_side.extend(_paired_curve_metrics(videos, vicons))

    if not n_patients:
        return None
    return {
        "n_patients": n_patients,
        "n_video": n_video,
        "n_reference": n_reference,
        "per_joint_side": per_joint_side,
        "by_joint": summarize_agreement(per_joint_side),
    }
