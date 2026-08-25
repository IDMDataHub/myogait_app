"""Clinical read-outs layered on the pooled cohort: validity, scores, norms.

Streamlit-free. Three things a clinician needs beyond the raw curves:

- **Per-parameter validity** -- which numbers are trustworthy enough to act on,
  from the markerless-vs-Vicon validation (hip/knee sagittal are clinical
  grade; the ankle's absolute offset is not; step length is unbiased on
  average but noisy per trial). Stated so a number is never read blind.
- **2-D gait scores** (GPS/GDI/GVS) -- single-number screening summaries,
  reusing ``myogait.scores`` (explicitly the 2-D sagittal screening variants,
  not the validated 3-D indices).
- **Normative bands** -- age-matched textbook reference, reusing
  ``myogait.normative``.

Every myogait call is guarded: an older install that lacks a function returns
``None``/``{}`` rather than raising, so the cohort still renders.
"""

from __future__ import annotations

#: grade -> how to read it. "clinical" = trust the value; "good" = reliable;
#: "caution" = read shape/relative, not the absolute; keyed by the joint or
#: parameter the Cohort tab displays.
PARAM_VALIDITY: dict[str, dict[str, str]] = {
    "hip": {
        "grade": "clinical",
        "note": "Sagittal hip vs Vicon: waveform r >= 0.97, centred RMSE < 4 deg.",
    },
    "knee": {
        "grade": "clinical",
        "note": "Sagittal knee vs Vicon: waveform r >= 0.97, centred RMSE < 4 deg.",
    },
    "ankle": {
        "grade": "caution",
        "note": "Ankle shape is good (r ~ 0.9) but the absolute offset is less "
                "stable -- read ROM and shape, not the zero.",
    },
    "cadence": {
        "grade": "good",
        "note": "Cadence / temporal parameters track Vicon within ~1%.",
    },
    "stance": {
        "grade": "good",
        "note": "Stance / swing share within a couple of % of Vicon.",
    },
    "step_length": {
        "grade": "caution",
        "note": "Unbiased on average but noisy per trial; metric only when a "
                "subject height is provided.",
    },
    "duration": {
        "grade": "good",
        "note": "Derived from the frame count and fps.",
    },
}

#: Order and labels for a compact validity legend.
VALIDITY_GRADES = {
    "clinical": "Clinical grade",
    "good": "Reliable",
    "caution": "Read with caution",
}


def validity(param: str) -> dict[str, str]:
    """Validity entry for a joint/parameter, or an empty dict if unknown."""
    return PARAM_VALIDITY.get(param, {})


def select_stratum(age=None) -> str:
    """Age-appropriate normative stratum, via myogait when available."""
    try:
        from myogait.normative import select_stratum as _select
    except Exception:
        # Same thresholds myogait uses, so behaviour matches without it.
        if isinstance(age, (int, float)):
            if age < 18:
                return "pediatric"
            if age >= 65:
                return "elderly"
        return "adult"
    return _select(age)


def normative_bands(joints, stratum: str = "adult") -> dict:
    """``{joint: {lower, upper, mean}}`` for overlay, empty if unavailable."""
    try:
        from myogait.normative import get_normative_band
    except Exception:
        return {}
    bands: dict = {}
    for joint in joints:
        try:
            bands[joint] = get_normative_band(joint, stratum=stratum)
        except Exception:
            continue
    return bands


def clinical_scores(cycles: dict, stratum: str = "adult") -> dict | None:
    """GPS-2D / GDI-2D overall + per-joint GVS from pooled cycles.

    ``cycles`` must carry a per-side ``summary`` with ``{joint}_mean`` curves
    (what :func:`pooling.pool_cycles` produces). Returns ``None`` when the
    installed myogait has no ``myogait.scores`` or the computation fails.
    """
    try:
        from myogait.scores import (
            gait_profile_score_2d,
            movement_analysis_profile,
            sagittal_deviation_index,
        )
    except Exception:
        return None
    try:
        gps = gait_profile_score_2d(cycles, stratum=stratum) or {}
        gdi = sagittal_deviation_index(cycles, stratum=stratum) or {}
        mapatt = movement_analysis_profile(cycles, stratum=stratum) or {}
    except Exception:
        return None

    gvs_by_joint: dict[str, float] = {}
    joints = mapatt.get("joints") or []
    left = mapatt.get("left") or []
    right = mapatt.get("right") or []
    for i, joint in enumerate(joints):
        sides = [v for v in (
            left[i] if i < len(left) else None,
            right[i] if i < len(right) else None,
        ) if isinstance(v, (int, float))]
        if sides:
            gvs_by_joint[joint] = float(sum(sides) / len(sides))

    return {
        "gps_2d_overall": gps.get("gps_2d_overall"),
        "gdi_2d_overall": gdi.get("gdi_2d_overall"),
        "gvs_by_joint": gvs_by_joint,
        "note": "2-D sagittal screening scores, not the validated 3-D indices.",
    }
