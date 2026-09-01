"""ui/state.py's pure helpers -- no Streamlit needed to exercise these."""
from __future__ import annotations

from myogait_app.ui.state import resolve_pivot_kind_and_path


def test_video_source_with_a_still_existing_video_path_upgrades_to_kind_video(tmp_path):
    """The bug this guards against: a video extraction, loaded back via

    Recent jobs -> Analyse (or the recording switcher), used to always
    install as kind="json" -- so source.kind == "video" (what the
    skeleton-overlay export and the video report both gate on) was
    unreachable through the normal workflow, even moments after the
    extraction that produced it.
    """
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"not a real video, just needs to exist")
    data = {"meta": {"source": "video", "video_path": str(video_file)}}

    kind, path = resolve_pivot_kind_and_path(data, tmp_path / "pivot.json")

    assert kind == "video"
    assert path == video_file


def test_video_source_whose_file_no_longer_exists_falls_back_to_json(tmp_path):
    """A pivot re-uploaded standalone, or moved to a different machine --

    the recorded video_path (from wherever it was originally extracted)
    will not resolve here. Falls back to the pre-existing behaviour rather
    than claiming a video source export can work when it cannot.
    """
    default_path = tmp_path / "pivot.json"
    data = {"meta": {"source": "video", "video_path": r"C:\gone\clip.mp4"}}

    kind, path = resolve_pivot_kind_and_path(data, default_path)

    assert kind == "json"
    assert path == default_path


def test_video_source_with_no_recorded_video_path_falls_back_to_json(tmp_path):
    default_path = tmp_path / "pivot.json"
    kind, path = resolve_pivot_kind_and_path({"meta": {"source": "video"}}, default_path)
    assert kind == "json"
    assert path == default_path


def test_c3d_source_never_upgrades_to_video(tmp_path):
    video_file = tmp_path / "clip.mp4"
    video_file.write_bytes(b"irrelevant")
    default_path = tmp_path / "pivot.json"
    data = {"meta": {"source": "c3d", "video_path": str(video_file)}}

    kind, path = resolve_pivot_kind_and_path(data, default_path)

    assert kind == "json"
    assert path == default_path


def test_missing_meta_falls_back_to_json(tmp_path):
    default_path = tmp_path / "pivot.json"
    assert resolve_pivot_kind_and_path({}, default_path) == ("json", default_path)
