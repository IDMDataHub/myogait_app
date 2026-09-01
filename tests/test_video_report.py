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


def test_prepare_computes_the_virtual_accelerometer_and_its_biomarkers():
    data, cycles, stats = _prepared()
    rd = vr.prepare(data, cycles, stats, accel_site="sacrum")

    assert rd.accel_site == "sacrum"
    assert rd.accel_ap is not None and rd.accel_v is not None
    assert rd.accel_t is not None and len(rd.accel_t) == len(rd.accel_v)
    assert rd.accel_rms_v is not None and len(rd.accel_rms_v) == len(rd.accel_v)
    assert rd.accel_display is not None
    assert rd.accel_display.shape == (len(data["frames"]), 2)
    assert rd.biomarkers is not None
    assert rd.biomarkers.site == "sacrum"
    assert rd.cohort is None  # no reference_cohort was passed


def test_prepare_degrades_gracefully_when_the_accelerometer_cannot_be_built():
    """Too few frames for gait_accelerometry -- the report must still

    build the rest of its data (angles, RoM, spatio-temporal), just
    without an accelerometer/biomarkers section, not raise.
    """
    from myogait_app.demo import make_demo_data

    data = make_demo_data(n_frames=10, fps=30.0)
    myogait = pytest.importorskip("myogait")
    data = myogait.compute_angles(data)
    data = myogait.canonicalize_angle_signs(data)
    data = myogait.detect_events(data)
    cycles = myogait.segment_cycles(data)
    stats = myogait.analyze_gait(data, cycles)

    rd = vr.prepare(data, cycles, stats)
    assert rd.biomarkers is None
    assert rd.accel_ap is None and rd.accel_v is None


def test_parse_reference_cohort_groups_by_biomarker_and_drops_thin_groups():
    data, cycles, stats = _prepared()
    bio = vr.ga.analyze_recording(data, site="sacrum")
    rows = (
        [{"subject": f"S{i}", "biomarker": "Cadence", "video": 90 + i, "imu": 88 + i} for i in range(5)]
        # Only 2 points: below the 3-point minimum, must be dropped.
        + [{"subject": "S1", "biomarker": "Too thin", "video": 1.0, "imu": 1.0},
           {"subject": "S2", "biomarker": "Too thin", "video": 2.0, "imu": 2.0}]
    )
    cohort = vr._parse_reference_cohort(rows, bio)
    assert cohort is not None
    assert "Cadence" in cohort
    assert "Too thin" not in cohort
    subjects, video_vals, imu_vals, r, p_value, own_value = cohort["Cadence"]
    assert len(subjects) == 5
    assert r == pytest.approx(1.0)
    # "Cadence" resolves via _COHORT_ALIASES to this recording's own value.
    assert own_value == pytest.approx(bio.to_dict()["temporal_cadence"])


def test_parse_reference_cohort_returns_none_for_malformed_or_empty_input():
    assert vr._parse_reference_cohort([], None) is None
    assert vr._parse_reference_cohort(None, None) is None
    junk = [{"subject": "S1", "biomarker": "Cadence"}]  # missing video/imu
    assert vr._parse_reference_cohort(junk, None) is None


def test_parse_reference_cohort_tolerates_an_unrecognised_biomarker_label():
    """An unaliased label still plots -- it just has no "own value" to mark."""
    rows = [{"subject": f"S{i}", "biomarker": "Something Custom", "video": i, "imu": i + 0.1}
            for i in range(4)]
    cohort = vr._parse_reference_cohort(rows, None)
    assert cohort is not None
    assert cohort["Something Custom"][5] is None  # own_value


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


def _install_shrunk_timeline(monkeypatch) -> None:
    """Same segments ``_timeline(has_cohort)`` would build, but ~3 output

    frames each instead of hundreds -- keeps the real main loop (frame
    reading, segment dispatch, compositing, video writing) under real
    coverage without a multi-minute render. *has_cohort* is still
    forwarded to the real function first, so which branch
    ``render_video_report`` itself picked stays observable through
    ``vr._timeline(True/False)`` after patching.
    """
    real_timeline = vr._timeline

    def shrunk(has_cohort: bool):
        full = real_timeline(has_cohort)
        return tuple(
            (name, i * 0.1, (i + 1) * 0.1, j0, spd)
            for i, (name, _t0, _t1, j0, spd) in enumerate(full)
        )

    monkeypatch.setattr(vr, "_timeline", shrunk)


def test_render_video_report_end_to_end(tmp_path, monkeypatch):
    """The real main loop, shrunk to a handful of frames per segment --

    the default (no reference cohort) 7-segment timeline.
    """
    data, cycles, stats = _prepared()
    video_path = tmp_path / "dummy.mp4"
    _write_dummy_video(video_path, n_frames=len(data["frames"]))
    _install_shrunk_timeline(monkeypatch)
    short_segments = vr._timeline(False)

    out_path = tmp_path / "out.mp4"
    progress: list[float] = []
    result = vr.render_video_report(
        data, cycles, stats, str(video_path), str(out_path),
        progress_callback=progress.append,
    )

    assert result == out_path
    assert out_path.is_file() and out_path.stat().st_size > 0
    assert progress and progress[-1] == 1.0
    assert [name for name, *_r in short_segments] == [
        "intro", "angles", "spatiotemporal", "rom", "accelerometer", "biomarkers", "summary",
    ]

    cap = cv2.VideoCapture(str(out_path))
    assert cap.get(cv2.CAP_PROP_FRAME_COUNT) == int(short_segments[-1][2] * vr.FPS_OUT)
    ok, frame = cap.read()
    assert ok and frame.shape == (vr.H_OUT, vr.W_OUT, 3)
    cap.release()


def test_render_video_report_inserts_the_cohort_segment_when_given_a_reference(tmp_path, monkeypatch):
    data, cycles, stats = _prepared()
    video_path = tmp_path / "dummy.mp4"
    _write_dummy_video(video_path, n_frames=len(data["frames"]))
    _install_shrunk_timeline(monkeypatch)
    expected = vr._timeline(True)
    assert "cohort" in [name for name, *_r in expected]

    cohort_rows = [
        {"subject": f"S{i}", "biomarker": "Cadence", "video": 90 + i, "imu": 88 + i} for i in range(4)
    ]
    out_path = tmp_path / "out_cohort.mp4"
    result = vr.render_video_report(
        data, cycles, stats, str(video_path), str(out_path), reference_cohort=cohort_rows,
    )

    assert result == out_path
    cap = cv2.VideoCapture(str(out_path))
    # The real reference_cohort resolved to something usable, so
    # render_video_report itself chose the 8-segment (True) timeline.
    assert cap.get(cv2.CAP_PROP_FRAME_COUNT) == int(expected[-1][2] * vr.FPS_OUT)
    cap.release()


def test_render_video_report_falls_back_to_seven_segments_when_the_cohort_has_nothing_usable(
    tmp_path, monkeypatch,
):
    """A reference file with only thin (<3-point) groups parses to nothing

    -- the report must still render, just without a cohort segment,
    rather than crash on an empty one.
    """
    data, cycles, stats = _prepared()
    video_path = tmp_path / "dummy.mp4"
    _write_dummy_video(video_path, n_frames=len(data["frames"]))
    _install_shrunk_timeline(monkeypatch)
    expected = vr._timeline(False)

    out_path = tmp_path / "out_thin.mp4"
    result = vr.render_video_report(
        data, cycles, stats, str(video_path), str(out_path),
        reference_cohort=[{"subject": "S1", "biomarker": "Cadence", "video": 1.0, "imu": 1.0}],
    )
    assert result == out_path
    cap = cv2.VideoCapture(str(out_path))
    # Only 1 point (< 3 minimum) parsed to no usable cohort, so
    # render_video_report itself fell back to the 7-segment (False) timeline.
    assert cap.get(cv2.CAP_PROP_FRAME_COUNT) == int(expected[-1][2] * vr.FPS_OUT)
    cap.release()
