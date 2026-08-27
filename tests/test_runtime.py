from __future__ import annotations

import pytest

from myogait_app.runtime import Runtime, _version_tuple


def _runtime(version: str | None) -> Runtime:
    return Runtime(
        myogait_version=version,
        gaitkit_version=None,
        device="cpu",
        device_detail="test",
        onnx_providers=(),
        event_methods=(),
        angle_methods=(),
    )


@pytest.mark.parametrize(
    ("version", "expected"),
    [(None, False), ("0.8.1", False), ("0.8.2", True), ("0.9.0", True)],
)
def test_step_length_isotropic_version_gate(version, expected):
    assert _runtime(version).step_length_isotropic_native is expected


def test_version_parser_accepts_development_and_release_candidate_suffixes():
    assert _version_tuple("0.8.2.dev1") == (0, 8, 2)
    assert _version_tuple("1.0.0rc1") == (1, 0, 0)


def test_backend_availability_uses_one_shared_registry_probe(monkeypatch):
    import myogait_app.runtime as runtime_module

    calls = 0

    def fake_registry() -> dict[str, bool]:
        nonlocal calls
        calls += 1
        return {"mediapipe": True, "yolo": False}

    monkeypatch.setattr(runtime_module, "_myogait_backend_availability", fake_registry)

    availability = _runtime("0.8.2").backend_availability()

    assert calls == 1
    assert availability["mediapipe"] is True
    assert availability["yolo"] is False
