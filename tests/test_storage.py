"""Storage behaviours that must remain safe for local research sessions."""

from __future__ import annotations

import io
import threading

import pytest

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


def test_content_addressed_uploads_are_spooled_in_a_single_pass(tmp_path):
    class CountingStream(io.BytesIO):
        def __init__(self, payload: bytes) -> None:
            super().__init__(payload)
            self.read_calls = 0

        def read(self, size: int = -1) -> bytes:
            self.read_calls += 1
            return super().read(size)

    workspace = Workspace("test", tmp_path / "session").ensure()
    stream = CountingStream(b"abcdef")

    stored = store_uploaded_file(workspace, stream, "walk.mp4", chunk_size=2)

    assert stored.read_bytes() == b"abcdef"
    # Three data chunks plus the final empty read: no second pass for writing.
    assert stream.read_calls == 4
    assert not list(workspace.uploads.glob(".upload-*.tmp"))


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
    """Two threads hammering the same file must never crash the *writer*

    (write_json_atomic's own retry against Windows' transient
    PermissionError -- see storage.py). A read racing the other thread's
    write may still legitimately return None (read_json's own documented
    contract: "a transient failure is expected and is not worth an
    exception" -- real callers like JobManager already tolerate it); only
    the post-join read, once nothing is writing any more, must be reliable.
    """
    target = tmp_path / "state.json"
    errors = []

    def write(value: int) -> None:
        try:
            for _ in range(10):
                write_json_atomic(target, {"value": value})
                assert read_json(target) in ({"value": 1}, {"value": 2}, None)
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


def test_atomic_json_write_survives_a_concurrent_reader(tmp_path):
    """A poller reading job.json while a worker thread updates it must not

    crash the writer -- the exact shape of a real bug report (Windows'
    MoveFileEx raising PermissionError/WinError 5 when the destination is
    momentarily open for reading by another thread; POSIX rename has no
    such restriction, so this only ever reproduces on Windows, but the
    retry it exercises is harmless everywhere).
    """
    target = tmp_path / "job.json"
    write_json_atomic(target, {"progress": 0})
    stop = threading.Event()
    errors: list[Exception] = []

    def reader() -> None:
        while not stop.is_set():
            read_json(target)  # a poller: failure is already tolerated (returns None)

    def writer() -> None:
        try:
            for progress in range(1, 60):
                write_json_atomic(target, {"progress": progress})
        except Exception as exc:  # pragma: no cover - asserted after joining
            errors.append(exc)

    reader_thread = threading.Thread(target=reader)
    writer_thread = threading.Thread(target=writer)
    reader_thread.start()
    writer_thread.start()
    writer_thread.join(timeout=10)
    stop.set()
    reader_thread.join(timeout=5)

    assert not writer_thread.is_alive()
    assert not errors
    assert read_json(target)["progress"] == 59
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_json_write_retries_permission_error_then_succeeds(tmp_path, monkeypatch):
    """Deterministic version of the race above: the first few replace()

    calls fail exactly the way Windows' transient lock does, then succeed
    -- verifies the retry loop itself, independent of real OS timing.
    """
    from pathlib import Path

    target = tmp_path / "job.json"
    calls = {"n": 0}
    real_replace = Path.replace

    def flaky_replace(self, dest):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise PermissionError(5, "Access is denied")
        return real_replace(self, dest)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    write_json_atomic(target, {"ok": True})

    assert calls["n"] == 4
    assert read_json(target) == {"ok": True}
    assert not list(tmp_path.glob("*.tmp"))


def test_atomic_json_write_reraises_after_exhausting_retries(tmp_path, monkeypatch):
    from pathlib import Path

    target = tmp_path / "job.json"

    def always_denied(self, dest):
        raise PermissionError(5, "Access is denied")

    monkeypatch.setattr(Path, "replace", always_denied)
    with pytest.raises(PermissionError):
        write_json_atomic(target, {"ok": True})

    # The failed temp file is cleaned up, not left behind forever.
    assert not list(tmp_path.glob("*.tmp"))
