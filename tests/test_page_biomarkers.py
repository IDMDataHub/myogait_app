"""Render the Advanced -> Accelerometry tab with a real video source loaded.

``test_pages_with_data.py`` already renders Advanced with a demo source, but
that fixture's ``kind == "demo"`` takes this page's early-return branch, not
the one that actually calls ``gait_accelerometry.analyze_recording`` and
builds the per-category dataframes -- exactly the branch a real bug lived in
during development (an ``int``/``float``-mixed "Value" column made pyarrow's
table serialisation raise, silently auto-fixed by Streamlit rather than
surfaced as ``app.exception``, so this needs to specifically inspect the
rendered dataframes, not just assert no exception).
"""

from __future__ import annotations

from pathlib import Path

import pytest

APP_PY = Path(__file__).resolve().parent.parent / "app.py"


def test_accelerometry_tab_renders_real_biomarker_tables_without_a_type_error():
    pytest.importorskip("streamlit")
    pytest.importorskip("myogait")
    from streamlit.testing.v1 import AppTest

    from myogait_app.demo import make_demo_data
    from myogait_app.ui import state

    app = AppTest.from_file(str(APP_PY), default_timeout=90)
    app.run()
    app.session_state[state.K_SOURCE] = state.Source(
        kind="video", name="demo.mp4",
        data=make_demo_data(n_frames=300, fps=30.0, progression=0.25, noise=0.0015),
        key="demo-video-fixture", model="synthetic",
    )
    app.session_state["nav_page"] = "Advanced"
    app.run()

    assert not app.exception
    # One dataframe per BIOMARKER_CATEGORIES group, each with a uniformly
    # string-typed "Value" column (the regression this test guards).
    from myogait_app import gait_accelerometry as ga

    tables = [df.value for df in app.dataframe if "Biomarker" in df.value.columns]
    assert len(tables) == len(ga.BIOMARKER_CATEGORIES)
    for table in tables:
        assert table["Value"].map(type).eq(str).all()
