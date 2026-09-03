"""page_export.render(mode=...) — the tab set per mode is load-bearing.

[A4] slimmed the Analysis export route to data / figures / native PDF
report while Advanced keeps the full surface. [B7] of the action plan is
the non-regression guard for that split: a change to page_export must not
silently drop an Advanced tab or leak an Advanced-only one into Analysis.
"""

from __future__ import annotations

from pathlib import Path

import pytest

APP_PY = Path(__file__).resolve().parent.parent / "app.py"


def _export_page(nav_page: str, analysis_scope: str | None = None):
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


def _tab_labels(app) -> list[str]:
    return [t.label for t in app.get("tab")]


def test_analysis_export_keeps_only_data_figures_report():
    app = _export_page("Analysis", "Export")
    keys = {b.key for b in app.button}
    labels = _tab_labels(app)
    assert "rep_go" in keys, "native PDF report must stay on the Analysis route"
    assert "mocaprep_go" not in keys, "MoCap report is Advanced-only"
    assert "Video" not in labels and "Video report" not in labels
    assert "MoCap report" not in labels
    assert "Export a cohort of video+C3D pairs as one file" not in [
        e.label for e in app.expander
    ]


def test_advanced_export_keeps_the_full_surface():
    app = _export_page("Advanced")
    keys = {b.key for b in app.button}
    labels = _tab_labels(app)
    assert "rep_go" in keys and "mocaprep_go" in keys
    for tab in ("Data files", "Figures", "Video", "PDF report", "Video report", "MoCap report"):
        assert tab in labels, f"Advanced Export lost its {tab!r} tab"
    assert "Export a cohort of video+C3D pairs as one file" in [
        e.label for e in app.expander
    ]
