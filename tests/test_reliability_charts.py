"""Reliability figures (Bland-Altman, group boxplot) + accuracy-mode smoke."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from myogait_app.pooling import RunResult
from myogait_app.reliability import bland_altman

APP_PY = Path(__file__).resolve().parents[1] / "app.py"


def test_bland_altman_plot_traces_and_lines():
    from myogait_app.charts.reliability import bland_altman_plot

    ba = bland_altman(np.array([10.0, 12.0, 14.0, 16.0]),
                      np.array([11.0, 11.5, 15.0, 15.5]))
    fig = bland_altman_plot(ba, parameter="hip_rom")
    # One scatter trace with all pairs, plus bias/LoA/zero as h-lines.
    assert len(fig.data) == 1
    assert len(fig.data[0].x) == ba.n
    hlines = [s for s in fig.layout.shapes if s.type == "line"]
    assert len(hlines) >= 4  # bias, two LoA, zero


def test_group_boxplot_two_boxes_with_points():
    from myogait_app.charts.reliability import group_boxplot

    rows = ([{"parameter": "hip_rom", "group": "A", "condition": "A", "value": v}
             for v in (30.0, 31.0, 32.0)]
            + [{"parameter": "hip_rom", "group": "B", "condition": "B", "value": v}
               for v in (20.0, 21.0, 22.0)])
    fig = group_boxplot(rows, "hip_rom", "A", "B", by="group")
    assert len(fig.data) == 2
    assert all(trace.type == "box" for trace in fig.data)
    assert list(fig.data[0].y) == [30.0, 31.0, 32.0]


def _paired_fixture() -> list[RunResult]:
    curve = [float(i) for i in range(101)]
    cycles = {"cycles": [{"side": "left", "cycle_id": 1,
                          "angles_normalized": {"hip": curve, "knee": curve, "ankle": curve}}],
              "summary": {}}
    runs = []
    for i in range(6):
        study = {"patient_id": f"P{i}", "run": "r1", "condition": "baseline"}
        runs.append(RunResult(f"P{i}_v.json", study, ok=True, kind="video",
                              cycles=cycles, stats={}))
        runs.append(RunResult(f"P{i}_ref.json", study, ok=True, kind="vicon",
                              cycles=cycles, stats={}))
    return runs


def test_accuracy_scope_renders_validity_sections() -> None:
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP_PY), default_timeout=60)
    app.run()
    app.session_state["nav_page"] = "Analysis"
    app.session_state["analysis_scope"] = "Accuracy vs C3D"
    app.session_state["pool_runs"] = _paired_fixture()
    app.run()
    assert not app.exception
    text = " ".join(getattr(el, "value", "") or "" for el in app.markdown)
    assert "ICC(2,1)" in text
    assert "Test-retest" in text
