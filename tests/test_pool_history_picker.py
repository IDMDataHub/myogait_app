"""The "paired recordings already in Recent jobs" picker on Analysis's
cohort scopes (audit UX-04): building a cohort to check accuracy used to
mean uploading the same JSONs again by hand, or a detour through New
assessment -> Recent jobs. A ready (video + C3D) pair should now be
selectable directly from where the cohort is built.
"""

from __future__ import annotations

from pathlib import Path

import pytest

APP_PY = Path(__file__).resolve().parent.parent / "app.py"


def test_paired_job_history_picker_appears_with_a_ready_pair(tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    from myogait_app.demo import make_demo_data
    from myogait_app.jobs import JobManager
    from myogait_app.settings import Settings

    settings = Settings(workspace_root=tmp_path)
    manager = JobManager(settings)
    data = make_demo_data()
    study = {"patient_id": "P03", "condition": "walk"}
    manager.register_immediate(data, "video.mp4", "mediapipe", study=study)
    manager.register_immediate(data, "markers.c3d", "c3d-import", study=study)
    manager._pool.shutdown(wait=True)

    # page_pool._paired_history_picker resolves SETTINGS from its own
    # module namespace (`from ..settings import SETTINGS`), not a fresh
    # lookup on myogait_app.settings each call -- patch it there so the
    # picker inside the running app lists jobs from the same tmp_path the
    # fixture jobs above were just registered into.
    monkeypatch.setattr("myogait_app.ui.page_pool.SETTINGS", settings)

    app = AppTest.from_file(str(APP_PY), default_timeout=60)
    app.run()
    app.session_state["nav_page"] = "Analysis"
    app.session_state["analysis_scope"] = "Accuracy vs C3D"
    app.run()

    assert not app.exception
    picker = app.multiselect(key="pool_history_pairs")
    assert picker.options == ["P03 / walk (2 file(s))"]
