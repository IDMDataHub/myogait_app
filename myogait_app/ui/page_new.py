"""New assessment -- the entry screen: bring a recording in, watch the jobs.

The same machinery as the old Data page, reframed around the clinical verb
"start an assessment". It reuses the Data tabs verbatim (video extraction,
C3D import, pivot load, jobs) -- the Cohort moves to Analysis, where reading
a study belongs.
"""

from __future__ import annotations

import streamlit as st

from . import page_data, state
from .components import page_header, source_summary, storage_banner


def render() -> None:
    page_header(
        "New assessment",
        "Bring a recording in and attach it to a patient. A video to extract, "
        "a Vicon C3D, or an already-exported pivot -- the pipeline configures "
        "itself.",
    )

    with st.expander("Video + Vicon C3D: how to measure accuracy", expanded=False):
        st.markdown(
            "Two steps, tagging both with the **same patient and condition**:\n\n"
            "1. **Video**: pick the file, fill the patient / condition "
            "identifiers, start it. It runs as a job (see *Recent jobs*).\n"
            "2. **C3D**: import the matching Vicon trial and give it the *same* "
            "patient and condition.\n\n"
            "They then pair **automatically by patient** in **Analysis → Accuracy "
            "vs C3D**. A single video alone is fine too — you just get "
            "variability, not accuracy."
        )

    source = state.get_source()
    if source is not None:
        st.success(f"Loaded: **{source.name}** ({source.kind})")
        source_summary(source)
        if st.button("Unload"):
            state.clear_source()
            st.rerun()
        st.divider()

    cols = st.columns([3, 1])
    cols[0].caption("No recording at hand? Try the example walk: a healthy adult "
                    "filmed side-on, Sapiens landmarks (CC BY 4.0).")
    if cols[1].button("Load the example", key="load_demo", use_container_width=True):
        _load_demo()

    tab_video, tab_c3d, tab_json, tab_jobs = st.tabs(
        ["Video", "Vicon C3D", "myogait JSON", "Recent jobs"]
    )
    with tab_video:
        page_data._video_tab()
    with tab_c3d:
        page_data._c3d_tab()
    with tab_json:
        st.caption(
            "The same pivot JSON can also be loaded straight into a cohort on "
            "**Advanced → Groups** or **Advanced → Patient over time** "
        )
        page_data._json_tab()
    with tab_jobs:
        page_data._ticket_tab()

    st.divider()
    storage_banner()


def _load_demo() -> None:
    """Install the bundled example walk and open Trial Explorer on it."""
    from ..demo import EXAMPLE_JSON, load_example_data

    data = load_example_data()
    model = str((data.get("extraction") or {}).get("model") or "sapiens")
    state.set_source(state.Source(kind="demo", name="Example walk (healthy adult)",
                                  data=data, key="example-walk", model=model,
                                  path=EXAMPLE_JSON))
    page_data.go_to_trial_explorer()
    st.rerun()
