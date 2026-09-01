"""ICC, Bland-Altman and biomarker extraction (reliability module).

Pure and synthetic. The ICC implementation is locked against the published
Shrout & Fleiss (1979) worked example, so a regression is a change in the
math, not in a fixture.
"""
from __future__ import annotations

import numpy as np
import pytest

from myogait_app.pooling import RunResult
from myogait_app.reliability import (
    BlandAltman,
    ICCResult,
    biomarker_table,
    bland_altman,
    group_comparison_biomarkers,
    icc,
    paired_video_reference,
    retest_battery,
    retest_matrix,
    validity_battery,
)

# Shrout & Fleiss (1979), Table 2: 6 subjects x 4 raters.
SF_MATRIX = np.array([
    [9, 2, 5, 8],
    [6, 1, 3, 2],
    [8, 4, 6, 8],
    [7, 1, 2, 6],
    [10, 5, 6, 9],
    [6, 2, 4, 7],
], dtype=float)


# ── ICC ──────────────────────────────────────────────────────────────


def test_icc2_1_matches_shrout_fleiss():
    result = icc(SF_MATRIX, form="ICC2_1")
    assert isinstance(result, ICCResult)
    assert result.value == pytest.approx(0.29, abs=0.005)
    assert result.n == 6 and result.k == 4


def test_icc3_1_matches_shrout_fleiss():
    result = icc(SF_MATRIX, form="ICC3_1")
    assert result.value == pytest.approx(0.71, abs=0.005)


def test_icc2_k_matches_shrout_fleiss():
    result = icc(SF_MATRIX, form="ICC2_k")
    assert result.value == pytest.approx(0.62, abs=0.005)


def test_icc_perfect_agreement_is_one():
    base = np.arange(5, dtype=float)
    matrix = np.column_stack([base, base])
    assert icc(matrix, form="ICC2_1").value == pytest.approx(1.0)
    assert icc(matrix, form="ICC3_1").value == pytest.approx(1.0)


def test_icc_guards_return_none():
    small = SF_MATRIX[:4]                      # < 5 subjects
    assert icc(small, form="ICC2_1") is None
    one_rater = SF_MATRIX[:, :1]               # < 2 raters
    assert icc(one_rater, form="ICC2_1") is None
    assert icc([1, 2, 3], form="ICC2_1") is None  # not 2-D


def test_icc_drops_nan_rows():
    dirty = SF_MATRIX.copy()
    dirty = np.vstack([dirty, [np.nan, 1, 2, 3]])
    result = icc(dirty, form="ICC3_1")
    assert result.n == 6                       # the NaN row is gone
    assert result.value == pytest.approx(0.71, abs=0.005)


def test_icc_unknown_form_raises():
    with pytest.raises(ValueError):
        icc(SF_MATRIX, form="ICC9_9")


def test_icc3_ci_bounds_are_ordered_and_contain_the_estimate():
    result = icc(SF_MATRIX, form="ICC3_1")
    if result.ci95 is not None:                # scipy present in practice
        lo, hi = result.ci95
        assert lo <= result.value <= hi


# ── Bland-Altman ─────────────────────────────────────────────────────


def test_bland_altman_constant_offset():
    a = np.array([10.0, 20.0, 30.0, 40.0])
    b = a - 5.0
    ba = bland_altman(a, b)
    assert isinstance(ba, BlandAltman)
    assert ba.bias == pytest.approx(5.0)
    assert ba.sd == pytest.approx(0.0)
    assert ba.loa_low == pytest.approx(5.0)
    assert ba.loa_high == pytest.approx(5.0)
    assert ba.n == 4


def test_bland_altman_hand_computed():
    a = np.array([1.0, 2.0, 3.0, 4.0])
    b = np.array([1.5, 1.5, 3.5, 3.5])
    diffs = a - b                              # [-0.5, 0.5, -0.5, 0.5]
    ba = bland_altman(a, b)
    assert ba.bias == pytest.approx(float(diffs.mean()))
    assert ba.sd == pytest.approx(float(diffs.std(ddof=1)))
    assert ba.loa_high == pytest.approx(ba.bias + 1.96 * ba.sd)


def test_bland_altman_guards():
    assert bland_altman([1.0, 2.0], [1.0, 2.0]) is None       # < 3 pairs
    assert bland_altman([1, 2, 3], [1, 2]) is None            # shape mismatch
    ba = bland_altman([1.0, 2.0, np.nan, 4.0], [1.0, 2.0, 3.0, 4.0])
    assert ba.n == 3                                          # NaN pair dropped


# ── Biomarker extraction and pairings ────────────────────────────────


def _cycles(rom: float) -> dict:
    wave = np.linspace(0.0, rom, 101).tolist()
    return {"cycles": [
        {"side": "left", "angles_normalized": {j: wave for j in ("hip", "knee", "ankle")}},
    ], "summary": {}}


def _run(patient, kind="video", rom=30.0, run="r1", group="", condition="base",
         cadence=110.0) -> RunResult:
    return RunResult(
        name=f"{patient}_{run}_{kind}",
        study={"patient_id": patient, "run": run, "group": group, "condition": condition},
        ok=True, kind=kind, cycles=_cycles(rom),
        stats={"spatiotemporal": {"cadence_steps_per_min": cadence}},
    )


def test_biomarker_table_long_format():
    rows = biomarker_table([_run("P1", rom=100.0)])
    params = {r["parameter"]: r["value"] for r in rows}
    assert params["hip_rom"] == pytest.approx(100.0)
    assert params["cadence_steps_per_min"] == pytest.approx(110.0)
    assert all(r["patient"] == "P1" for r in rows)


def test_paired_video_reference_needs_both_kinds():
    runs = [_run("P1", "video", rom=30.0), _run("P1", "vicon", rom=35.0),
            _run("P2", "video", rom=28.0)]   # P2 has no reference
    video, ref, patients = paired_video_reference(runs, "hip_rom")
    assert patients == ["P1"]
    assert video[0] == pytest.approx(30.0) and ref[0] == pytest.approx(35.0)


def test_retest_matrix_truncates_to_common_k():
    runs = [_run("P1", rom=30, run="r1"), _run("P1", rom=31, run="r2"),
            _run("P1", rom=32, run="r3"),
            _run("P2", rom=28, run="r1"), _run("P2", rom=29, run="r2")]
    matrix = retest_matrix(runs, "hip_rom")
    assert matrix.shape == (2, 2)              # truncated to min k = 2


def test_retest_matrix_none_with_single_patient():
    runs = [_run("P1", rom=30, run="r1"), _run("P1", rom=31, run="r2")]
    assert retest_matrix(runs, "hip_rom") is None


def test_validity_battery_reports_pairs_and_guards():
    runs = []
    for i in range(6):
        runs.append(_run(f"P{i}", "video", rom=30.0 + i))
        runs.append(_run(f"P{i}", "vicon", rom=32.0 + i))
    battery = validity_battery(runs, ("hip_rom",))
    entry = battery[0]
    assert entry["n_patients"] == 6
    assert entry["bland_altman"].bias == pytest.approx(-2.0)  # video under-reads
    assert entry["icc"] is not None            # 6 subjects x 2 raters


def test_retest_battery_shapes():
    runs = []
    for i in range(6):
        runs.append(_run(f"P{i}", rom=30.0 + i, run="r1"))
        runs.append(_run(f"P{i}", rom=30.5 + i, run="r2"))
    battery = retest_battery(runs, ("hip_rom",))
    entry = battery[0]
    assert entry["n_patients"] == 6 and entry["k"] == 2
    assert entry["icc"] is not None and entry["icc"].form == "ICC3_1"


def test_group_comparison_biomarkers():
    runs = ([_run(f"A{i}", rom=40.0 + i, condition="groupA") for i in range(4)]
            + [_run(f"B{i}", rom=20.0 + i, condition="groupB") for i in range(4)])
    rows = group_comparison_biomarkers(
        runs, "groupA", "groupB", ("hip_rom",), by="condition")
    entry = rows[0]
    assert entry["n_a"] == 4 and entry["n_b"] == 4
    assert entry["delta"] == pytest.approx(20.0)
    assert entry["hedges_g"] is not None and entry["hedges_g"] > 5.0
