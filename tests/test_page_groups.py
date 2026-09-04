"""Advanced -> Groups -> Two groups (page_groups, plan B3).

Two independently imported, named groups; every shared parameter compared
with an adaptive test; a multiple-comparison warning; a visual-control
exclusion that keeps the recording in the group but drops it from the
statistics.
"""

from __future__ import annotations

from pathlib import Path

import pytest

APP_PY = Path(__file__).resolve().parent.parent / "app.py"


def _advanced(settings):
    pytest.importorskip("streamlit")
    pytest.importorskip("myogait")
    from streamlit.testing.v1 import AppTest

    import myogait_app.ui.group_sources as gs

    app = AppTest.from_file(str(APP_PY), default_timeout=240)
    app.run()
    # group_sources reads SETTINGS at call time to list jobs / resolve paths.
    gs.SETTINGS = settings
    app.session_state["nav_page"] = "Advanced"
    app.run()
    assert not app.exception
    return app


def _demo(gain: float):
    """Demo pivot with the vertical landmark excursion scaled about 0.5, so a
    group seeded with a different gain has visibly different joint ROM (else
    every recording is byte-identical and every difference test is degenerate).
    """
    from myogait_app.demo import make_demo_data

    data = make_demo_data()
    for frame in data["frames"]:
        for landmark in frame["landmarks"].values():
            landmark["y"] = 0.5 + (landmark["y"] - 0.5) * gain
    return data


def _seed_jobs(tmp_path):
    from myogait_app.jobs import JobManager
    from myogait_app.settings import Settings

    settings = Settings(workspace_root=tmp_path)
    manager = JobManager(settings)
    for i in range(3):
        manager.register_immediate(
            _demo(1.00 + 0.03 * i), f"a{i}.mp4", "mediapipe",
            study={"patient_id": f"A{i}", "condition": "control"},
        )
        manager.register_immediate(
            _demo(1.40 + 0.03 * i), f"b{i}.mp4", "mediapipe",
            study={"patient_id": f"B{i}", "condition": "patient"},
        )
    manager._pool.shutdown(wait=True)
    return settings


def _pick_group(app, key: str, tag: str) -> None:
    """Select every job whose history label carries ``-- <tag>`` into *key*."""
    picker = app.multiselect(key=key)
    for option in [o for o in picker.options if f"-- {tag}" in o]:
        app.multiselect(key=key).select(option)


def _compare(app):
    _pick_group(app, "groups_a_history", "A")
    _pick_group(app, "groups_b_history", "B")
    app.run()
    app.button(key="groups_go").click()
    app.run()
    assert not app.exception


def test_empty_state_asks_for_a_source_per_group(tmp_path):
    app = _advanced(_seed_jobs(tmp_path))

    names = {ti.value for ti in app.text_input}
    assert {"Group 1", "Group 2"} <= names
    assert any("press Compare" in i.value for i in app.info)


def test_compares_two_history_groups_with_a_multiple_comparison_warning(tmp_path):
    app = _advanced(_seed_jobs(tmp_path))
    _compare(app)

    assert "groups_two" in app.session_state
    captions = " ".join(c.value for c in app.caption)
    assert "Welch t" in captions and "Mann-Whitney U" in captions

    warnings = " ".join(w.value for w in app.warning)
    assert "multiple comparisons" in warnings and "Bonferroni" in warnings


def test_exclusion_keeps_the_recording_but_drops_it_from_stats(tmp_path):
    app = _advanced(_seed_jobs(tmp_path))
    _compare(app)

    stored = app.session_state["groups_two"]
    first_a = next(r for r in stored["a"] if r.ok)
    assert first_a.source_key  # a real per-recording id, not the shared "result.json"
    app.session_state["groups_excluded"] = [first_a.source_key]
    app.run()
    assert not app.exception

    header = " ".join(c.value for c in app.caption)
    assert "1 recording(s) excluded from the statistics" in header
    assert "2 recording(s), 2 patient(s)" in header  # group A: 3 imported, 1 excluded
