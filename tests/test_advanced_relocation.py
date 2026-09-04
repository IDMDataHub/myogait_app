"""One patient over time and the group views live on Advanced now, not
Analysis (audit action plan, chantier B).

Analysis keeps the clinical read (Trial Explorer, Markerbased vs
Monocular, Accuracy vs C3D, Export); Advanced is the fullest analysis
screen. This checks the relocation actually happened -- the tabs exist on
Advanced, the scopes are gone from Analysis -- and that Advanced's Groups
tab (now two real sub-tabs, One group + Two groups, with page_pool
rendered once) does not raise a duplicate-widget error.
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


def test_advanced_groups_tab_has_one_and_two_group_subtabs():
    app = _run("Advanced")
    labels = [t.label for t in app.get("tab")]
    assert "One group" in labels
    assert "Two groups" in labels


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


def test_two_groups_subtab_renders_its_import_zones():
    app = _run("Advanced")
    # Two named import zones, each with a name field defaulting to Group 1/2.
    name_values = {ti.value for ti in app.text_input}
    assert {"Group 1", "Group 2"} <= name_values
    infos = " ".join(i.value for i in app.info)
    assert "press Compare" in infos
