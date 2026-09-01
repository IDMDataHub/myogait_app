"""Unit tests for charts.kinematics -- pure Plotly figure builders, no
Streamlit import, so these run without an AppTest harness.
"""
from __future__ import annotations

import numpy as np

from myogait_app.charts import kinematics as K
from myogait_app.charts.theme import series_colors


def _pooled(mean_by_side: dict[str, list[float]]) -> dict:
    summary = {
        side: {"hip_mean": mean, "hip_std": [1.0] * 101, "n_cycles": 2}
        for side, mean in mean_by_side.items()
    }
    return {"cycles": [], "summary": summary}


def test_video_vs_reference_overlay_uses_a_dedicated_colour_per_kind():
    hip_video = np.linspace(0, 30, 101).tolist()
    hip_vicon = np.linspace(5, 40, 101).tolist()
    video_pooled = _pooled({"left": hip_video, "right": hip_video})
    vicon_pooled = _pooled({"left": hip_vicon, "right": hip_vicon})

    fig = K.video_vs_reference_overlay(video_pooled, vicon_pooled, joint="hip", dark=False)

    assert len(fig.data) == 4  # video L/R + vicon L/R
    video_colour, reference_colour = series_colors(False)[0], series_colors(False)[1]
    for trace in fig.data:
        expected = video_colour if trace.name.startswith("Video") else reference_colour
        assert trace.line.color == expected
        # side is still legible without colour: solid for left, dashed for right
        expected_dash = "solid" if "Left" in trace.name else "dash"
        assert (trace.line.dash or "solid") == expected_dash


def test_video_vs_reference_overlay_skips_a_side_with_no_pooled_mean():
    video_pooled = _pooled({"left": np.linspace(0, 30, 101).tolist()})
    vicon_pooled = _pooled({"left": np.linspace(5, 40, 101).tolist()})

    fig = K.video_vs_reference_overlay(video_pooled, vicon_pooled, joint="hip", dark=False)

    assert len(fig.data) == 2  # only the left side has a mean on either side
    assert all("Left" in trace.name for trace in fig.data)
