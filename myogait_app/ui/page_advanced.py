"""Advanced -- research tools, kept off the clinical path.

Parameter sweeps, exports and the method-validation benchmark live here,
so New assessment and Analysis stay focused on the clinical read. Single-
recording pipeline tuning itself is Analysis's "Trial Explorer" scope, not
a tab here -- it used to be duplicated in both places (the exact same
page_pipeline.render()), which the audit flagged as a confusing doubled
route (UX-01); it now lives only under Analysis. Every remaining tab is an
existing page, rendered unchanged.
"""

from __future__ import annotations

import streamlit as st

from ..settings import SETTINGS
from . import page_biomarkers, page_compare, page_export
from .components import page_header


def render() -> None:
    page_header(
        "Advanced",
        "Research tools: sweep one parameter at a time, export files and "
        "figures, read accelerometry biomarkers, and validate the method "
        "against Vicon. Not needed for a routine clinical read.",
    )

    labels = ["Comparator", "Export", "Accelerometry"]
    if SETTINGS.enable_experimental:
        labels.append("Method validation")

    # The Advanced folio is enough; the pages in the tabs must not add theirs.
    st.session_state["_embedded_header"] = True
    tabs = st.tabs(labels)
    with tabs[0]:
        page_compare.render()
    with tabs[1]:
        page_export.render()
    with tabs[2]:
        page_biomarkers.render()
    if SETTINGS.enable_experimental:
        from . import page_experimental

        with tabs[3]:
            page_experimental.render()
