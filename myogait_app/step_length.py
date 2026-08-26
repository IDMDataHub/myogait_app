"""Metric step length from 3-D marker trajectories, computed automatically.

Video pixel calibration gives a step length in metres only when the pixel
scale is trustworthy; a marker (C3D) pivot instead carries real 3-D marker
positions, so the true metric step length is right there -- no calibration
needed. This module reads it straight off the heel and hip markers, so a
Cohort with a Vicon reference shows a real step length instead of a dash.

Streamlit-free and unit-testable. The one entry point,
``step_length_m_from_markers``, returns ``None`` when the markers needed are
absent or too sparse, so a caller can simply fall back to the video estimate.

Method (marker-only, no external events needed): heel strikes are the frames
where a heel is most forward relative to the pelvis (the coordinate-based
"Zeni" rule the pipeline already uses for events); step length is the
antero-posterior distance between the two heels at that instant.
"""

from __future__ import annotations

import numpy as np

#: Physiological human step-length bounds (m); values outside are treated as
#: detection noise and dropped, matching the Cohort's own clamp.
_STEP_LENGTH_M_RANGE = (0.2, 1.2)


def _as_array(markers: dict, name: str):
    value = markers.get(name)
    if value is None:
        return None
    arr = np.asarray(value, dtype=float)
    return arr if arr.ndim == 2 and arr.shape[1] == 3 else None


def _unit_scale(coords: np.ndarray) -> float:
    """0.001 when the coordinates look like millimetres, else 1.0 (metres).

    Human marker coordinates are under a few metres; in millimetres they run
    to hundreds or thousands. Decide on the median finite magnitude so a few
    stray large values do not flip the unit.
    """
    finite = coords[np.isfinite(coords)]
    if finite.size == 0:
        return 1.0
    return 0.001 if float(np.median(np.abs(finite))) > 50.0 else 1.0


def _forward_axis(heels: np.ndarray) -> int:
    """The horizontal walking axis: the one the heels travel along most."""
    spans = np.nanmax(heels, axis=0) - np.nanmin(heels, axis=0)
    return int(np.argmax(spans))


def _forward_strikes(heel_rel: np.ndarray) -> list[int]:
    """Heel-strike frames: local maxima of heel-minus-pelvis forward position."""
    strikes: list[int] = []
    for i in range(1, len(heel_rel) - 1):
        window = heel_rel[i - 1:i + 2]
        if np.isfinite(window).all() and heel_rel[i] >= heel_rel[i - 1] and heel_rel[i] > heel_rel[i + 1]:
            strikes.append(i)
    return strikes


def step_length_m_from_markers(markers: dict) -> float | None:
    """Mean metric step length (m) from heel + hip markers, or ``None``.

    Robust to walking direction (positions are taken relative to the pelvis,
    and the step is an absolute distance) and to millimetre/metre units.
    """
    if not isinstance(markers, dict):
        return None
    left_heel = _as_array(markers, "LEFT_HEEL")
    right_heel = _as_array(markers, "RIGHT_HEEL")
    left_hip = _as_array(markers, "LEFT_HIP")
    right_hip = _as_array(markers, "RIGHT_HIP")
    if any(a is None for a in (left_heel, right_heel, left_hip, right_hip)):
        return None

    n = min(len(left_heel), len(right_heel), len(left_hip), len(right_hip))
    if n < 5:
        return None
    left_heel, right_heel = left_heel[:n], right_heel[:n]
    pelvis = (left_hip[:n] + right_hip[:n]) / 2.0

    scale = _unit_scale(np.vstack([left_heel, right_heel]))
    axis = _forward_axis(np.vstack([left_heel, right_heel]))

    lh = left_heel[:, axis] * scale
    rh = right_heel[:, axis] * scale
    pel = pelvis[:, axis] * scale

    steps: list[float] = []
    for this_heel, other_heel in ((lh, rh), (rh, lh)):
        for i in _forward_strikes(this_heel - pel):
            distance = abs(this_heel[i] - other_heel[i])
            if np.isfinite(distance):
                steps.append(float(distance))

    lo, hi = _STEP_LENGTH_M_RANGE
    plausible = [s for s in steps if lo <= s <= hi]
    if len(plausible) < 2:
        return None
    return float(np.mean(plausible))
