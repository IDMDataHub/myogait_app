"""Advanced -- the fullest analysis screen.

Everything downstream of a single trial's read: one patient over time, one
group's statistics, two groups compared, parameter sweeps, the full export
surface, accelerometry biomarkers and the method-validation benchmark. The
clinical path (New assessment -> Analysis) stays focused; the depth lives
here (audit action plan, chantier B). Every tab is an existing page,
rendered unchanged.

**One group / Two groups share one tab for now.** They read the same
loaded cohort and the same input widgets; ``page_pool.render`` uses fixed
widget keys, so rendering it twice in one script run would collide. An
inner switch picks the emphasis (one group's read vs the two-condition
comparison). The plan's full split -- two tabs, each with its own named
import zone and comparison statistics -- is the B2/B3 rebuild, separate
work with its own open questions.
"""

from __future__ import annotations

import streamlit as st

from ..settings import SETTINGS
from . import page_biomarkers, page_compare, page_export, page_longitudinal, page_pool
from .components import page_header

_ONE_GROUP = "One group"
_TWO_GROUPS = "Two groups"


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
    """One group vs Two groups: a switch, not two tabs -- see the module
    docstring for why. Renders ``page_pool`` exactly once per run."""
    choice = st.radio(
        "View", [_ONE_GROUP, _TWO_GROUPS], horizontal=True,
        key="advanced_group_view", label_visibility="collapsed",
    )
    st.caption(
        "**One group** reads a single cohort. **Two groups** leads with the "
        "condition-by-condition comparison. Both work off the cohort loaded "
        "below."
    )
    mode = "single" if choice == _ONE_GROUP else "compare"
    page_pool.render(show_header=False, mode=mode)
