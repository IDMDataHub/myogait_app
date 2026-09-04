"""Analysis scope selection after the Advanced relocation.

Analysis is now four scopes: Trial Explorer, Markerbased vs Monocular,
Accuracy vs C3D, Export. "One group" / "Two groups" / "Patient over time"
moved to Advanced tabs. The page must open on the view that matches the
data actually loaded, survive scope labels stored by an older app version
(including the three that left), and expose the export surface as a scope
of its own.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from myogait_app.pooling import RunResult

APP_PY = Path(__file__).resolve().parents[1] / "app.py"

SCOPES = ("Trial Explorer", "Markerbased vs Monocular", "Accuracy vs C3D", "Export")
DEPARTED = ("One group", "Two groups", "Patient over time", "Study & conditions")


def _pool_fixture(conditions=("base",)) -> list[RunResult]:
    curve = [float(i) for i in range(101)]
    cycles = {"cycles": [{"side": "left", "cycle_id": 1,
                          "angles_normalized": {"hip": curve, "knee": curve, "ankle": curve}}],
              "summary": {}}
    return [
        RunResult(f"{cond}_{i}.json", {"patient_id": f"P{i}", "condition": cond},
                  ok=True, kind="video", cycles=cycles, stats={})
        for i, cond in enumerate(conditions)
    ]


def _app():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP_PY), default_timeout=60)
    app.run()
    app.session_state["nav_page"] = "Analysis"
    return app


def test_loaded_cohort_defaults_to_markerbased_scope() -> None:
    app = _app()
    app.session_state["pool_runs"] = _pool_fixture()
    app.run()
    assert app.session_state["analysis_scope"] == "Markerbased vs Monocular"


def test_multi_condition_cohort_also_defaults_to_markerbased() -> None:
    app = _app()
    app.session_state["pool_runs"] = _pool_fixture(("pre", "post"))
    app.run()
    assert app.session_state["analysis_scope"] == "Markerbased vs Monocular"


def test_no_data_defaults_to_trial_explorer() -> None:
    app = _app()
    app.run()
    assert app.session_state["analysis_scope"] == "Trial Explorer"


@pytest.mark.parametrize("stale", DEPARTED)
def test_a_departed_scope_value_is_dropped_not_fatal(stale) -> None:
    app = _app()
    app.session_state["analysis_scope"] = stale
    app.run()
    assert not app.exception
    assert app.session_state["analysis_scope"] in SCOPES


def test_stale_scope_value_is_dropped_not_fatal() -> None:
    app = _app()
    app.session_state["analysis_scope"] = "Some renamed scope"
    app.run()
    assert not app.exception
    assert app.session_state["analysis_scope"] in SCOPES


def test_legacy_single_run_label_still_maps_to_trial_explorer() -> None:
    app = _app()
    app.session_state["analysis_scope"] = "Single run"
    app.run()
    assert not app.exception
    assert app.session_state["analysis_scope"] == "Trial Explorer"


def test_export_scope_renders_without_error() -> None:
    app = _app()
    app.session_state["analysis_scope"] = "Export"
    app.run()
    assert not app.exception
    assert app.session_state["analysis_scope"] == "Export"
