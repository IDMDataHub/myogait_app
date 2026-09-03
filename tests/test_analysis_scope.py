"""Analysis scope selection: data-aware default, legacy remap, Export pill.

The Analysis page must open on the view that shows the data actually loaded
(a single freshly loaded source -> "Trial Explorer", a built cohort -> a
group view), survive scope labels stored by an older app version, and
expose the export surface as a scope of its own.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from myogait_app.pooling import RunResult

APP_PY = Path(__file__).resolve().parents[1] / "app.py"

SCOPES = ("Trial Explorer", "Markerbased vs Monocular", "Patient over time",
          "One group", "Two groups", "Accuracy vs C3D", "Export")


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


def test_pool_batch_defaults_to_group_scope() -> None:
    app = _app()
    app.session_state["pool_runs"] = _pool_fixture()
    app.run()
    assert app.session_state["analysis_scope"] == "One group"


def test_two_condition_batch_defaults_to_two_groups() -> None:
    app = _app()
    app.session_state["pool_runs"] = _pool_fixture(("pre", "post"))
    app.run()
    assert app.session_state["analysis_scope"] == "Two groups"


def test_no_data_defaults_to_group_scope() -> None:
    app = _app()
    app.run()
    assert app.session_state["analysis_scope"] == "One group"


def test_legacy_study_scope_is_remapped() -> None:
    app = _app()
    app.session_state["analysis_scope"] = "Study & conditions"
    app.run()
    assert not app.exception
    assert app.session_state["analysis_scope"] == "One group"


def test_legacy_single_run_scope_is_remapped_to_trial_explorer() -> None:
    """"Single run" was this scope's label before it was renamed "Trial
    Explorer" (UX-01) -- a session that stored the old label must not land
    on a scope that no longer exists."""
    app = _app()
    app.session_state["analysis_scope"] = "Single run"
    app.run()
    assert not app.exception
    assert app.session_state["analysis_scope"] == "Trial Explorer"


def test_stale_scope_value_is_dropped_not_fatal() -> None:
    app = _app()
    app.session_state["analysis_scope"] = "Some renamed scope"
    app.run()
    assert not app.exception
    assert app.session_state["analysis_scope"] in SCOPES


def test_export_scope_renders_without_error() -> None:
    app = _app()
    app.session_state["analysis_scope"] = "Export"
    app.run()
    assert not app.exception
    assert app.session_state["analysis_scope"] == "Export"
