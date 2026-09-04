"""Advanced Export's "cohort of video+C3D pairs as one file" (added
2026-09-03, per user request while merging the audit's action plan): a
ready pair from job history gets both sides run through the current
pipeline config and combined into one JSON (full fidelity) or Excel
(summary) file. This drives the JSON path end to end -- the Excel path
reuses the same _combine_pair result, so a JSON-path regression already
covers most of what could break for either format.
"""

from __future__ import annotations

from pathlib import Path

import pytest

APP_PY = Path(__file__).resolve().parent.parent / "app.py"


def test_combined_json_export_succeeds_for_a_ready_pair(tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    pytest.importorskip("myogait")
    from streamlit.testing.v1 import AppTest

    from myogait_app.demo import make_demo_data
    from myogait_app.jobs import JobManager
    from myogait_app.settings import Settings
    from myogait_app.ui import state

    settings = Settings(workspace_root=tmp_path)
    manager = JobManager(settings)
    study = {"patient_id": "P07", "condition": "walk"}
    manager.register_immediate(make_demo_data(), "video.mp4", "mediapipe", study=study)
    manager.register_immediate(make_demo_data(), "markers.c3d", "c3d-import", study=study)
    manager._pool.shutdown(wait=True)
    monkeypatch.setattr("myogait_app.ui.page_export.SETTINGS", settings)

    app = AppTest.from_file(str(APP_PY), default_timeout=90)
    app.run()
    app.session_state[state.K_SOURCE] = state.Source(
        kind="demo", name="demo", data=make_demo_data(), key="demo-fixture",
        model="synthetic",
    )
    app.session_state["nav_page"] = "Advanced"
    app.run()
    assert not app.exception

    picker = app.multiselect(key="combined_export_pairs")
    assert picker.options == ["P07 / walk"]
    picker.set_value(picker.options).run()
    app.button(key="combined_export_go").click().run()

    assert not app.exception
    assert any("Combined pairs (JSON) ready" in s.value for s in app.success)


def test_combined_export_section_shows_with_no_recording_loaded(tmp_path, monkeypatch):
    """The section drives off job history, not the loaded recording, so a
    user who has only built a cohort must still reach it -- it used to sit
    behind Export's "nothing loaded" guard and was unreachable."""
    pytest.importorskip("streamlit")
    pytest.importorskip("myogait")
    from streamlit.testing.v1 import AppTest

    from myogait_app.demo import make_demo_data
    from myogait_app.jobs import JobManager
    from myogait_app.settings import Settings

    settings = Settings(workspace_root=tmp_path)
    manager = JobManager(settings)
    study = {"patient_id": "P07", "condition": "walk"}
    manager.register_immediate(make_demo_data(), "video.mp4", "mediapipe", study=study)
    manager.register_immediate(make_demo_data(), "markers.c3d", "c3d-import", study=study)
    manager._pool.shutdown(wait=True)
    monkeypatch.setattr("myogait_app.ui.page_export.SETTINGS", settings)

    app = AppTest.from_file(str(APP_PY), default_timeout=90)
    app.run()
    # No state.K_SOURCE set -- nothing loaded.
    app.session_state["nav_page"] = "Advanced"
    app.run()

    assert not app.exception
    assert app.multiselect(key="combined_export_pairs").options == ["P07 / walk"]
