"""The Index page: function glossary search, plus the new Guides section."""
from __future__ import annotations

from pathlib import Path

import pytest

from myogait_app.ui.page_reference import _GUIDES

APP_PY = Path(__file__).resolve().parent.parent / "app.py"


def test_guides_are_non_empty_and_have_a_title_and_body():
    assert _GUIDES
    for title, body in _GUIDES:
        assert title.strip()
        assert body.strip()


def test_index_page_renders_the_pairing_guide():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP_PY), default_timeout=60)
    app.run()
    app.session_state["nav_page"] = "Index"
    app.run()

    assert not app.exception
    titles = [e.label for e in app.expander]
    assert "Compare a video extraction against its Vicon C3D" in titles
