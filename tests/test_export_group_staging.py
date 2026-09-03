"""The named-group staging tool on Analysis's Export (scope="light").

Producing half of the Phase 3 bridge: pick finished jobs, name the set,
save it. Nothing reads these groups back yet (Advanced's Patient over
time / Two groups rebuild is separate, later work) -- this only checks
that saving and removing a group actually round-trips through session
state, since a regression here would silently strand this Phase 2 feature
half-built before Phase 3 ever gets to consume it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

APP_PY = Path(__file__).resolve().parent.parent / "app.py"


def test_saving_and_removing_a_named_group_round_trips_through_session_state(tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    pytest.importorskip("myogait")
    from streamlit.testing.v1 import AppTest

    from myogait_app.demo import make_demo_data
    from myogait_app.jobs import JobManager
    from myogait_app.settings import Settings
    from myogait_app.ui import state

    settings = Settings(workspace_root=tmp_path)
    manager = JobManager(settings)
    manager.register_immediate(make_demo_data(), "video.mp4", "mediapipe",
                                study={"patient_id": "P09", "condition": "walk"})
    manager._pool.shutdown(wait=True)
    monkeypatch.setattr("myogait_app.ui.page_export.SETTINGS", settings)

    app = AppTest.from_file(str(APP_PY), default_timeout=90)
    app.run()
    app.session_state[state.K_SOURCE] = state.Source(
        kind="demo", name="demo", data=make_demo_data(), key="demo-fixture",
        model="synthetic",
    )
    app.session_state["nav_page"] = "Analysis"
    app.session_state["analysis_scope"] = "Export"
    app.run()
    assert not app.exception

    app.multiselect(key="group_staging_picks").set_value(
        [t for t in app.multiselect(key="group_staging_picks").options]
    ).run()
    app.text_input(key="group_staging_name").set_value("Suivi Patient 009").run()
    app.button(key="group_staging_save").click().run()

    assert not app.exception
    assert app.session_state["_named_job_groups"] == {
        "Suivi Patient 009": app.multiselect(key="group_staging_picks").value
    }
    assert any("Suivi Patient 009" in c.value for c in app.caption)

    app.button(key="group_staging_remove_Suivi Patient 009").click().run()

    assert not app.exception
    assert "Suivi Patient 009" not in app.session_state["_named_job_groups"]


def test_group_staging_shows_with_no_recording_loaded(tmp_path, monkeypatch):
    """It only needs finished jobs, not a loaded recording -- it used to
    sit behind Analysis Export's "nothing loaded" guard, so a user who
    had built a cohort but loaded no single source could not reach it."""
    pytest.importorskip("streamlit")
    pytest.importorskip("myogait")
    from streamlit.testing.v1 import AppTest

    from myogait_app.demo import make_demo_data
    from myogait_app.jobs import JobManager
    from myogait_app.settings import Settings

    settings = Settings(workspace_root=tmp_path)
    manager = JobManager(settings)
    manager.register_immediate(make_demo_data(), "video.mp4", "mediapipe",
                                study={"patient_id": "P09", "condition": "walk"})
    manager._pool.shutdown(wait=True)
    monkeypatch.setattr("myogait_app.ui.page_export.SETTINGS", settings)

    app = AppTest.from_file(str(APP_PY), default_timeout=90)
    app.run()
    # No state.K_SOURCE set -- nothing loaded.
    app.session_state["nav_page"] = "Analysis"
    app.session_state["analysis_scope"] = "Export"
    app.run()

    assert not app.exception
    assert len(app.multiselect(key="group_staging_picks").options) == 1
