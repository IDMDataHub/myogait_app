from __future__ import annotations

from pathlib import Path

import pytest

#: Absolute path to the Streamlit entry script at the repository root.
#: AppTest.from_file resolves a relative path against the *caller's* file
#: (this tests/ directory), so it must be given the absolute path.
APP_PY = Path(__file__).resolve().parent.parent / "app.py"


@pytest.mark.parametrize(
    "page",
    ["Data", "Pipeline explorer", "Comparator", "Longitudinal", "Export", "Experimental", "Reference"],
)
def test_page_renders_without_an_exception(page):
    """Exercise every empty-state page through Streamlit's public test API."""
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP_PY))
    app.run()
    app.radio[0].set_value(page).run()

    assert not app.exception
