"""Analysis -> "Markerbased vs Monocular": one video+C3D pair, every
parameter, monocular vs marker-based together (Solution A).

Driven by ready video+C3D pairs from job history, not the loaded cohort.
With no pair it explains the empty case; with one it runs both sides and
renders the five comparison tabs without raising.
"""

from __future__ import annotations

from pathlib import Path

import pytest

APP_PY = Path(__file__).resolve().parent.parent / "app.py"


def _analysis_markerbased(settings=None):
    pytest.importorskip("streamlit")
    pytest.importorskip("myogait")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP_PY), default_timeout=120)
    app.run()
    app.session_state["nav_page"] = "Analysis"
    app.session_state["analysis_scope"] = "Markerbased vs Monocular"
    app.run()
    assert not app.exception
    return app


def test_empty_state_when_no_pair_exists(tmp_path, monkeypatch):
    from myogait_app.settings import Settings

    settings = Settings(workspace_root=tmp_path)
    monkeypatch.setattr("myogait_app.ui.page_export.SETTINGS", settings)

    app = _analysis_markerbased()
    assert any("No ready video+C3D pair" in i.value for i in app.info)


def test_runs_both_sides_and_renders_the_comparison_tabs(tmp_path, monkeypatch):
    from myogait_app.demo import make_demo_data
    from myogait_app.jobs import JobManager
    from myogait_app.settings import Settings

    settings = Settings(workspace_root=tmp_path)
    manager = JobManager(settings)
    study = {"patient_id": "P05", "condition": "walk"}
    manager.register_immediate(make_demo_data(), "video.mp4", "mediapipe", study=study)
    manager.register_immediate(make_demo_data(), "markers.c3d", "c3d-import", study=study)
    manager._pool.shutdown(wait=True)
    monkeypatch.setattr("myogait_app.ui.page_export.SETTINGS", settings)
    monkeypatch.setattr("myogait_app.ui.page_markerbased.SETTINGS", settings)

    app = _analysis_markerbased()

    picker = app.selectbox(key="mb_pair")
    assert picker.options == ["P05 / walk"]
    labels = [t.label for t in app.get("tab")]
    for tab in ("Kinematics", "Cycles", "Spatio-temporal", "Range of motion", "Accelerometry"):
        assert tab in labels
