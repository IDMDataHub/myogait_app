"""Unit tests for the video-vs-reference agreement battery.

Locks the metrics the Cohort accuracy table shows against the definitions the
validation report uses (rmse / mae / bias / cmc / rom / peak), so a regression
in any one -- or a silently dropped metric -- fails here rather than shipping a
wrong accuracy number to a clinician.
"""

from __future__ import annotations

import math

import numpy as np

from myogait_app.agreement import curve_metrics, summarize_agreement

# A realistic-ish sagittal knee curve: one flexion wave over the cycle.
_T = np.linspace(0, 2 * np.pi, 101)
_KNEE = 30.0 + 25.0 * (1 - np.cos(_T))  # 5..80 deg, single peak


def test_identical_curves_are_perfect_agreement():
    m = curve_metrics(_KNEE, _KNEE)
    assert m["rmse"] == 0.0
    assert m["mae"] == 0.0
    assert m["bias"] == 0.0
    assert m["rmse_centered"] == 0.0
    assert m["shape_r"] == 1.0
    assert math.isclose(m["cmc"], 1.0, abs_tol=1e-9)
    assert m["rom_err"] == 0.0
    assert m["peak_t_err"] == 0.0


def test_constant_offset_shows_in_bias_not_in_shape():
    offset = 4.0
    m = curve_metrics(_KNEE + offset, _KNEE)
    # A pure offset: bias == offset, raw RMSE == |offset|, but the shape is
    # untouched so centred RMSE ~ 0 and Pearson r ~ 1.
    assert math.isclose(m["bias"], offset, abs_tol=1e-9)
    assert math.isclose(m["mae"], offset, abs_tol=1e-9)
    assert math.isclose(m["rmse"], offset, abs_tol=1e-9)
    assert math.isclose(m["rmse_centered"], 0.0, abs_tol=1e-9)
    assert math.isclose(m["shape_r"], 1.0, abs_tol=1e-9)
    assert m["rom_err"] == 0.0
    # CMC, unlike Pearson r, is dragged below 1 by the offset -- the whole point
    # of reporting both.
    assert m["cmc"] < 1.0


def test_bias_sign_follows_video_minus_reference():
    assert curve_metrics(_KNEE - 3.0, _KNEE)["bias"] < 0
    assert curve_metrics(_KNEE + 3.0, _KNEE)["bias"] > 0


def test_amplitude_error_shows_in_rom_err():
    # Scale the wave about its mean: same shape, larger range of motion.
    scaled = _KNEE.mean() + 1.2 * (_KNEE - _KNEE.mean())
    m = curve_metrics(scaled, _KNEE)
    assert m["rom_err"] > 0  # video ROM exceeds reference ROM
    assert math.isclose(m["shape_r"], 1.0, abs_tol=1e-9)  # shape unchanged


def test_nan_or_empty_curve_yields_no_metrics():
    assert curve_metrics([], _KNEE) == {}
    bad = _KNEE.copy()
    bad[10] = np.nan
    assert curve_metrics(bad, _KNEE) == {}


def test_summarize_drops_uncorrelated_sides_and_averages_the_rest():
    good_l = {**curve_metrics(_KNEE + 2, _KNEE), "joint": "knee"}
    good_r = {**curve_metrics(_KNEE - 2, _KNEE), "joint": "knee"}
    # Anti-correlated: shape_r < TRACKED_OK_R, so it must be excluded.
    noise = {**curve_metrics(-_KNEE, _KNEE), "joint": "knee"}

    out = summarize_agreement([good_l, good_r, noise])
    assert out["knee"]["n"] == 2  # the noisy side dropped
    # +2 and -2 offsets average to ~0 signed bias but ~2 mae.
    assert math.isclose(out["knee"]["bias"], 0.0, abs_tol=1e-9)
    assert math.isclose(out["knee"]["mae"], 2.0, abs_tol=1e-9)
    assert 0.0 <= out["knee"]["cmc"] <= 1.0
