"""Advanced -- the fullest analysis screen.

Everything downstream of a single trial's read: one patient over time, one
group's statistics, two groups compared, parameter sweeps, the full export
surface, accelerometry biomarkers and the method-validation benchmark. The
clinical path (New assessment -> Analysis) stays focused; the depth lives
here (audit action plan, chantier B). Every tab is an existing page,
rendered unchanged.

**Groups is two sub-tabs.** *One group* (``page_pool`` mode ``"single"``)
reads a single loaded cohort; *Two groups* (``page_groups``) imports two
named groups independently and compares them (audit action plan, B2/B3).
``page_pool.render`` is called once per run (only inside *One group*), so
its fixed widget keys no longer collide -- the reason the two used to
share an inner switch.
"""

from __future__ import annotations

import streamlit as st

from ..settings import SETTINGS
from . import (
    page_biomarkers,
    page_compare,
    page_export,
    page_groups,
    page_longitudinal,
    page_pool,
)
from .components import page_header


def render() -> None:
    page_header(
        "Advanced",
        "The deep dive: one patient over time, one group's statistics, two "
        "groups compared, parameter sweeps, the full export surface, "
        "accelerometry biomarkers, and method validation against Vicon.",
    )

    labels = [
        "Patient over time", "Groups", "Comparator", "Accelerometry", "Export",
    ]
    if SETTINGS.enable_experimental:
        labels.append("Method validation")

    # The Advanced folio is enough; the pages in the tabs must not add theirs.
    st.session_state["_embedded_header"] = True
    tabs = st.tabs(labels)
    with tabs[0]:
        page_longitudinal.render()
    with tabs[1]:
        _groups_tab()
    with tabs[2]:
        page_compare.render()
    with tabs[3]:
        page_biomarkers.render()
    with tabs[4]:
        page_export.render()
    if SETTINGS.enable_experimental:
        from . import page_experimental

        with tabs[5]:
            page_experimental.render()


def _groups_tab() -> None:
    """One group vs Two groups as two real sub-tabs. ``page_pool.render`` is
    called once (One group only), so its fixed widget keys don't collide."""
    one_group, two_groups = st.tabs(["One group", "Two groups"])
    with one_group:
        st.caption(
            "Descriptive read of a single loaded cohort: pooled curves, ROM, "
            "stance/swing and per-parameter descriptive statistics, per "
            "condition. Load the cohort below."
        )
        page_pool.render(show_header=False, mode="single")
    with two_groups:
        page_groups.render()
