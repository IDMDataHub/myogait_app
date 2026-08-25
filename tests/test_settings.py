from __future__ import annotations

from myogait_app.settings import Settings


def test_settings_uses_defaults_for_invalid_integer_environment(monkeypatch):
    monkeypatch.setenv("MYOGAIT_APP_MAX_JOBS", "not-a-number")
    monkeypatch.setenv("MYOGAIT_APP_INMEMORY_WARN_MB", "128")

    settings = Settings.from_env()

    assert settings.max_concurrent_jobs == 1
    assert settings.in_memory_warn_mb == 128


def test_settings_reads_optional_local_roots(monkeypatch, tmp_path):
    vicon_root = tmp_path / "vicon"
    monkeypatch.setenv("MYOGAIT_APP_VICON_ROOT", str(vicon_root))

    assert Settings.from_env().vicon_root == vicon_root
