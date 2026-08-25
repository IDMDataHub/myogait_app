"""Storage behaviours that must remain safe for local research sessions."""

from __future__ import annotations

import io
import threading

from myogait_app.storage import (
    Workspace,
    exceeds_in_memory_warning,
    path_is_within_root,
    store_uploaded_file,
    read_json,
    write_json_atomic,
)


def test_content_addressed_uploads_do_not_collide_on_name_and_size(tmp_path):
    """Different files named walk.mp4 must never reuse one another's bytes."""
    workspace = Workspace("test", tmp_path / "session").ensure()

    first = store_uploaded_file(workspace, io.BytesIO(b"ABCD"), "walk.mp4")
    second = store_uploaded_file(workspace, io.BytesIO(b"WXYZ"), "walk.mp4")
    repeated = store_uploaded_file(workspace, io.BytesIO(b"ABCD"), "walk.mp4")

    assert first != second
    assert first.name.endswith(".mp4")
    assert second.name.endswith(".mp4")
    assert first.read_bytes() == b"ABCD"
    assert second.read_bytes() == b"WXYZ"
    assert repeated == first


def test_path_is_within_root_rejects_a_sibling_directory(tmp_path):
    root = tmp_path / "vicon"
    trial = root / "trial_01"
    sibling = tmp_path / "other_trial"
    trial.mkdir(parents=True)
    sibling.mkdir()

    assert path_is_within_root(trial, root)
    assert not path_is_within_root(sibling, root)


def test_in_memory_upload_warning_uses_a_strict_size_threshold():
    threshold_mb = 2
    assert not exceeds_in_memory_warning(2 * 1024 * 1024, threshold_mb)
    assert exceeds_in_memory_warning(2 * 1024 * 1024 + 1, threshold_mb)


def test_atomic_json_writes_remain_readable_under_concurrent_writers(tmp_path):
    target = tmp_path / "state.json"
    errors = []

    def write(value: int) -> None:
        try:
            for _ in range(10):
                write_json_atomic(target, {"value": value})
                assert read_json(target) in ({"value": 1}, {"value": 2})
        except Exception as exc:  # pragma: no cover - asserted after joining
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(value,)) for value in (1, 2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not any(thread.is_alive() for thread in threads)
    assert not errors
    assert read_json(target) in ({"value": 1}, {"value": 2})
    assert not list(tmp_path.glob("*.tmp"))
