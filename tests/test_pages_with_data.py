"""Render every analysis page with data loaded, not just its empty state.

The plain page smoke test loads no data, so the charts never draw. This one
injects the synthetic demo recording (which segments into ~18 cycles under
the default config) as the loaded source and drives each chart-bearing page,
so a regression in any figure -- kinematics, advanced or comparison -- shows
up as an ``app.exception`` rather than passing unnoticed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

APP_PY = Path(__file__).resolve().parent.parent / "app.py"


@pytest.mark.parametrize(
    "page",
    ["Pipeline explorer", "Comparator", "Longitudinal", "Export"],
)
def test_page_renders_with_demo_data(page: str) -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    from myogait_app.demo import make_demo_data
    from myogait_app.ui import state

    app = AppTest.from_file(str(APP_PY), default_timeout=90)
    app.run()
    app.session_state[state.K_SOURCE] = state.Source(
        kind="demo", name="demo", data=make_demo_data(), key="demo-fixture",
        model="synthetic",
    )
    app.session_state["nav_page"] = page
    app.run()

    assert not app.exception
