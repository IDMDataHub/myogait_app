"""Analysis -- read the data at any scope, accuracy vs Vicon when present.

One screen, one scope selector. It routes to the views that already exist:
a study/condition cohort, one patient over time, a single run, or the export
surface. The scope the page opens on follows the data actually loaded --
a single freshly loaded recording opens on "Single run" (the view that shows
it), not on the cohort view that would look empty. The markerless-vs-Vicon
accuracy surfaces on its own wherever a marker reference is present (paired
automatically by patient in the cohort view).
"""

from __future__ import annotations

import streamlit as st

from . import page_export, page_longitudinal, page_pipeline, page_pool, state
from .components import page_header

#: Scope label -> the existing renderer it delegates to.
_STUDY = "Study & conditions"
_PATIENT = "Patient over time"
_RUN = "Single run"
_EXPORT = "Export"
_SCOPES = (_STUDY, _PATIENT, _RUN, _EXPORT)


def _default_scope() -> str:
    """The scope matching the data actually loaded.

    A cohort batch wins (the user explicitly built it), then longitudinal
    sessions, then a single loaded source -- the case that used to land on an
    empty-looking cohort view. ``st.pills`` only honours ``default`` on first
    instantiation, so this steers the first visit and never fights the user's
    own later selection.
    """
    if st.session_state.get("pool_runs"):
        return _STUDY
    if state.get_longitudinal_sessions():
        return _PATIENT
    if state.has_source():
        return _RUN
    return _STUDY


def render() -> None:
    page_header(
        "Analysis",
        "Read the data at the scope you need -- a whole study by condition, one "
        "patient across visits, or a single run -- and export from here. "
        "Accuracy vs Vicon appears wherever a marker reference is present.",
    )

    # A stored scope from an older app version (renamed/removed label) makes
    # st.pills raise; drop it so the dynamic default takes over instead.
    if st.session_state.get("analysis_scope") not in (None, *_SCOPES):
        st.session_state.pop("analysis_scope", None)

    scope = st.pills(
        "Scope", list(_SCOPES), selection_mode="single",
        default=_default_scope(), key="analysis_scope",
        label_visibility="collapsed",
    ) or _default_scope()

    st.divider()
    # The Analysis folio is enough; the view below must not add its own.
    st.session_state["_embedded_header"] = True
    if scope == _STUDY:
        page_pool.render(show_header=False)
    elif scope == _PATIENT:
        page_longitudinal.render()
    elif scope == _EXPORT:
        page_export.render()
    else:
        page_pipeline.render()
