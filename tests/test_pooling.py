"""Unit tests for the cohort pooling and video-vs-reference agreement.

Pure functions only: RunResult objects are built directly, so these need
neither myogait nor streamlit (the pipeline itself is exercised elsewhere).
"""

from __future__ import annotations

import numpy as np
import pytest

from myogait_app.agreement import curve_metrics, summarize_agreement
from myogait_app.pooling import (
    RunResult,
    _detect_kind,
    _duration_s,
    condition_agreement,
    condition_summary,
    group_by_condition,
    overall_agreement,
)

_HIP = (np.sin(np.linspace(0, np.pi, 101)) * 30).tolist()


def _cycle(side: str) -> dict:
    return {
        "side": side,
        "cycle_id": 1,
        "stance_pct": 60,
        "angles_normalized": {"hip": _HIP, "knee": _HIP, "ankle": _HIP},
    }


def _run(kind: str, condition: str, patient: str, run: str) -> RunResult:
    cycles = {"cycles": [_cycle("left"), _cycle("right")], "summary": {}}
    return RunResult(
        name=f"{patient}_{run}",
        study={"condition": condition, "patient_id": patient, "run": run},
        ok=True,
        kind=kind,
        duration_s=2.0,
        cycles=cycles,
        stats={"spatiotemporal": {"cadence_steps_per_min": 110.0}},
    )


def test_curve_metrics_identical():
    m = curve_metrics(_HIP, _HIP)
    assert m["rmse"] == pytest.approx(0.0, abs=1e-9)
    assert m["rmse_centered"] == pytest.approx(0.0, abs=1e-9)
    assert m["shape_r"] == pytest.approx(1.0)
    assert m["rom_err"] == pytest.approx(0.0)
    assert m["peak_t_err"] == pytest.approx(0.0)


def test_curve_metrics_constant_offset():
    shifted = [v + 5.0 for v in _HIP]
    m = curve_metrics(shifted, _HIP)
    assert m["rmse"] == pytest.approx(5.0)
    assert m["rmse_centered"] == pytest.approx(0.0, abs=1e-9)  # offset removed
    assert m["shape_r"] == pytest.approx(1.0)


def test_curve_metrics_empty_on_nan():
    assert curve_metrics([float("nan")] * 101, _HIP) == {}
    assert curve_metrics([], _HIP) == {}


def test_detect_kind():
    assert _detect_kind({"c3d_markers_3d": {"LEFT_HEEL": [1]}}) == "vicon"
    assert _detect_kind({"study": {"source": "c3d"}}) == "vicon"
    assert _detect_kind({"meta": {"source": "c3d"}}) == "vicon"
    assert _detect_kind({"meta": {"source": "video"}}) == "video"
    assert _detect_kind({}) == "video"


def test_duration_from_fps():
    assert _duration_s({"meta": {"fps": 50}, "frames": [{}] * 100}) == pytest.approx(2.0)
    assert _duration_s({"meta": {"duration_s": 3.5}}) == pytest.approx(3.5)
    assert _duration_s({"meta": {}, "frames": []}) is None


def test_group_by_condition_and_summary():
    runs = [_run("video", "A", "P1", "r1"), _run("video", "A", "P2", "r1"),
            _run("video", "B", "P1", "r2")]
    groups = group_by_condition(runs)
    assert set(groups) == {"A", "B"}
    summary = condition_summary(groups["A"])
    assert summary["n_runs"] == 2
    assert summary["n_patients"] == 2
    assert summary["n_reference"] == 0
    assert summary["duration_s"] == pytest.approx(2.0)
    assert summary["rom_deg"]["hip"] == pytest.approx(30.0, abs=1e-6)


def test_condition_agreement_requires_a_reference():
    video = _run("video", "A", "P1", "r1")
    assert condition_agreement([video]) is None  # variability only

    both = [video, _run("vicon", "A", "P1", "r1")]
    agreement = condition_agreement(both)
    assert agreement is not None
    assert agreement["n_video"] == 1
    assert agreement["n_reference"] == 1
    assert agreement["by_joint"]["hip"]["rmse"] == pytest.approx(0.0, abs=1e-9)
    assert agreement["by_joint"]["hip"]["shape_r"] == pytest.approx(1.0)
    # video_pooled/vicon_pooled: what a video-vs-reference comparison chart
    # needs (each kind pooled separately, not blended into one mean).
    assert agreement["video_pooled"]["summary"]["left"]["hip_mean"] == pytest.approx(_HIP)
    assert agreement["vicon_pooled"]["summary"]["left"]["hip_mean"] == pytest.approx(_HIP)


def test_overall_agreement_pairs_by_patient_across_conditions():
    # Same patient, markerless and marker in DIFFERENT conditions.
    runs = [
        _run("video", "iphone", "P1", "r1"),
        _run("vicon", "lab", "P1", "r2"),
        _run("video", "iphone", "P2", "r1"),  # P2 has no reference
    ]
    agreement = overall_agreement(runs)
    assert agreement is not None
    assert agreement["n_patients"] == 1  # only P1 has both kinds
    assert agreement["n_video"] == 1 and agreement["n_reference"] == 1
    assert "hip" in agreement["by_joint"]
    assert agreement["video_pooled"]["summary"]["left"]["n_cycles"] == 1
    assert agreement["vicon_pooled"]["summary"]["left"]["n_cycles"] == 1

    # condition_agreement finds nothing here: the two kinds never share a
    # condition. Pairing by patient is what makes accuracy appear automatically.
    for _cond, cond_runs in group_by_condition(runs).items():
        assert condition_agreement(cond_runs) is None


def test_overall_agreement_none_without_any_reference():
    runs = [_run("video", "iphone", "P1", "r1"), _run("video", "iphone", "P2", "r1")]
    assert overall_agreement(runs) is None


def test_overall_agreement_does_not_pair_runs_without_a_patient_identifier():
    video = _run("video", "iphone", "P1", "r1")
    reference = _run("vicon", "lab", "P2", "r1")
    video.study.pop("patient_id")
    reference.study.pop("patient_id")

    assert overall_agreement([video, reference]) is None


def test_summarize_agreement_drops_uncorrelated():
    good = {"joint": "hip", "shape_r": 0.9, "rmse": 2.0, "mae": 1.6, "bias": 1.0,
            "rmse_centered": 1.0, "cmc": 0.95, "rom_err": 1.0, "peak_t_err": 2.0}
    bad = {"joint": "hip", "shape_r": 0.2, "rmse": 9.0, "mae": 8.0, "bias": -7.0,
           "rmse_centered": 8.0, "cmc": 0.3, "rom_err": 9.0, "peak_t_err": 9.0}
    out = summarize_agreement([good, bad])
    assert out["hip"]["n"] == 1  # the r=0.2 joint-side is excluded
    assert out["hip"]["rmse"] == pytest.approx(2.0)
