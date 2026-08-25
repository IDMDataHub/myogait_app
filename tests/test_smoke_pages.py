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
    # The Data page also renders radios of its own (e.g. "Video source"),
    # so select the sidebar navigation radio by its options rather than by
    # position in the element tree.
    nav = next(r for r in app.radio if "Data" in r.options)
    nav.set_value(page).run()

    assert not app.exception
