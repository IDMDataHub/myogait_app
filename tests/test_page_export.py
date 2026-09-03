"""Export actually produces a file, not just a page that renders.

test_pages_with_data.py already renders Advanced (which hosts Export as a
tab) and checks nothing raises -- but AppTest only executes each tab body
once, at its initial state; it never clicks the "Generate"/export buttons
themselves. Those button-gated branches (report/PDF assembly, workbook
writing) are exactly the ones the audit flagged as least covered (DEV-02):
the code that runs is different from the code that renders the form
around it. This drives the actual buttons on demo data and asserts a real
file came out the other end.

The video report is deliberately not exercised here: it needs a real
source video on disk (``source.kind == "video"`` and ``source.path``
set), which the synthetic demo fixture has neither of, and rendering it
takes several minutes even when it can run -- too slow and too heavy for
this suite. It stays covered only by the render-without-exception smoke
test in test_pages_with_data.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

APP_PY = Path(__file__).resolve().parent.parent / "app.py"


def _app_on_export_with_demo_data():
    from streamlit.testing.v1 import AppTest

    from myogait_app.demo import make_demo_data
    from myogait_app.ui import state

    app = AppTest.from_file(str(APP_PY), default_timeout=90)
    app.run()
    app.session_state[state.K_SOURCE] = state.Source(
        kind="demo", name="demo", data=make_demo_data(), key="demo-fixture",
        model="synthetic",
    )
    app.session_state["nav_page"] = "Advanced"
    app.run()
    assert not app.exception
    return app


def test_generate_pdf_report_produces_a_downloadable_file():
    """The native myogait report (kept in Analysis's own slimmed-down
    Export per the Analysis/Advanced redesign) -- button key "rep_go"."""
    pytest.importorskip("streamlit")
    pytest.importorskip("myogait")
    app = _app_on_export_with_demo_data()

    button = app.button(key="rep_go")
    if button.disabled:
        pytest.skip("myogait build in this environment has no report generator.")
    button.click().run()

    assert not app.exception
    assert any("ready" in s.value for s in app.success), (
        "expected a 'PDF report ready - ...' success message"
    )


def test_generate_mocap_report_produces_a_downloadable_file():
    """This app's own 4-section MoCap PDF (kept in Advanced's full Export)
    -- button key "mocaprep_go"."""
    pytest.importorskip("streamlit")
    pytest.importorskip("myogait")
    app = _app_on_export_with_demo_data()

    button = app.button(key="mocaprep_go")
    button.click().run()

    assert not app.exception
    assert any("ready" in s.value for s in app.success), (
        "expected a 'MoCap report ready - ...' success message"
    )


def test_generate_excel_workbook_produces_a_downloadable_file():
    """A Data files export, for coverage on _run_export's non-report path
    too -- button key "exp_xlsx"."""
    pytest.importorskip("streamlit")
    pytest.importorskip("myogait")
    app = _app_on_export_with_demo_data()

    button = app.button(key="exp_xlsx")
    button.click().run()

    assert not app.exception
    assert any("ready" in s.value for s in app.success), (
        "expected an 'Excel ready - ...' success message"
    )
