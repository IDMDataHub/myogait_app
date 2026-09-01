"""app myogait -- interactive workbench for the myogait toolkit.

Run with:
    streamlit run app.py

The sidebar holds the whole pipeline configuration and stays visible on
every page, because the questions this app exists to answer are all of
the form "what does this parameter change" -- which only works if the
parameters and their consequences are on screen together.
"""

from __future__ import annotations

# Two-screen IA: New assessment (get data in) and Analysis (read it).
import streamlit as st

from myogait_app import theme_css
from myogait_app.branding import BRANDING
from myogait_app.settings import SETTINGS
from myogait_app.storage import purge_expired
from myogait_app.ui import (
    components,
    page_advanced,
    page_analysis,
    page_new,
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


#: Two clinical screens -- get data in, then read it -- plus a demoted
#: Advanced space for the research tools and Reference for the docs.
PAGES = {
    "New assessment": page_new.render,
    "Analysis": page_analysis.render,
    "Advanced": page_advanced.render,
    "Reference": page_reference.render,
}


def main() -> None:
    _startup()
    state.init()
    # Only the top-level screen shows a folio; nested pages (Advanced tabs,
    # Analysis scopes) set this flag to skip theirs. Reset it every run.
    st.session_state["_embedded_header"] = False
    st.markdown(theme_css.inject(), unsafe_allow_html=True)
    st.markdown(theme_css.background_css(), unsafe_allow_html=True)

    with st.sidebar:
        components.sidebar_identity()
        st.divider()

        page = st.pills(
            "Page", list(PAGES), selection_mode="single", default="New assessment",
            label_visibility="collapsed", key="nav_page",
        )
        page = page or "New assessment"

        source = state.get_source()
        if source is None:
            st.caption("No data loaded.")
        else:
            st.caption(f"Loaded: **{source.name}**")

        st.divider()

        # The configuration panel is only useful once there is something
        # to apply it to, and showing thirty disabled controls on first
        # load would bury the one action that matters. Reference is pure
        # documentation and never needs it, loaded source or not. A cohort
        # batch counts as "something": its shared-recipe mode applies this
        # very configuration to every recording in the batch.
        has_batch = bool(st.session_state.get("pool_runs"))
        if (source is not None or has_batch) and page in ("Analysis", "Advanced"):
            st.markdown("**Pipeline configuration**")
            state.set_config(sidebar.render(state.get_config(), source))
            if st.button("Reset to defaults", use_container_width=True):
                state.reset_config()
                st.rerun()
            st.divider()

        components.runtime_badge()

    components.runtime_warnings()

    PAGES[page]()

    theme_css.render_footer()


if __name__ == "__main__":
    main()
