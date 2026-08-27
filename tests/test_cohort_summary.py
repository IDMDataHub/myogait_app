"""Contracts for clinically meaningful values in a pooled Cohort summary."""

from __future__ import annotations

import numpy as np
import pytest

from myogait_app.pooling import RunResult, condition_summary


def _cycles() -> dict:
    curve = np.linspace(0.0, 30.0, 101).tolist()
    return {
        "cycles": [
            {"side": "left", "cycle_id": 1, "angles_normalized": {
                "hip": curve, "knee": curve, "ankle": curve,
            }},
            {"side": "right", "cycle_id": 2, "angles_normalized": {
                "hip": curve, "knee": curve, "ankle": curve,
            }},
        ],
        "summary": {},
    }


def _run(*, step_length: dict | None, age: float | None = None) -> RunResult:
    study = {"condition": "baseline", "patient_id": "P01", "run": "R01"}
    if age is not None:
        study["age"] = age
    stats = {"spatiotemporal": {"cadence_steps_per_min": 100.0}}
    if step_length is not None:
        stats["step_length"] = step_length
    return RunResult("P01_R01", study, ok=True, cycles=_cycles(), stats=stats)


def test_condition_summary_surfaces_only_calibrated_metric_step_length(monkeypatch) -> None:
    """The Cohort read-out must never label a normalized length as metres."""
    monkeypatch.setattr("myogait_app.pooling.clinical_scores", lambda *_args, **_kw: None)
    calibrated = _run(step_length={
        "unit": "m", "step_length_left": 0.60, "step_length_right": 0.70,
    })
    normalized = _run(step_length={
        "unit": "body_height", "step_length_left": 0.3, "step_length_right": 0.4,
    })

    summary = condition_summary([calibrated, normalized])

    assert summary["step_length_m"] == pytest.approx(0.65)
    assert "step_length" not in summary["spatiotemporal"]


def test_condition_summary_hides_step_length_without_metric_calibration(monkeypatch) -> None:
    monkeypatch.setattr("myogait_app.pooling.clinical_scores", lambda *_args, **_kw: None)

    summary = condition_summary([_run(step_length={
        "unit": "normalized", "step_length_left": 0.4, "step_length_right": 0.5,
    })])

    assert summary["step_length_m"] is None


def test_condition_summary_ignores_non_finite_clinical_measurements(monkeypatch) -> None:
    monkeypatch.setattr("myogait_app.pooling.clinical_scores", lambda *_args, **_kw: None)
    usable = _run(step_length={
        "unit": "m", "step_length_left": 0.60, "step_length_right": 0.70,
    })
    invalid = _run(step_length={
        "unit": "m", "step_length_left": float("nan"), "step_length_right": float("inf"),
    })
    invalid.stats["spatiotemporal"]["cadence_steps_per_min"] = float("nan")

    summary = condition_summary([usable, invalid])

    assert summary["step_length_m"] == pytest.approx(0.65)
    assert summary["spatiotemporal"]["cadence_steps_per_min"] == pytest.approx(100.0)


def test_condition_summary_drops_implausible_metric_step_lengths(monkeypatch) -> None:
    monkeypatch.setattr("myogait_app.pooling.clinical_scores", lambda *_args, **_kw: None)
    plausible = _run(step_length={
        "unit": "m", "step_length_left": 0.20, "step_length_right": 1.20,
    })
    implausible = _run(step_length={
        # 0.02 m is below the 0.05 m floor (lowered from 0.2 for pathological
        # gait) and 12.0 m is above the 1.2 m ceiling -> both dropped.
        "unit": "m", "step_length_left": 0.02, "step_length_right": 12.0,
    })

    summary = condition_summary([plausible, implausible])

    assert summary["step_length_m"] == pytest.approx(0.70)


def test_condition_summary_selects_an_age_matched_clinical_stratum(monkeypatch) -> None:
    seen: dict[str, str] = {}

    def fake_scores(_cycles: dict, *, stratum: str) -> dict:
        seen["stratum"] = stratum
        return {"gps_2d_overall": 4.0}

    monkeypatch.setattr("myogait_app.pooling.clinical_scores", fake_scores)

    summary = condition_summary([_run(step_length=None, age=12)])

    assert summary["stratum"] == "pediatric"
    assert seen["stratum"] == "pediatric"
    assert summary["scores"] == {"gps_2d_overall": 4.0}
