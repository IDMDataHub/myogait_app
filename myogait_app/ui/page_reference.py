"""A small index of what myogait's processing functions actually do.

Grouped in pipeline order, grounded in the package's own docstrings
(``myogait_app.glossary``), with a status tag distinguishing what is
already usable in this app from what a later phase will add. Available
with nothing loaded -- it is documentation, not an analysis screen.
"""

from __future__ import annotations

import streamlit as st

from ..glossary import GROUPS, find
from .components import page_header

_STATUS_BADGE = {
    "phase4": " &middot; :orange[planned - Phase 4]",
    "phase5": " &middot; :orange[planned - Phase 5]",
    "backlog": " &middot; :gray[backlog - not wired]",
}


def render() -> None:
    page_header(
        "Reference",
        "What each myogait processing function does, grouped by pipeline stage. "
        "Written from the package's own docstrings.",
    )

    query = st.text_input(
        "Search", placeholder="e.g. butterworth, GVS, femur, c3d, perspective"
    )

    if query.strip():
        matches = find(query)
        st.caption(f"{len(matches)} match(es).")
        if not matches:
            return
        last_group = None
        for group, entry in matches:
            if group != last_group:
                st.markdown(f"**{group}**")
                last_group = group
            _entry_row(entry)
        return

    for title, entries in GROUPS:
        with st.expander(title, expanded=False):
            for entry in entries:
                _entry_row(entry)


def _entry_row(entry) -> None:
    badge = _STATUS_BADGE.get(entry.status, "")
    st.markdown(f"`{entry.name}`{badge}")
    caption = entry.summary
    if entry.citation:
        caption += f"  _{entry.citation}_"
    st.caption(caption)
