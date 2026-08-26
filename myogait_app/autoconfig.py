"""Pick the pipeline recipe from the recording itself.

The default pipeline config fits a clean, single-direction, standing-start
clip. Real data isn't always that: a marker (C3D) trial and an overground
walkway that starts mid-stride and walks there-and-back need calibration
off, the standstill kept, and physiological cycle bounds -- the validated
recipe. Rather than make the user know this, introspect the pivot and choose.

Streamlit-free and testable. ``detect_config`` returns a ``PipelineConfig``
plus a short human rationale; ``run_auto`` runs it and, if segmentation still
finds no cycle, falls back to the overground recipe once before giving up.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np

from .pipeline import (
    PipelineConfig,
    PipelineRunner,
)


def _mid_hip_x(frames: list) -> np.ndarray:
    """Antero-posterior progression proxy: the finite mid-hip x values.

    Auto-configuration is advisory, so an incomplete landmark must not turn a
    usable recording into a failed Cohort load. Invalid hips are simply absent
    from this proxy; the pipeline still receives the original pivot unchanged.
    """
    xs: list[float] = []
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        landmarks = frame.get("landmarks")
        if not isinstance(landmarks, dict):
            continue
        values: list[float] = []
        for key in ("LEFT_HIP", "RIGHT_HIP"):
            hip = landmarks.get(key)
            if not isinstance(hip, dict):
                continue
            try:
                value = float(hip.get("x"))
            except (TypeError, ValueError):
                continue
            if np.isfinite(value):
                values.append(value)
        if values:
            xs.append(float(np.mean(values)))
    return np.asarray(xs, dtype=float)


def _has_static_start(frames: list, n: int = 20, thresh: float = 0.01) -> bool:
    """True when the first frames barely move -- a standing neutral pose.

    A standing start gives calibration a real neutral to key off; a
    mid-stride start does not, and first-frame calibration then shifts the
    whole cycle. Measured on the mid-hip x spread (normalised units).
    """
    xs = _mid_hip_x(frames[: min(n, len(frames))])
    return xs.size >= 3 and float(xs.std()) < thresh


def _has_direction_reversal(frames: list, thresh: float = 0.15) -> bool:
    """True for a there-and-back walkway: the AP progression reverses.

    The mid-hip x goes one way then comes back by more than ``thresh`` of the
    frame width, so cycles from the two directions carry opposite sign and
    need direction-consistent handling (calibration off is the safe recipe).
    """
    xs = _mid_hip_x(frames)
    if xs.size < 10:
        return False
    start = float(xs[0])
    end = float(xs[-1])
    high = float(np.max(xs))
    low = float(np.min(xs))
    # A trial may begin in either camera direction. Detect an excursion to
    # either extreme followed by a meaningful return, not only x increasing
    # then decreasing.
    returned_from_high = high - start > thresh and high - end > thresh
    returned_from_low = start - low > thresh and end - low > thresh
    return returned_from_high or returned_from_low


#: The validated overground/marker recipe: no first-frame calibration, keep
#: the standstill, physiological cycle bounds. 3-D ankle reference is a no-op
#: unless the pivot actually carries markers.
def _overground(base: PipelineConfig) -> PipelineConfig:
    return replace(
        base,
        angles=replace(base.angles, calibrate=False, c3d_reference_ankle=True),
        events=replace(base.events, trim_standstill=False, min_cycle_duration=0.6),
        cycles=replace(base.cycles, min_duration=0.8, max_duration=1.8),
    )


def detect_config(data: dict, base: PipelineConfig | None = None) -> tuple[PipelineConfig, list[str]]:
    """Choose a pipeline config for one pivot, with a short rationale.

    ``base`` lets a caller keep its own normalize/subject settings; only the
    angle/event/cycle recipe is adapted.
    """
    base = base or PipelineConfig()
    frames = data.get("frames") or []
    reasons: list[str] = []

    is_c3d = bool(data.get("c3d_markers_3d")) or \
        str((data.get("meta") or {}).get("source") or "").lower() == "c3d"
    reversal = _has_direction_reversal(frames)
    static_start = _has_static_start(frames)

    if is_c3d:
        reasons.append("marker (C3D) source: 3-D ankle reference on")
    if reversal:
        reasons.append("there-and-back walkway: direction-dependent, calibration off")
    if not static_start and not reversal:
        reasons.append("no standing neutral at the start: calibration off")

    if is_c3d or reversal or not static_start:
        reasons.append("overground recipe: standstill kept, cycle bounds 0.8-1.8 s")
        return _overground(base), reasons

    reasons.append("clean standing-start clip: default recipe")
    return base, reasons


def run_auto(data: dict, source_key: str, base: PipelineConfig | None = None):
    """Run the pipeline with an auto-detected config, falling back once.

    Returns ``(result, config, reasons)``. If the detected config segments no
    cycle, retries with the overground recipe before returning -- so a
    misjudged clip degrades to "try the robust recipe", not to an empty page.
    """
    base = base or PipelineConfig()
    config, reasons = detect_config(data, base)
    result = PipelineRunner(data, source_key=source_key).run(config)

    n_cycles = len((result.cycles or {}).get("cycles", [])) if result.ok else 0
    overground = _overground(base)
    if result.ok and n_cycles == 0 and config != overground:
        alt = PipelineRunner(data, source_key=source_key + ":auto2").run(overground)
        if alt.ok and (alt.cycles or {}).get("cycles"):
            reasons.append("no cycle with the first recipe -> fell back to overground")
            return alt, overground, reasons
    return result, config, reasons
