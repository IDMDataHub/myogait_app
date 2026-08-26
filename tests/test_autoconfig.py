"""Unit tests for the per-recording pipeline auto-configuration."""

from __future__ import annotations

import numpy as np

from myogait_app.autoconfig import (
    _has_direction_reversal,
    _has_static_start,
    detect_config,
)


def _frames(xs):
    return [
        {"landmarks": {"LEFT_HIP": {"x": float(x), "y": 0.5},
                       "RIGHT_HIP": {"x": float(x), "y": 0.5}}}
        for x in xs
    ]


def test_c3d_source_takes_the_overground_recipe():
    data = {
        "c3d_markers_3d": {"LEFT_HEEL": [[0, 0, 0]]},
        "frames": _frames(np.linspace(0.3, 0.7, 60)),
    }
    cfg, reasons = detect_config(data)
    assert cfg.angles.calibrate is False
    assert cfg.events.trim_standstill is False
    assert cfg.cycles.max_duration == 1.8
    assert any("marker" in r or "C3D" in r for r in reasons)


def test_clean_standing_start_keeps_the_default_recipe():
    xs = [0.30] * 25 + list(np.linspace(0.30, 0.70, 35))  # stand, then walk one way
    data = {"frames": _frames(xs)}
    assert _has_static_start(data["frames"]) is True
    assert _has_direction_reversal(data["frames"]) is False
    cfg, reasons = detect_config(data)
    assert cfg.angles.calibrate is True  # default preserved


def test_there_and_back_walkway_takes_the_overground_recipe():
    xs = list(np.linspace(0.30, 0.80, 30)) + list(np.linspace(0.80, 0.30, 30))
    data = {"frames": _frames(xs)}
    assert _has_direction_reversal(data["frames"]) is True
    cfg, reasons = detect_config(data)
    assert cfg.angles.calibrate is False
    assert any("there-and-back" in r for r in reasons)


def test_detect_config_keeps_the_base_subject():
    from dataclasses import replace

    from myogait_app.pipeline import PipelineConfig, SubjectConfig

    base = replace(PipelineConfig(), subject=SubjectConfig(height_m=1.75))
    data = {"c3d_markers_3d": {"x": 1}, "frames": _frames(np.linspace(0.3, 0.7, 40))}
    cfg, _ = detect_config(data, base)
    assert cfg.subject.height_m == 1.75  # recipe changed, subject preserved
