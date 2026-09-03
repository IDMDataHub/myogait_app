"""page_export.render(scope=...) actually hides tabs, not just widens Advanced.

Analysis's Export used to be the exact same page_export.render() as
Advanced's, full surface included -- video export, the animated video
report, the MoCap PDF, alongside the native PDF report and data files.
The audit (UX-06) noted the export surface was one of the places the
"simple vs advanced" split existed in name only. This checks scope="light"
(Analysis) actually drops the Advanced-only tabs and adds the group-
staging tool, while scope="full" (Advanced, the default) is unchanged.
"""

from __future__ import annotations

from pathlib import Path

import pytest

APP_PY = Path(__file__).resolve().parent.parent / "app.py"


def _app_with_demo_data(nav_page: str, analysis_scope: str | None = None):
    pytest.importorskip("streamlit")
    pytest.importorskip("myogait")
    from streamlit.testing.v1 import AppTest

    from myogait_app.demo import make_demo_data
    from myogait_app.ui import state

    app = AppTest.from_file(str(APP_PY), default_timeout=90)
    app.run()
    app.session_state[state.K_SOURCE] = state.Source(
        kind="demo", name="demo", data=make_demo_data(), key="demo-fixture",
        model="synthetic",
    )
    app.session_state["nav_page"] = nav_page
    if analysis_scope is not None:
        app.session_state["analysis_scope"] = analysis_scope
    app.run()
    assert not app.exception
    return app


def test_analysis_export_hides_video_and_mocap_tabs_and_offers_group_staging():
    app = _app_with_demo_data("Analysis", "Export")

    button_keys = {b.key for b in app.button}
    assert "rep_go" in button_keys, "the native PDF report button should still be there"
    assert "mocaprep_go" not in button_keys, "MoCap report is Advanced-only now"
    assert "vidrep_go" not in button_keys, "Video report is Advanced-only now"

    expander_labels = [e.label for e in app.expander]
    assert "Prepare a named group for Advanced" in expander_labels


def test_advanced_export_still_has_the_full_surface():
    app = _app_with_demo_data("Advanced")

    button_keys = {b.key for b in app.button}
    assert "rep_go" in button_keys
    assert "mocaprep_go" in button_keys

    expander_labels = [e.label for e in app.expander]
    assert "Prepare a named group for Advanced" not in expander_labels


def _cohort_fixture():
    from myogait_app.pooling import RunResult

    curve = [float(i) for i in range(101)]
    cycles = {
        "cycles": [
            {"side": "left", "cycle_id": 1, "angles_normalized": {
                "hip": curve, "knee": curve, "ankle": curve}},
            {"side": "right", "cycle_id": 2, "angles_normalized": {
                "hip": curve, "knee": curve, "ankle": curve}},
        ],
        "summary": {},
    }
    study = {"patient_id": "P01", "run": "v1", "condition": "baseline"}
    stats = {"spatiotemporal": {"cadence_steps_per_min": 105.0}}
    return [
        RunResult("a.json", study, ok=True, kind="video", duration_s=2.0,
                  cycles=cycles, stats=stats),
        RunResult("b.json", dict(study, run="v2"), ok=True, kind="video", duration_s=2.0,
                  cycles=cycles, stats=stats),
    ]


def test_analysis_export_offers_the_cohort_bundle_when_a_cohort_is_loaded():
    """A cohort built in another Analysis scope must be exportable from
    Export too -- it used to dead-end on "Nothing loaded" because Export
    only ever looked at the single-recording store."""
    pytest.importorskip("streamlit")
    pytest.importorskip("myogait")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP_PY), default_timeout=90)
    app.run()
    # No K_SOURCE -- only a cohort is loaded.
    app.session_state["nav_page"] = "Analysis"
    app.session_state["analysis_scope"] = "Export"
    app.session_state["pool_runs"] = _cohort_fixture()
    app.run()

    assert not app.exception
    expander_labels = [e.label for e in app.expander]
    assert "Export cohort bundle (zip)" in expander_labels
    assert "Prepare a named group for Advanced" in expander_labels
    assert "bundle_go" in {b.key for b in app.button}
