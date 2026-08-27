"""Advanced -- research tools, kept off the clinical path.

Pipeline tuning, parameter sweeps, exports and the method-validation
benchmark live here, so New assessment and Analysis stay focused on the
clinical read. Every tab is an existing page, rendered unchanged.
"""

from __future__ import annotations

import streamlit as st

from ..settings import SETTINGS
from . import page_compare, page_export, page_pipeline
from .components import page_header


def render() -> None:
    page_header(
        "Advanced",
        "Research tools: tune the pipeline, sweep one parameter at a time, "
        "export files and figures, and validate the method against Vicon. Not "
        "needed for a routine clinical read.",
    )

    labels = ["Pipeline explorer", "Comparator", "Export"]
    if SETTINGS.enable_experimental:
        labels.append("Method validation")

    tabs = st.tabs(labels)
    with tabs[0]:
        page_pipeline.render()
    with tabs[1]:
        page_compare.render()
    with tabs[2]:
        page_export.render()
    if SETTINGS.enable_experimental:
        from . import page_experimental

        with tabs[3]:
            page_experimental.render()
