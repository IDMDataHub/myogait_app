"""app myogait -- interactive workbench for the myogait toolkit.

Run with:
    streamlit run app.py

The sidebar holds the whole pipeline configuration and stays visible on
every page, because the questions this app exists to answer are all of
the form "what does this parameter change" -- which only works if the
parameters and their consequences are on screen together.
"""

from __future__ import annotations

import streamlit as st

from myogait_app.branding import BRANDING
from myogait_app.settings import SETTINGS
from myogait_app.storage import purge_expired
from myogait_app.ui import (
    components,
    page_compare,
    page_data,
    page_experimental,
    page_export,
    page_longitudinal,
    page_pipeline,
    page_reference,
    sidebar,
    state,
)

st.set_page_config(
    page_title=BRANDING.app_name,
    page_icon="•",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def _startup() -> dict:
    """Once per server process: create the workspace and purge stale data.

    Cached as a resource rather than called on every rerun -- purging is
    filesystem work and this app reruns on every widget change.
    """
    SETTINGS.ensure_dirs()
    return purge_expired(SETTINGS)


PAGES = {
    "Data": page_data.render,
    "Pipeline explorer": page_pipeline.render,
    "Comparator": page_compare.render,
    "Longitudinal": page_longitudinal.render,
    "Export": page_export.render,
}
if SETTINGS.enable_experimental:
    PAGES["Experimental"] = page_experimental.render
PAGES["Reference"] = page_reference.render


def main() -> None:
    _startup()
    state.init()

    with st.sidebar:
        components.sidebar_identity()
        st.divider()

        page = st.radio("Page", list(PAGES), label_visibility="collapsed")

        source = state.get_source()
        if source is None:
            st.caption("No data loaded.")
        else:
            st.caption(f"Loaded: **{source.name}**")

        st.divider()

        # The configuration panel is only useful once there is something
        # to apply it to, and showing thirty disabled controls on first
        # load would bury the one action that matters. Reference is pure
        # documentation and never needs it, loaded source or not.
        if source is not None and page not in ("Data", "Reference"):
            st.markdown("**Pipeline configuration**")
            state.set_config(sidebar.render(state.get_config()))
            if st.button("Reset to defaults", use_container_width=True):
                state.reset_config()
                st.rerun()
            st.divider()

        components.runtime_badge()

    components.runtime_warnings()
    PAGES[page]()


if __name__ == "__main__":
    main()
