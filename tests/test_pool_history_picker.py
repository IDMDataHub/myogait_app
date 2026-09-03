"""The "completed video-C3D pairs from history" picker on Analysis's
Accuracy vs C3D scope (audit UX-04): building a cohort to check accuracy
used to mean re-uploading the same JSONs by hand, or a detour through New
assessment -> Recent jobs. A ready (video + C3D) pair should be selectable
straight from where the cohort is built.
"""

from __future__ import annotations

from pathlib import Path

import pytest

APP_PY = Path(__file__).resolve().parent.parent / "app.py"


def test_history_pair_picker_appears_with_a_ready_pair(tmp_path, monkeypatch):
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

    # page_pool._select_history_pairs resolves SETTINGS from its own module
    # namespace, so patch it there for the picker inside the running app to
    # see the tmp_path jobs the fixture just registered.
    monkeypatch.setattr("myogait_app.ui.page_pool.SETTINGS", settings)

    app = AppTest.from_file(str(APP_PY), default_timeout=60)
    app.run()
    app.session_state["nav_page"] = "Analysis"
    app.session_state["analysis_scope"] = "Accuracy vs C3D"
    app.run()

    assert not app.exception
    picker = app.multiselect(key="pool_accuracy_history_pairs")
    assert picker.options == ["P03 / walk (2 recordings)"]


def test_history_pair_picker_absent_without_a_c3d(tmp_path, monkeypatch):
    """A video with no matching C3D import is not a pair -- the picker
    stays empty rather than offering a half-pair."""
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    from myogait_app.demo import make_demo_data
    from myogait_app.jobs import JobManager
    from myogait_app.settings import Settings

    settings = Settings(workspace_root=tmp_path)
    manager = JobManager(settings)
    manager.register_immediate(make_demo_data(), "video.mp4", "mediapipe",
                                study={"patient_id": "P03", "condition": "walk"})
    manager._pool.shutdown(wait=True)
    monkeypatch.setattr("myogait_app.ui.page_pool.SETTINGS", settings)

    app = AppTest.from_file(str(APP_PY), default_timeout=60)
    app.run()
    app.session_state["nav_page"] = "Analysis"
    app.session_state["analysis_scope"] = "Accuracy vs C3D"
    app.run()

    assert not app.exception
    assert not any(w.key == "pool_accuracy_history_pairs" for w in app.multiselect)
