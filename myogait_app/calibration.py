"""Multi-segment calibration cross-check, on top of the femur-driven default.

myogait's own ``step_length`` and ``walking_speed`` calibrate from
``height_m`` alone, deriving a femur length as a fixed 24.5% of height
(Drillis, Contini & Bluestein 1964 -- an anthropometric population
average). When the femur is measured directly, ``SubjectConfig.
calibration_height_m`` already makes myogait itself calibrate from that
real measurement instead -- see ``myogait_app.pipeline`` -- so the
official step length, stride length and walking speed the app shows are
femur-calibrated whenever a femur is entered. That path needs nothing
from this module.

What this module adds is a cross-check: it calls
``myogait.segment_lengths()`` for the pixel-domain geometry, derives an
independent scale from *every other* measured segment (tibia, arms,
trunk) too, and flags when they disagree -- a data-quality signal the
femur-only number alone cannot give. It recomputes step length, stride
length and walking speed with the same event-based geometry
``myogait.analysis.step_length``/``walking_speed`` use, but driven by the
combined multi-segment scale, so the two can be compared directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: App-facing segment key -> the (left, right) keys myogait.segment_lengths
#: reports, from its DEFAULT_SEGMENTS.
SEGMENT_PAIRS: dict[str, tuple[str, str]] = {
    "femur": ("femur_L", "femur_R"),
    "tibia": ("tibia_L", "tibia_R"),
    "upper_arm": ("upper_arm_L", "upper_arm_R"),
    "forearm": ("forearm_L", "forearm_R"),
    "trunk": ("trunk_L", "trunk_R"),
}

#: Segment disagreement (spread / combined scale) above which the combined
#: estimate is flagged rather than silently trusted.
DISAGREEMENT_THRESHOLD = 0.10


@dataclass
class SegmentScale:
    """One measured segment's contribution to the pixel/mm calibration."""

    segment: str
    measured_mm: float
    pixel_mean: float  # mean of L/R, normalised units
    pixel_cv: float  # %, worst of L/R -- myogait's own stability signal
    scale_m_per_unit: float  # metres per normalised x/y unit
    unstable: bool  # True when myogait's own segment_lengths flagged CV > 15%


@dataclass
class CalibrationResult:
    """Every measured segment's scale estimate, plus a combined one."""

    segments: list[SegmentScale] = field(default_factory=list)
    combined_scale: float | None = None  # metres per normalised unit
    disagreement_pct: float | None = None  # spread across segments, %
    flagged: bool = False


def compute_scales(data: dict, measured_mm: dict[str, float]) -> CalibrationResult:
    """Derive a pixel/mm scale from each measured segment, and combine them.

    Parameters
    ----------
    data : dict
        Pivot dict with ``frames`` populated.
    measured_mm : dict
        ``{"femur": 410.0, "tibia": 380.0, ...}`` -- keys from
        :data:`SEGMENT_PAIRS`; segments without a real measurement should
        simply be absent (see ``SubjectConfig.measured_segments_mm``).
    """
    from myogait import segment_lengths

    if not measured_mm:
        return CalibrationResult()

    lengths = segment_lengths(data)
    quality_flags = set(lengths.get("quality_flags") or [])

    segments: list[SegmentScale] = []
    for name, measured in measured_mm.items():
        pair = SEGMENT_PAIRS.get(name)
        if pair is None or not measured:
            continue
        left_key, right_key = pair
        means = [
            lengths[key]["mean"]
            for key in (left_key, right_key)
            if key in lengths and lengths[key]["mean"] > 0
        ]
        if not means:
            continue
        pixel_mean = float(np.mean(means))
        cvs = [lengths[key]["cv"] for key in (left_key, right_key) if key in lengths]
        pixel_cv = max(cvs) if cvs else 0.0
        segments.append(
            SegmentScale(
                segment=name,
                measured_mm=float(measured),
                pixel_mean=pixel_mean,
                pixel_cv=pixel_cv,
                scale_m_per_unit=(measured / 1000.0) / pixel_mean,
                unstable=(left_key in quality_flags) or (right_key in quality_flags),
            )
        )

    if not segments:
        return CalibrationResult()

    scales = np.array([s.scale_m_per_unit for s in segments])
    # Weighted by inverse CV: a segment whose pixel length barely varies
    # across frames is a more trustworthy scale reference than a noisy one.
    weights = np.array([1.0 / max(s.pixel_cv, 1.0) for s in segments])
    combined = float(np.average(scales, weights=weights))
    spread = float((scales.max() - scales.min()) / combined) if combined else 0.0

    return CalibrationResult(
        segments=segments,
        combined_scale=combined,
        disagreement_pct=spread * 100,
        flagged=spread > DISAGREEMENT_THRESHOLD,
    )


@dataclass
class CalibratedSpatiotemporal:
    """Step/stride length and walking speed from an app-derived scale."""

    step_length_left_m: float | None = None
    step_length_right_m: float | None = None
    stride_length_left_m: float | None = None
    stride_length_right_m: float | None = None
    speed_mean_m_s: float | None = None


def calibrated_metrics(
    data: dict,
    cycles: dict,
    scale_m_per_unit: float | None,
    isotropic: bool = False,
) -> CalibratedSpatiotemporal:
    """Recompute step length, stride length and speed with an explicit scale.

    Mirrors the geometry of ``myogait.analysis.step_length`` and
    ``walking_speed`` exactly (same-ankle displacement between two known
    frames -- the leading ankle at the previous opposite-side heel strike
    vs. its own heel strike for step length; a cycle's own side, start and
    end frame for stride length and speed), differing only in where the
    scale comes from: a measured segment length here, ``height_m x
    0.245`` there. Without that, a discrepancy between the two panels
    could look like a real geometry difference when it is really just a
    different calibration source.

    ``isotropic`` tracks myogait's own geometry across versions. Landmarks
    are normalised per axis (x / width, y / height); the calibration scale
    is derived mostly from the (vertical) reference segments but a step is
    a (horizontal) antero-posterior distance, so on a non-square frame the
    two axes span different real lengths. From myogait 0.8.2 on,
    ``step_length``/``walking_speed`` de-normalise to source pixels before
    scaling (isotropic), so this cross-check must do the same to stay
    comparable -- pass ``isotropic=Runtime.step_length_isotropic_native``.
    The horizontal displacement is then taken in source pixels
    (``dx x width``) against a metres-per-source-pixel scale; the aspect
    factor is exact for a vertical reference (myogait's femur) and a close
    approximation for the combined multi-segment scale, whose segments are
    predominantly vertical. On an older install leave it False so the
    cross-check reproduces myogait's own anisotropic numbers.
    """
    frames = data.get("frames", [])
    events = data.get("events", {})
    if not frames or not events or not scale_m_per_unit:
        return CalibratedSpatiotemporal()

    # De-normalise the horizontal displacement to source pixels when
    # myogait does (>= 0.8.2). scale_m_per_unit is metres per normalised
    # unit of a mostly-vertical reference, i.e. metres per (height-pixel);
    # dividing by height turns it into metres per source pixel, and the
    # step is measured as (dx x width) source pixels. Net effect: the
    # antero-posterior distances gain the frame aspect ratio (width /
    # height) the anisotropic path dropped.
    meta = data.get("meta", {}) or {}
    img_w = float(meta.get("width") or 1.0)
    img_h = float(meta.get("height") or 1.0)
    if isotropic and img_h:
        x_scale = img_w
        unit_scale = scale_m_per_unit / img_h
    else:
        x_scale = 1.0
        unit_scale = scale_m_per_unit

    all_hs = [
        {"frame": ev["frame"], "side": side}
        for side in ("left", "right")
        for ev in events.get(f"{side}_hs", [])
    ]
    all_hs.sort(key=lambda e: e["frame"])

    def _x(frame_idx: int, landmark: str) -> float | None:
        if frame_idx >= len(frames):
            return None
        return frames[frame_idx].get("landmarks", {}).get(landmark, {}).get("x")

    step_lengths: dict[str, list[float]] = {"left": [], "right": []}
    for i in range(len(all_hs) - 1):
        if all_hs[i]["side"] == all_hs[i + 1]["side"]:
            continue
        side = all_hs[i + 1]["side"]  # step is named by the leading foot
        x1 = _x(all_hs[i]["frame"], f"{side.upper()}_ANKLE")
        x2 = _x(all_hs[i + 1]["frame"], f"{side.upper()}_ANKLE")
        if x1 is not None and x2 is not None:
            step_lengths[side].append(abs((x2 - x1) * x_scale) * unit_scale)

    stride_lengths: dict[str, list[float]] = {"left": [], "right": []}
    speeds: dict[str, list[float]] = {"left": [], "right": []}
    for cycle in cycles.get("cycles", []):
        side = cycle["side"]
        ankle = f"{side.upper()}_ANKLE"
        x1 = _x(cycle["start_frame"], ankle)
        x2 = _x(cycle["end_frame"], ankle)
        if x1 is None or x2 is None:
            continue
        dist = abs((x2 - x1) * x_scale) * unit_scale
        stride_lengths[side].append(dist)
        if cycle.get("duration"):
            speeds[side].append(dist / cycle["duration"])

    def _mean_or_none(values: list[float]) -> float | None:
        return float(np.mean(values)) if values else None

    return CalibratedSpatiotemporal(
        step_length_left_m=_mean_or_none(step_lengths["left"]),
        step_length_right_m=_mean_or_none(step_lengths["right"]),
        stride_length_left_m=_mean_or_none(stride_lengths["left"]),
        stride_length_right_m=_mean_or_none(stride_lengths["right"]),
        speed_mean_m_s=_mean_or_none(speeds["left"] + speeds["right"]),
    )
