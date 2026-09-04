"""One patient over time and the group views live on Advanced now, not
Analysis (audit action plan, chantier B).

Analysis keeps the clinical read (Trial Explorer, Markerbased vs
Monocular, Accuracy vs C3D, Export); Advanced is the fullest analysis
screen. This checks the relocation actually happened -- the tabs exist on
Advanced, the scopes are gone from Analysis -- and that rendering
Advanced (which now calls page_pool twice via the Groups switch) does not
raise a duplicate-widget error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

APP_PY = Path(__file__).resolve().parent.parent / "app.py"


def _run(nav_page: str):
    pytest.importorskip("streamlit")
    pytest.importorskip("myogait")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP_PY), default_timeout=90)
    app.run()
    app.session_state["nav_page"] = nav_page
    app.run()
    assert not app.exception
    return app


def test_advanced_has_the_relocated_analysis_tabs():
    app = _run("Advanced")
    labels = [t.label for t in app.get("tab")]
    assert "Patient over time" in labels
    assert "Groups" in labels
    assert "Comparator" in labels
    assert "Export" in labels


def test_advanced_group_switch_offers_one_and_two_groups():
    app = _run("Advanced")
    radio = app.radio(key="advanced_group_view")
    assert set(radio.options) == {"One group", "Two groups"}


def test_analysis_no_longer_offers_the_departed_scopes():
    _run("Analysis")  # renders without error
    # st.pills renders its options as buttons/markdown; assert via the
    # scope module's own list, which drives the widget.
    from myogait_app.ui import page_analysis

    assert page_analysis._SCOPES == (
        "Trial Explorer", "Markerbased vs Monocular", "Accuracy vs C3D", "Export",
    )
    for gone in ("One group", "Two groups", "Patient over time"):
        assert gone not in page_analysis._SCOPES


def test_switching_the_groups_view_does_not_raise():
    app = _run("Advanced")
    app.radio(key="advanced_group_view").set_value("Two groups").run()
    assert not app.exception
    app.radio(key="advanced_group_view").set_value("One group").run()
    assert not app.exception
