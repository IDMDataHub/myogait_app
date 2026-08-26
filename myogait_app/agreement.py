"""Accuracy of markerless curves against a marker-based reference.

Ported from the validation report's ``curve_metrics`` so the Cohort tab can
show, per joint, how a video mean cycle curve agrees with the paired Vicon
mean cycle curve -- the *ecart / biais* a marker reference unlocks and video
alone cannot give. Streamlit-free and unit-testable.

Every metric is on two 101-point mean cycle curves. The angle-error battery
mirrors the validation report's single-trial Vicon benchmark
(``experimental_vicon._angle_error_metrics``: rmse / mae / bias / rom_diff /
cmc) so the clinician-facing Cohort table shows the *same* numbers, plus the
waveform-shape metrics the app already read:

- ``rmse``          -- raw RMSE, includes the constant offset.
- ``mae``           -- mean absolute error (report: ``mae_deg``).
- ``bias``          -- signed mean video-minus-reference (report: ``bias_deg``);
                       the direction of the offset, not just its size.
- ``rmse_centered`` -- each curve minus its own mean first; isolates shape +
                       amplitude error from the zero-offset (a calibratable
                       joint-definition difference).
- ``shape_r``       -- Pearson correlation of the two curves (waveform match).
- ``cmc``           -- coefficient of multiple correlation (report: ``cmc``);
                       a shape metric that, unlike Pearson r, is penalised by a
                       constant offset.
- ``rom_err``       -- video range of motion minus reference ROM (deg).
- ``peak_err``      -- video peak minus reference peak (deg).
- ``peak_t_err``    -- timing error of the peak, in % of cycle, circular so a
                       peak near 0/100 % does not read as a full-cycle error.
"""

from __future__ import annotations

import numpy as np


def _cmc(a: np.ndarray, b: np.ndarray) -> float:
    """Coefficient of multiple correlation, per the report's definition.

    1.0 for identical curves; driven down by a constant offset (unlike
    Pearson r). NaN when the total variance is degenerate.
    """
    if a.size != b.size or a.size < 3:
        return float("nan")
    grand = float(np.mean(np.concatenate([a, b])))
    frame_mean = (a + b) / 2.0
    within = np.sum((a - frame_mean) ** 2 + (b - frame_mean) ** 2) / a.size
    total = np.sum((a - grand) ** 2 + (b - grand) ** 2) / (2 * a.size - 1)
    if total <= 1e-12:
        return float("nan")
    return float(np.sqrt(max(0.0, 1.0 - within / total)))


def curve_metrics(video_curve, reference_curve) -> dict:
    """Agreement metrics between a video and a reference mean cycle curve.

    Returns an empty dict when either curve is missing, too short or has NaNs,
    so a caller can simply skip a joint/side that could not be compared.
    """
    a = np.asarray(video_curve, dtype=float)
    b = np.asarray(reference_curve, dtype=float)
    n = min(a.size, b.size)
    if n == 0:
        return {}
    a, b = a[:n], b[:n]
    if np.isnan(a).any() or np.isnan(b).any():
        return {}

    rmse = float(np.sqrt(np.mean((a - b) ** 2)))
    mae = float(np.mean(np.abs(a - b)))
    bias = float(np.mean(a - b))
    ac, bc = a - a.mean(), b - b.mean()
    rmse_centered = float(np.sqrt(np.mean((ac - bc) ** 2)))
    shape_r = (
        float(np.corrcoef(a, b)[0, 1]) if a.std() > 0 and b.std() > 0 else float("nan")
    )
    cmc = _cmc(a, b)
    rom_err = float((a.max() - a.min()) - (b.max() - b.min()))
    peak_err = float(a.max() - b.max())
    delta = (int(np.argmax(a)) - int(np.argmax(b))) % n
    peak_t_err = float(delta if delta <= n // 2 else delta - n) * (100.0 / n)

    return {
        "rmse": rmse,
        "mae": mae,
        "bias": bias,
        "rmse_centered": rmse_centered,
        "shape_r": shape_r,
        "cmc": cmc,
        "rom_err": rom_err,
        "peak_err": peak_err,
        "peak_t_err": peak_t_err,
    }


#: Which joint-sides count as trustworthy enough to average, mirroring the
#: report: a waveform correlation below this means the two curves are not even
#: describing the same movement, so the numeric error is meaningless.
TRACKED_OK_R = 0.5


def summarize_agreement(per_joint_side: list[dict]) -> dict:
    """Mean agreement per joint over the tracked-ok joint-sides.

    ``per_joint_side`` is a list of ``curve_metrics`` outputs each tagged with
    a ``joint`` key. Returns ``{joint: {rmse, rmse_centered, shape_r,
    rom_err_abs, peak_t_err_abs, n}}``.
    """
    joints: dict[str, list[dict]] = {}
    for entry in per_joint_side:
        if not entry or "shape_r" not in entry:
            continue
        if not (entry.get("shape_r", 0) > TRACKED_OK_R):
            continue
        joints.setdefault(entry["joint"], []).append(entry)

    out: dict[str, dict] = {}
    for joint, entries in joints.items():
        cmcs = [e["cmc"] for e in entries if not np.isnan(e.get("cmc", float("nan")))]
        out[joint] = {
            "rmse": float(np.mean([e["rmse"] for e in entries])),
            "mae": float(np.mean([e["mae"] for e in entries])),
            "bias": float(np.mean([e["bias"] for e in entries])),
            "rmse_centered": float(np.mean([e["rmse_centered"] for e in entries])),
            "shape_r": float(np.mean([e["shape_r"] for e in entries])),
            "cmc": float(np.mean(cmcs)) if cmcs else float("nan"),
            "rom_err_abs": float(np.mean([abs(e["rom_err"]) for e in entries])),
            "peak_t_err_abs": float(np.mean([abs(e["peak_t_err"]) for e in entries])),
            "n": len(entries),
        }
    return out
