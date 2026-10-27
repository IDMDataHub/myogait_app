"""Markerless kinetics for the app: per-foot ground reaction forces, centre of
pressure and joint moments without force plates (``myogait.estimate_kinetics``,
myogait >= 0.10).

Needs the subject's body mass and a length reference (height or femur). The
step never blocks the gait analysis: if it cannot run (older myogait, missing
anthropometry, too few gait events) it returns ``None`` or a dict with an
``error`` key that the UI shows as a note.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np


def kinetics_available() -> bool:
    try:
        from myogait import estimate_kinetics  # noqa: F401
    except ImportError:
        return False
    return True


def compute_kinetics(data: dict, subject: Any, video_path: Optional[str] = None,
                     camera_moving: Optional[bool] = None) -> Optional[dict]:
    """Run ``myogait.estimate_kinetics`` on an events-bearing pivot.

    ``subject`` is a :class:`myogait_app.pipeline.SubjectConfig` (or any object with ``weight_kg``,
    ``height_m``, ``femur_length_mm`` and ``sex``). Returns ``None`` when the mass or the length reference is
    missing, ``{"error": ...}`` when the computation fails, else the myogait result plus a ``table``
    (per-stance peaks, one row per stance) and ``mean_curves`` (per side, 101 points).
    """
    mass = getattr(subject, "weight_kg", None)
    height = getattr(subject, "height_m", None); femur = getattr(subject, "femur_length_mm", None)
    if not mass or not (height or femur):
        return None
    if not kinetics_available():
        return {"error": "myogait >= 0.10 is required for kinetics (estimate_kinetics)."}
    from myogait import estimate_kinetics
    sex = (getattr(subject, "sex", None) or "M")[:1].upper()
    try:
        res = estimate_kinetics(data, float(mass), height_m=height, femur_mm=femur, sex=sex if sex in ("M", "F") else "M",
                                video_path=video_path, camera_moving=camera_moving)
    except Exception as exc:  # noqa: BLE001 - reported to the user, never raised
        return {"error": f"{type(exc).__name__}: {exc}"}
    if not res.get("stances"):
        return {"error": "No complete stance with both double-support events was found."}
    res["table"] = kinetics_table(res)
    res["mean_curves"] = mean_curves(res)
    return res


def kinetics_table(res: dict):
    """One row per stance: interpretable peaks of the per-foot GRF and of the sagittal moments."""
    import pandas as pd

    rows = []
    for st in res.get("stances", []):
        fv, fap = np.asarray(st["vgrf_bw"]), np.asarray(st["apgrf_bw"])
        an, kn, hp, pw = (np.asarray(st[k]) for k in ("ankle_Nm_kg", "knee_Nm_kg", "hip_Nm_kg", "ankle_power_W_kg"))
        p1, p2 = fv[5:50].max(), fv[50:96].max()
        rows.append({"side": st["side"], "on_frame": st["on"], "off_frame": st["off"],
                     "vGRF peak 1 (BW)": p1, "vGRF peak 2 (BW)": p2, "a1/a2": p1 / p2 if p2 > 0 else np.nan,
                     "braking peak (BW)": -fap[:50].min(), "propulsion peak (BW)": fap[50:].max(),
                     "ankle plantarflexor peak (N·m/kg)": an.max(), "knee extensor peak 0-40 % (N·m/kg)": kn[:41].max(),
                     "hip extensor peak 0-30 % (N·m/kg)": hp[:31].max(), "hip flexor peak (N·m/kg)": -hp.min(),
                     "ankle power A2 (W/kg)": pw[50:].max()})
    return pd.DataFrame(rows)


def mean_curves(res: dict) -> dict:
    """Mean ± SD of the 101-point stance curves, per side."""
    keys = ("vgrf_bw", "apgrf_bw", "cop_minus_ankle_m", "ankle_Nm_kg", "knee_Nm_kg", "hip_Nm_kg", "ankle_power_W_kg")
    out = {}
    for side in ("left", "right"):
        sts = [s for s in res.get("stances", []) if s["side"] == side]
        if sts:
            out[side] = {k: {"mean": np.mean([s[k] for s in sts], 0), "sd": np.std([s[k] for s in sts], 0), "n": len(sts)} for k in keys}
    return out
