"""Unit + fast end-to-end tests for mocap_report.py."""
from __future__ import annotations

import pytest

from myogait_app import mocap_report as mr
from myogait_app.demo import make_demo_data
from myogait_app.pipeline import AnglesConfig, PipelineConfig


def _prepared():
    myogait = pytest.importorskip("myogait")
    data = make_demo_data()
    data = myogait.compute_angles(data)
    data = myogait.canonicalize_angle_signs(data)
    data = myogait.detect_events(data)
    cycles = myogait.segment_cycles(data)
    stats = myogait.analyze_gait(data, cycles)
    return data, cycles, stats


def test_both_sides_rom_covers_left_and_right():
    _data, cycles, _stats = _prepared()
    both = mr._both_sides_rom(cycles)
    assert set(both) == {"LEFT", "RIGHT"}
    for side in both.values():
        assert side["n"] > 0
        assert set(side["rom"]) == set(side["hs"]) == set(side["to"])


def test_methodology_lines_describe_the_actual_config_not_a_generic_default():
    # PipelineConfig()'s own default has ISB reconstruction on (a correctness
    # fix, see pipeline.py's AnglesConfig.isb_reconstruction docstring) and
    # calibration on -- the methodology text must say exactly that, not a
    # fixed "off" template.
    default = mr._methodology_lines(PipelineConfig(), isb_tier=None)
    text = "\n".join(default)
    assert "Neutral calibration: on" in text
    assert "ISB reconstruction: on" in text

    isb_off_no_calib = mr._methodology_lines(
        PipelineConfig(angles=AnglesConfig(isb_reconstruction=False, calibrate=False)),
        isb_tier=None,
    )
    text_off = "\n".join(isb_off_no_calib)
    assert "Neutral calibration: off" in text_off
    assert "ISB reconstruction: off" in text_off

    with_tier = mr._methodology_lines(
        PipelineConfig(angles=AnglesConfig(isb_reconstruction=True)), isb_tier="tier2",
    )
    assert "ISB reconstruction: on (tier2)" in "\n".join(with_tier)


def test_render_mocap_report_end_to_end(tmp_path):
    data, cycles, stats = _prepared()
    out_path = tmp_path / "report.pdf"

    result = mr.render_mocap_report(data, cycles, stats, PipelineConfig(), str(out_path))

    assert result == out_path
    assert out_path.is_file() and out_path.stat().st_size > 1000
    with open(out_path, "rb") as f:
        assert f.read(5) == b"%PDF-"
