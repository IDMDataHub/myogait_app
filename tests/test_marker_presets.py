"""Caching contracts for C3D marker-preset helpers."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from myogait_app.marker_presets import _read_c3d_labels_cached, read_c3d_labels


def test_read_c3d_labels_reuses_an_unchanged_file_fingerprint(tmp_path, monkeypatch):
    calls: list[str] = []
    trial = tmp_path / "trial.c3d"
    trial.write_bytes(b"fixture")

    def fake_c3d(path: str) -> dict:
        calls.append(path)
        return {"parameters": {"POINT": {"LABELS": {"value": [" LASI ", "RASI"]}}}}

    _read_c3d_labels_cached.cache_clear()
    monkeypatch.setitem(sys.modules, "ezc3d", SimpleNamespace(c3d=fake_c3d))

    assert read_c3d_labels(trial) == ["LASI", "RASI"]
    assert read_c3d_labels(trial) == ["LASI", "RASI"]

    assert calls == [str(trial.resolve())]
