"""Streamlit-free contracts for the Cohort clinical read-outs."""

from __future__ import annotations

import sys
from types import ModuleType

from myogait_app.clinical import (
    PARAM_VALIDITY,
    VALIDITY_GRADES,
    clinical_scores,
    select_stratum,
    validity,
)


def test_validity_covers_every_cohort_parameter_and_joint() -> None:
    displayed = {"hip", "knee", "ankle", "cadence", "stance", "step_length", "duration"}

    assert displayed <= PARAM_VALIDITY.keys()
    for parameter in displayed:
        entry = validity(parameter)
        assert entry["grade"] in VALIDITY_GRADES
        assert entry["note"]
    assert validity("unknown") == {}


def test_clinical_scores_combines_left_and_right_gvs(monkeypatch) -> None:
    package = ModuleType("myogait")
    package.__path__ = []  # Mark it as a package for the import below.
    scores = ModuleType("myogait.scores")
    scores.gait_profile_score_2d = lambda cycles, stratum: {"gps_2d_overall": 4.2}
    scores.sagittal_deviation_index = lambda cycles, stratum: {"gdi_2d_overall": 91.0}
    scores.movement_analysis_profile = lambda cycles, stratum: {
        "joints": ["hip", "knee", "ankle"],
        "left": [2.0, 3.0, None],
        "right": [4.0, None, 6.0],
    }
    monkeypatch.setitem(sys.modules, "myogait", package)
    monkeypatch.setitem(sys.modules, "myogait.scores", scores)

    result = clinical_scores({"summary": {}}, stratum="adult")

    assert result == {
        "gps_2d_overall": 4.2,
        "gdi_2d_overall": 91.0,
        "gvs_by_joint": {"hip": 3.0, "knee": 3.0, "ankle": 6.0},
        "note": "2-D sagittal screening scores, not the validated 3-D indices.",
    }


def test_clinical_scores_fails_closed_when_the_backend_raises(monkeypatch) -> None:
    package = ModuleType("myogait")
    package.__path__ = []
    scores = ModuleType("myogait.scores")

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("optional backend unavailable")

    scores.gait_profile_score_2d = unavailable
    scores.sagittal_deviation_index = unavailable
    scores.movement_analysis_profile = unavailable
    monkeypatch.setitem(sys.modules, "myogait", package)
    monkeypatch.setitem(sys.modules, "myogait.scores", scores)

    assert clinical_scores({"summary": {}}) is None


def test_select_stratum_has_a_dependency_free_fallback(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "myogait.normative", None)

    assert select_stratum(12) == "pediatric"
    assert select_stratum(18) == "adult"
    assert select_stratum(65) == "elderly"
