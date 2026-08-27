"""New assessment -- the entry screen: bring a recording in, watch the jobs.

The same machinery as the old Data page, reframed around the clinical verb
"start an assessment". It reuses the Data tabs verbatim (video extraction,
C3D import, pivot load, jobs) -- the Cohort moves to Analysis, where reading
a study belongs.
"""

from __future__ import annotations

import streamlit as st

from . import page_data, state
from .components import page_header, source_summary


def render() -> None:
    page_header(
        "New assessment",
        "Bring a recording in and attach it to a patient. A video to extract, "
        "a Vicon C3D, or an already-exported pivot -- the pipeline configures "
        "itself.",
    )

    st.info(
        "**Loading a video and its Vicon C3D for accuracy** — do it in two "
        "steps, tagging both with the **same patient and condition**:\n\n"
        "1. **Video → extraction**: pick the file, fill the patient / condition "
        "identifiers, start it. It runs as a job (see *Recent jobs*).\n"
        "2. **C3D**: import the matching Vicon trial and give it the *same* "
        "patient and condition.\n\n"
        "They then pair **automatically by patient** in **Analysis → Study & "
        "conditions**, where the markerless-vs-Vicon accuracy appears on its "
        "own. A single video alone is fine too — you just get variability, not "
        "accuracy."
    )

    source = state.get_source()
    if source is not None:
        st.success(f"Loaded: **{source.name}** ({source.kind})")
        source_summary(source)
        if st.button("Unload"):
            state.clear_source()
            st.rerun()
        st.divider()

    tab_video, tab_c3d, tab_json, tab_jobs = st.tabs(
        ["Video -> extraction", "C3D", "Pivot JSON", "Recent jobs"]
    )
    with tab_video:
        page_data._video_tab()
    with tab_c3d:
        page_data._c3d_tab()
    with tab_json:
        page_data._json_tab()
    with tab_jobs:
        page_data._ticket_tab()
