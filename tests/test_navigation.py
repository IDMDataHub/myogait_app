"""The "Go to New assessment" button (components._to_new_assessment).

Regression test for a real crash: clicking it set
st.session_state["nav_page"] directly, but that widget (the sidebar pills)
already ran earlier in the same script -- Streamlit raises
StreamlitAPIException the instant a widget's key is written after that
widget has been instantiated in the current run. Reproduces the exact
path from the bug report: Advanced -> Export, no source loaded, empty
state's button.
"""
from __future__ import annotations

from pathlib import Path

import pytest

APP_PY = Path(__file__).resolve().parent.parent / "app.py"


def test_go_to_new_assessment_button_does_not_crash_and_navigates():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP_PY), default_timeout=60)
    app.run()
    app.session_state["nav_page"] = "Advanced"
    app.run()
    assert not app.exception

    button = app.button(key="loader_data_export")
    button.click().run()

    assert not app.exception
    assert app.session_state["nav_page"] == "New assessment"
