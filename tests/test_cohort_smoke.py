"""Functional smoke test for rendering a populated Cohort tab."""

from __future__ import annotations

from pathlib import Path

import pytest

from myogait_app.pooling import RunResult


APP_PY = Path(__file__).resolve().parents[1] / "app.py"


def _cycles() -> dict:
    curve = [float(i) for i in range(101)]
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


def _cohort_fixture() -> list[RunResult]:
    """A paired markerless-video and C3D/reference trial for one visit."""
    study = {
        "patient_id": "P01", "run": "visit-01", "condition": "baseline",
        "height_m": 1.75, "age": 42,
    }
    stats = {
        "spatiotemporal": {"cadence_steps_per_min": 105.0},
        "step_length": {"unit": "m", "step_length_left": 0.62, "step_length_right": 0.64},
    }
    return [
        RunResult("P01_visit-01_video.json", study, ok=True, kind="video", duration_s=2.0,
                  cycles=_cycles(), stats=stats),
        RunResult("P01_visit-01_reference.json", study, ok=True, kind="vicon", duration_s=2.0,
                  cycles=_cycles(), stats=stats),
    ]


def test_cohort_tab_renders_a_paired_video_and_reference_trial() -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    # Generous timeout: the themed app injects its identity + background on
    # every run and the cohort tab runs a small pipeline, well over the 3 s
    # AppTest default on a cold import.
    app = AppTest.from_file(str(APP_PY), default_timeout=60)
    app.run()
    app.session_state["pool_runs"] = _cohort_fixture()
    app.run()

    assert not app.exception
    assert any(metric.label == "Step length" for metric in app.metric)
