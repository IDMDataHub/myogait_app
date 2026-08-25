"""Storage behaviours that must remain safe for local research sessions."""

from __future__ import annotations

import io

from myogait_app.storage import Workspace, store_uploaded_file


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
