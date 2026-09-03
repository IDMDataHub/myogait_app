"""page_pool.render(mode=...) actually filters its sections now (UX-02).

Before this, every mode rendered the full page -- overview, condition
comparison, accuracy -- just reordered ("mode is emphasis, not a filter",
the render() docstring's own former wording). "Accuracy vs C3D" showing
the same general-browsing tables as every other scope was one of the
audit's clearest examples of a menu distinction that did not exist in
what actually rendered. This checks the two new/changed modes directly
against the same paired video+C3D fixture, so a regression that makes
"accuracy" leaky (or "markerbased" a no-op) shows up immediately.
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
    """A paired markerless-video and C3D/reference trial for one visit --
    the exact shape that makes both the general-overview material and the
    vs-Vicon accuracy material available at once, so a mode that leaks the
    wrong section is actually observable."""
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


#: _overall_accuracy's own subheader -- the cross-patient, cross-condition
#: aggregate accuracy rollup. Distinct from _accuracy_section's per-
#: condition accuracy subsection (inside each condition's own tab), which
#: legitimately still shows in both modes below as part of "everything
#: about this one condition" -- the aggregate rollup is what "Accuracy vs
#: C3D" now exclusively owns.
_AGGREGATE_ACCURACY_SUBHEADER = "Accuracy vs Vicon — paired automatically by patient"


def test_markerbased_vs_monocular_shows_the_overview_not_the_aggregate_accuracy():
    app = _run_with_scope("Markerbased vs Monocular")

    subheaders = [s.value for s in app.subheader]
    assert "Conditions at a glance" in subheaders
    assert _AGGREGATE_ACCURACY_SUBHEADER not in subheaders


def test_accuracy_vs_c3d_shows_only_the_aggregate_accuracy():
    app = _run_with_scope("Accuracy vs C3D")

    subheaders = [s.value for s in app.subheader]
    assert _AGGREGATE_ACCURACY_SUBHEADER in subheaders
    assert "Conditions at a glance" not in subheaders
