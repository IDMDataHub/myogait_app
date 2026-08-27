"""Tests for the recording-level interpretation gate."""

from myogait_app.quality import assess_quality


def _data(score: float = 85.0) -> dict:
    return {"frames": [{"landmarks": {}}], "quality": {"score": score}}


def test_quality_gate_accepts_good_extraction_with_usable_cycles():
    assessment = assess_quality(_data(), {"cycles": [{}, {}], "summary": {}})

    assert assessment.status == "accepted"
    assert assessment.allows_derived_metrics
    assert assessment.to_dict()["n_cycles"] == 2


def test_quality_gate_rejects_missing_cycles_even_with_a_good_score():
    assessment = assess_quality(_data(), {"cycles": [], "summary": {}})

    assert assessment.status == "rejected"
    assert not assessment.allows_derived_metrics
    assert "No gait cycle" in assessment.reasons[0]


def test_quality_gate_warns_for_rejected_cycles_and_a_borderline_score():
    assessment = assess_quality(
        _data(60.0), {"cycles": [{}], "summary": {"n_rejected_quality": 3}}
    )

    assert assessment.status == "warning"
    assert assessment.n_rejected_cycles == 3
    assert len(assessment.reasons) == 2
