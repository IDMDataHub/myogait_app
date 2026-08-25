from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "page",
    ["Data", "Pipeline explorer", "Comparator", "Longitudinal", "Export", "Experimental", "Reference"],
)
def test_page_renders_without_an_exception(page):
    """Exercise every empty-state page through Streamlit's public test API."""
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file("app.py")
    app.run()
    app.radio[0].set_value(page).run()

    assert not app.exception
