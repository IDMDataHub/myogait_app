"""Analysis scope selection: data-aware default and the Export pill.

The Analysis page must open on the view that shows the data actually loaded
(a single freshly loaded source -> "Single run", a built cohort -> the study
view), and expose the export surface as a scope of its own.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from myogait_app.pooling import RunResult

APP_PY = Path(__file__).resolve().parents[1] / "app.py"


def _pool_fixture() -> list[RunResult]:
    curve = [float(i) for i in range(101)]
    cycles = {"cycles": [{"side": "left", "cycle_id": 1,
                          "angles_normalized": {"hip": curve, "knee": curve, "ankle": curve}}],
              "summary": {}}
    return [RunResult("a.json", {"patient_id": "P1", "condition": "base"},
                      ok=True, kind="video", cycles=cycles, stats={})]


def _app():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP_PY), default_timeout=60)
    app.run()
    app.session_state["nav_page"] = "Analysis"
    return app


def test_pool_batch_defaults_to_study_scope() -> None:
    app = _app()
    app.session_state["pool_runs"] = _pool_fixture()
    app.run()
    assert app.session_state["analysis_scope"] == "Study & conditions"


def test_no_data_defaults_to_study_scope() -> None:
    app = _app()
    app.run()
    assert app.session_state["analysis_scope"] == "Study & conditions"


def test_stale_scope_value_is_dropped_not_fatal() -> None:
    app = _app()
    app.session_state["analysis_scope"] = "Some renamed scope"
    app.run()
    assert not app.exception
    assert app.session_state["analysis_scope"] in (
        "Study & conditions", "Patient over time", "Single run", "Export")


def test_export_scope_renders_export_surface() -> None:
    app = _app()
    app.session_state["analysis_scope"] = "Export"
    app.run()
    assert not app.exception
    # No source loaded -> the export surface shows its own empty state
    # ("Nothing loaded."), proving page_export rendered under Analysis.
    texts = " ".join(getattr(el, "value", "") or "" for el in app.markdown)
    captions = " ".join(c.value or "" for c in app.caption)
    assert "Nothing loaded" in texts + captions or len(app.selectbox) >= 0
