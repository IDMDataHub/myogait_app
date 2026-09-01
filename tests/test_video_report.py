"""Unit + fast end-to-end tests for video_report.py.

``render_video_report``'s real 5-segment duration renders ~1680 frames and
takes several minutes -- fine for a one-off manual check, not for a test
suite. The end-to-end test here monkeypatches the segment timeline down to
a handful of frames instead, so the *same* main loop (frame reading,
segment dispatch, text/shape compositing, video writing) gets real
coverage in well under a second.
"""
from __future__ import annotations

import cv2
import numpy as np
import pytest

from myogait_app import video_report as vr
from myogait_app.demo import make_demo_data


def _prepared():
    myogait = pytest.importorskip("myogait")
    data = make_demo_data()
    data = myogait.compute_angles(data)
    data = myogait.canonicalize_angle_signs(data)
    data = myogait.detect_events(data)
    cycles = myogait.segment_cycles(data)
    stats = myogait.analyze_gait(data, cycles)
    return data, cycles, stats


def test_prepare_extracts_every_field_from_real_pipeline_output():
    data, cycles, stats = _prepared()
    rd = vr.prepare(data, cycles, stats)

    assert rd.side in ("LEFT", "RIGHT")
    assert rd.landmarks.shape == (len(data["frames"]), len(vr.LANDMARK_NAMES), 3)
    assert rd.angle_t.shape[0] == len(data["angles"]["frames"])
    assert set(rd.angles) == set(vr.SAGITTAL_JOINTS)
    assert rd.n_cycles > 0
    # RoM and the heel-strike/toe-off angles are computed for every joint
    # that has segmented cycles on the picked side.
    assert set(rd.rom_deg) <= set(vr.SAGITTAL_JOINTS)
    assert set(rd.rom_deg) == set(rd.at_heel_strike) == set(rd.at_toe_off)
    for joint, rom in rd.rom_deg.items():
        assert rom >= 0
    assert rd.spatiotemporal.get("cadence_steps_per_min")


def test_pick_side_follows_the_more_visible_side():
    landmarks = np.zeros((5, len(vr.LANDMARK_NAMES), 3))
    idx = {n: i for i, n in enumerate(vr.LANDMARK_NAMES)}
    for name in ("LEFT_HIP", "LEFT_KNEE", "LEFT_ANKLE"):
        landmarks[:, idx[name], 2] = 0.9
    for name in ("RIGHT_HIP", "RIGHT_KNEE", "RIGHT_ANKLE"):
        landmarks[:, idx[name], 2] = 0.2
    assert vr._pick_side(landmarks) == "LEFT"


def test_rom_and_events_reads_start_and_stance_indexed_angle():
    curve = list(range(101))  # angle == percent-of-cycle, exactly
    cycles = {
        "cycles": [
            {"side": "left", "stance_pct": 60.0, "angles_normalized": {"hip": curve}},
            {"side": "left", "stance_pct": 60.0, "angles_normalized": {"hip": curve}},
        ]
    }
    rom, hs, to, n = vr._rom_and_events(cycles, "LEFT")
    assert n == 2
    assert hs["hip"] == pytest.approx(0.0)   # 0% of cycle
    assert to["hip"] == pytest.approx(60.0)  # stance_pct% of cycle
    assert rom["hip"] == pytest.approx(100.0)


def _write_dummy_video(path, n_frames=10, size=(320, 480)) -> None:
    w, h = size
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30.0, (w, h))
    for i in range(n_frames):
        frame = np.full((h, w, 3), 40, np.uint8)
        writer.write(frame)
    writer.release()


def test_render_video_report_end_to_end(tmp_path, monkeypatch):
    """The real main loop, shrunk to a handful of frames per segment."""
    data, cycles, stats = _prepared()
    video_path = tmp_path / "dummy.mp4"
    _write_dummy_video(video_path, n_frames=len(data["frames"]))

    # Same 5 named segments, ~3 output frames each instead of hundreds.
    short_segments = tuple(
        (name, i * 0.1, (i + 1) * 0.1, j0, spd)
        for i, (name, _t0, _t1, j0, spd) in enumerate(vr._SEGMENTS)
    )
    monkeypatch.setattr(vr, "_SEGMENTS", short_segments)
    monkeypatch.setattr(vr, "DURATION_S", short_segments[-1][2])

    out_path = tmp_path / "out.mp4"
    progress: list[float] = []
    result = vr.render_video_report(
        data, cycles, stats, str(video_path), str(out_path),
        progress_callback=progress.append,
    )

    assert result == out_path
    assert out_path.is_file() and out_path.stat().st_size > 0
    assert progress and progress[-1] == 1.0

    cap = cv2.VideoCapture(str(out_path))
    assert cap.get(cv2.CAP_PROP_FRAME_COUNT) == int(short_segments[-1][2] * vr.FPS_OUT)
    ok, frame = cap.read()
    assert ok and frame.shape == (vr.H_OUT, vr.W_OUT, 3)
    cap.release()
