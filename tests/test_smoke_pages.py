from __future__ import annotations

from pathlib import Path

import pytest

#: Absolute path to the Streamlit entry script at the repository root.
#: AppTest.from_file resolves a relative path against the *caller's* file
#: (this tests/ directory), so it must be given the absolute path.
APP_PY = Path(__file__).resolve().parent.parent / "app.py"


@pytest.mark.parametrize(
    "page",
    ["New assessment", "Analysis", "Advanced", "Reference"],
)
def test_page_renders_without_an_exception(page):
    """Exercise every empty-state page through Streamlit's public test API."""
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    # A generous timeout: some pages import the full analysis stack and the
    # app injects its theme + background on every run, which is well over the
    # 3 s AppTest default on a cold import.
    app = AppTest.from_file(str(APP_PY), default_timeout=60)
    app.run()
    # Navigation is a keyed st.pills ("nav_page"); drive it through session
    # state, which AppTest supports for any keyed widget regardless of type.
    app.session_state["nav_page"] = page
    app.run()

    assert not app.exception
