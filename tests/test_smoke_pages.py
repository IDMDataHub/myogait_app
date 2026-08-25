from __future__ import annotations

import pytest


def test_data_page_renders_without_an_exception():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file("app.py")
    app.run()
    assert not app.exception
