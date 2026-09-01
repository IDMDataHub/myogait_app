"""Unit tests for gait_accelerometry.py -- the virtual accelerometer and

its biomarkers, computed from a pivot's own landmarks with no IMU.
"""
from __future__ import annotations

import numpy as np
import pytest

from myogait_app import gait_accelerometry as ga
from myogait_app.demo import make_demo_data


def _walk(**kwargs):
    return make_demo_data(n_frames=300, fps=30.0, progression=0.25, noise=0.0015, **kwargs)


# ── Virtual signal ───────────────────────────────────────────────────


@pytest.mark.parametrize("site", ga.SITES)
def test_every_site_resolves_on_a_full_demo_walk(site):
    data = _walk()
    assert ga.site_available(data, site)
    sig = ga.compute_virtual_signal(data, site=site)
    assert sig is not None
    assert sig.ap.shape == sig.v.shape
    assert sig.fs == 100.0
    assert sig.duration_s == pytest.approx(len(sig.v) / 100.0)
    assert np.isfinite(sig.ap).all()
    assert np.isfinite(sig.v).all()


def test_unknown_site_returns_none():
    assert ga.compute_virtual_signal(_walk(), site="elbow") is None


def test_too_short_a_recording_returns_none():
    data = make_demo_data(n_frames=10, fps=30.0)
    assert ga.compute_virtual_signal(data) is None


def test_missing_torso_landmarks_disable_every_site_not_only_the_one_removed():
    """Every site's normalisation needs the shoulder-hip distance, so

    losing the hips breaks sternum too, not only sacrum/lumbar.
    """
    data = _walk()
    for frame in data["frames"]:
        frame["landmarks"].pop("LEFT_HIP", None)
        frame["landmarks"].pop("RIGHT_HIP", None)
    for site in ga.SITES:
        assert not ga.site_available(data, site)
        assert ga.compute_virtual_signal(data, site=site) is None


def test_resample_rate_is_honoured():
    sig = ga.compute_virtual_signal(_walk(), site="sacrum", fs_out=50.0)
    assert sig.fs == 50.0
    assert sig.v.shape[0] == pytest.approx(300 / 30.0 * 50.0, abs=2)


# ── Biomarkers ───────────────────────────────────────────────────────


def test_analyze_recording_produces_every_biomarker_group():
    bio = ga.analyze_recording(_walk(), site="sacrum")
    assert bio is not None
    assert bio.site == "sacrum"
    assert bio.segment_length > 0
    assert bio.temporal.total_steps > 0
    assert bio.temporal.cadence > 0
    # Autocorrelation coefficients are bounded in [-1, 1] by construction.
    assert -1 <= bio.regularity.C1_V <= 1
    assert -1 <= bio.regularity.C2_V <= 1
    assert bio.variability.rms_total >= max(bio.variability.rms_AP, bio.variability.rms_V)


def test_analyze_recording_returns_none_when_the_signal_cannot_be_built():
    data = make_demo_data(n_frames=5, fps=30.0)
    assert ga.analyze_recording(data) is None


def test_to_dict_is_flat_and_prefixed():
    bio = ga.analyze_recording(_walk(), site="sacrum")
    flat = bio.to_dict()
    assert flat["temporal_cadence"] == bio.temporal.cadence
    assert flat["reg_C2_V"] == bio.regularity.C2_V
    assert flat["site"] == "sacrum"
    assert all(not isinstance(v, (dict, list)) for v in flat.values())


def test_no_locolike_or_proprietary_fields_are_exposed():
    """Regression: the source script's proprietary RDM/_locolike indices

    (see this module's own docstring) must never resurface here.
    """
    bio = ga.analyze_recording(_walk(), site="sacrum")
    flat = bio.to_dict()
    assert not any("locolike" in k.lower() for k in flat)
    assert not any("rdm" in k.lower() for k in flat)


def test_harmonic_ratio_of_a_clean_periodic_signal_is_positive():
    fs = 100.0
    t = np.arange(0, 20, 1 / fs)
    f0 = 0.9
    v = np.sin(2 * np.pi * f0 * t) + 0.3 * np.sin(2 * np.pi * 2 * f0 * t)
    ap = 0.5 * np.sin(2 * np.pi * f0 * t + 0.4)
    bio = ga.compute_all_biomarkers(ap, v, fs, site="sacrum")
    assert bio.harmonic.HR_V > 0
    assert bio.harmonic.IH_V > 0


# ── Reference ranges (published literature only) ────────────────────


def test_every_category_entry_resolves_to_a_real_biomarker():
    """Every code the UI groups under a category must be a key

    ``to_dict()`` actually produces -- a typo here would silently show a
    blank cell forever, never an error.
    """
    bio = ga.analyze_recording(_walk(), site="sacrum")
    flat = bio.to_dict()
    for entries in ga.BIOMARKER_CATEGORIES.values():
        for code, _label, _desc in entries:
            assert code in flat, code


def test_reference_range_lookup_covers_every_range_this_module_defines():
    for code in ga.REFERENCE_RANGES:
        assert ga.get_reference_range(code) != "-", code
        assert ga.get_clinical_interpretation(code, -1e9) != "-"


def test_interpretation_flags_low_high_and_normal():
    code = "temporal_cadence"
    lo, hi = ga.REFERENCE_RANGES[code]["min"], ga.REFERENCE_RANGES[code]["max"]
    assert ga.get_reference_status(code, lo - 10) == "low"
    assert ga.get_reference_status(code, hi + 10) == "high"
    assert ga.get_reference_status(code, (lo + hi) / 2) == "normal"


def test_unknown_code_is_reported_as_not_applicable():
    assert ga.get_reference_range("not_a_real_code") == "-"
    assert ga.get_reference_status("not_a_real_code", 1.0) == "n/a"
    assert ga.get_clinical_interpretation("not_a_real_code", 1.0) == "-"
