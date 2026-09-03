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
    # Advanced hosts the chart-bearing pages (Comparator, Export) as tabs;
    # AppTest executes every tab body, so rendering it with a loaded source
    # draws all those figures in one go. Trial Explorer moved out of Advanced
    # (it is Analysis's own default scope now, UX-01) -- Analysis is included
    # too so page_pipeline.py's charts stay exercised with real demo data.
    ["Advanced", "Analysis"],
)
def test_page_renders_with_demo_data(page: str) -> None:
    pytest.importorskip("streamlit")
    # Rendering a chart page runs the pipeline, which needs myogait; the CI
    # image omits it (heavy pose-estimation deps), so skip cleanly there rather
    # than error, the same way the longitudinal test skips without matplotlib.
    pytest.importorskip("myogait")
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
