"""Accelerometry biomarkers: gait_accelerometry.py surfaced as its own page.

The video report already narrates two of its segments from this module;
this page is the same computation shown as a standing table, for a
recording read outside the context of that video, and reachable without
re-rendering it. See ``gait_accelerometry.py``'s own docstring for what
these biomarkers are, which of them cite published reference ranges, and
what was deliberately left out of the underlying port.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from .. import gait_accelerometry as ga
from . import state
from .components import page_header, recording_switcher, source_loader


def render() -> None:
    page_header(
        "Accelerometry biomarkers",
        "Trunk-accelerometry-style biomarkers (regularity, smoothness, spectral "
        "content, entropy) computed from this recording's own landmark "
        "trajectories -- no sensor worn. See the Index for method details.",
    )
    st.warning(
        "These biomarkers are computed differently from the similarly-named "
        "ones in the cohort tables (Analysis): different normalisation and "
        "filtering, not the same numbers. Don't compare a value from this "
        "page directly against a cohort-view value of the same name."
    )
    source = state.get_source()
    if source is None:
        source_loader(
            "Nothing loaded.",
            "This reads a recording's markerless landmarks as a virtual "
            "accelerometer -- go to New assessment to load a video first.",
            slot="biomarkers",
        )
        return

    recording_switcher("biomarkers")

    if source.kind != "video":
        st.caption(
            "Needs a video source's own landmark trajectories -- a C3D or a "
            "demo pivot without frame-by-frame landmarks cannot supply this."
        )
        return

    sites = [s for s in ga.SITES if ga.site_available(source.data, s)]
    if not sites:
        st.warning(
            "No anatomical site has enough landmark coverage in this recording "
            "for a virtual accelerometer (needs the hip and shoulder landmarks "
            "visible across most of the clip)."
        )
        return

    site = st.selectbox(
        "Site", sites, format_func=lambda s: ga.SITE_LABEL[s], key="biomarkers_site",
        help="Which landmark(s) the virtual accelerometer is built from. Sacrum "
        "matches a waist-worn sensor most closely.",
    )
    bio = ga.analyze_recording(source.data, site=site)
    if bio is None:
        st.warning(f"Could not build a stable signal at {ga.SITE_LABEL[site]} for this recording.")
        return

    st.caption(
        f"{bio.segment_length} samples at {bio.sampling_rate:.0f} Hz  ·  "
        f"{bio.temporal.total_steps} step(s) detected  ·  "
        "antero-posterior and vertical axes only -- a single camera has no "
        "medio-lateral depth, unlike a worn 3-axis sensor."
    )

    flat = bio.to_dict()
    for category, entries in ga.BIOMARKER_CATEGORIES.items():
        st.markdown(f"**{category}**")
        rows = []
        for code, label, description in entries:
            value = flat.get(code)
            # A uniform string column, not a mix of float/int/None -- a mixed
            # dtype column makes pyarrow's Streamlit table serialisation fall
            # back to a lossy auto-fix (observed: an int cell raised
            # ArrowTypeError against a column typed from its float neighbours).
            if isinstance(value, float):
                value_str = f"{value:.3f}"
            elif isinstance(value, int):
                value_str = str(value)
            else:
                value_str = "-"
            rows.append({
                "Biomarker": label,
                "Value": value_str,
                "Reference range": ga.get_reference_range(code),
                "Interpretation": ga.get_clinical_interpretation(code, value)
                if isinstance(value, (int, float)) else "-",
                "Description": description,
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.caption(
        "Reference ranges cite published literature (Moe-Nilssen & Helbostad "
        "2004, Gage et al. 2004, Bellanca et al. 2013, Hollman et al. 2011, "
        "Winter 2009, Bruijn et al. 2013) -- see gait_accelerometry.py's own "
        "docstring for the full list. Not derived from a bundled cohort: none "
        "ships with this app."
    )
