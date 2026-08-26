"""Tests for browser-upload pivot loading without Streamlit."""

from __future__ import annotations

import io
from pathlib import Path

from myogait_app.pivot_io import load_uploaded_pivot
from myogait_app.storage import Workspace


def test_load_uploaded_pivot_persists_the_stream_before_loading(tmp_path) -> None:
    workspace = Workspace("test", tmp_path / "session").ensure()
    seen: list[str] = []

    def loader(path: str) -> dict:
        seen.append(path)
        return {"meta": {"fps": 30}, "frames": []}

    result = load_uploaded_pivot(
        workspace, io.BytesIO(b'{"meta": {}, "frames": []}'), "visit.json", loader
    )

    assert result["frames"] == []
    assert len(seen) == 1
    stored = workspace.uploads / Path(seen[0]).name
    assert stored.is_file()
    assert stored.read_bytes() == b'{"meta": {}, "frames": []}'
