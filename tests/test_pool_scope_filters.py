"""page_pool.render(mode="accuracy") is a real section filter (UX-02).

"accuracy" used to render the full page -- overview, condition comparison,
per-condition tabs -- just reordered ("mode is emphasis, not a filter").
For a scope named after one analysis that was misleading. It now shows the
aggregate vs-Vicon accuracy, the ICC validity/test-retest section and the
bundle export, then returns. This checks that against a paired video+C3D
fixture, so a regression that makes "accuracy" leaky shows up at once.
"""

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


def _paired_cohort_fixture() -> list[RunResult]:
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


def _run_with_scope(scope: str):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP_PY), default_timeout=60)
    app.run()
    app.session_state["nav_page"] = "Analysis"
    app.session_state["analysis_scope"] = scope
    app.session_state["pool_runs"] = _paired_cohort_fixture()
    app.run()
    assert not app.exception
    return app


_AGGREGATE_ACCURACY_SUBHEADER = "Accuracy vs Vicon — paired automatically by patient"


def test_accuracy_vs_c3d_shows_only_the_aggregate_accuracy():
    app = _run_with_scope("Accuracy vs C3D")

    subheaders = [s.value for s in app.subheader]
    assert _AGGREGATE_ACCURACY_SUBHEADER in subheaders
    assert "Conditions at a glance" not in subheaders


def test_one_group_still_shows_the_full_page():
    """The relocated "One group" (page_pool mode "single") keeps everything
    -- it is the general read, not a filter."""
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP_PY), default_timeout=60)
    app.run()
    app.session_state["nav_page"] = "Advanced"
    app.session_state["pool_runs"] = _paired_cohort_fixture()
    app.run()
    assert not app.exception

    subheaders = [s.value for s in app.subheader]
    assert "Conditions at a glance" in subheaders
    assert _AGGREGATE_ACCURACY_SUBHEADER in subheaders
