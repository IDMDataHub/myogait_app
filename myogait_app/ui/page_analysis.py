"""Analysis -- read the data at any scope, accuracy vs Vicon when present.

One screen, one scope selector. It routes to the views that already exist:
a study/condition cohort, one patient over time, or a single run. The
markerless-vs-Vicon accuracy surfaces on its own wherever a marker reference
is present (paired automatically by patient in the cohort view).
"""

from __future__ import annotations

import streamlit as st

from . import page_longitudinal, page_pipeline, page_pool
from .components import page_header

#: Scope label -> the existing renderer it delegates to.
_STUDY = "Study & conditions"
_PATIENT = "Patient over time"
_RUN = "Single run"


def render() -> None:
    page_header(
        "Analysis",
        "Read the data at the scope you need -- a whole study by condition, one "
        "patient across visits, or a single run. Accuracy vs Vicon appears "
        "wherever a marker reference is present.",
    )

    scope = st.pills(
        "Scope", [_STUDY, _PATIENT, _RUN], selection_mode="single",
        default=_STUDY, key="analysis_scope", label_visibility="collapsed",
    ) or _STUDY

    st.divider()
    # The Analysis folio is enough; the view below must not add its own.
    st.session_state["_embedded_header"] = True
    if scope == _STUDY:
        page_pool.render(show_header=False)
    elif scope == _PATIENT:
        page_longitudinal.render()
    else:
        page_pipeline.render()
