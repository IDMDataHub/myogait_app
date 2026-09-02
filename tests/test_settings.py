from __future__ import annotations

import re
from pathlib import Path

from myogait_app.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_settings_rejects_values_below_their_supported_minimum(monkeypatch):
    monkeypatch.setenv("MYOGAIT_APP_RETENTION_HOURS", "0")
    monkeypatch.setenv("MYOGAIT_APP_MAX_UPLOAD_MB", "-1")
    monkeypatch.setenv("MYOGAIT_APP_INMEMORY_WARN_MB", "-1")
    monkeypatch.setenv("MYOGAIT_APP_MAX_JOBS", "0")
    monkeypatch.setenv("MYOGAIT_APP_JOB_STALE_MINUTES", "-1")

    settings = Settings.from_env()

    assert settings.retention_hours == 24
    assert settings.max_upload_mb == 2048
    assert settings.in_memory_warn_mb == 512
    assert settings.max_concurrent_jobs == 1
    assert settings.job_stale_minutes == 120


def test_upload_limit_stays_in_sync_across_settings_streamlit_and_nginx():
    """Three independent files must agree on the upload ceiling (CLAUDE.md's
    own "three places that must stay in sync" note): Settings.max_upload_mb,
    .streamlit/config.toml's maxUploadSize, and nginx's client_max_body_size.
    A drift here used to only ever surface as a generic HTTP 413 on a video
    upload, with nothing connecting that symptom back to these three files.

    Read by regex rather than a full TOML parser -- the project has no TOML
    dependency yet and this only ever needs one integer out of one line.

    Uses ``Settings()``'s own dataclass default, not ``from_env()`` -- an
    environment variable override in the machine running this test would
    otherwise make the comparison meaningless.
    """
    default_upload_mb = Settings().max_upload_mb

    streamlit_config = (REPO_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    streamlit_match = re.search(r"^maxUploadSize\s*=\s*(\d+)", streamlit_config, re.MULTILINE)
    assert streamlit_match, "maxUploadSize not found in .streamlit/config.toml"
    assert int(streamlit_match.group(1)) == default_upload_mb

    nginx_config = (REPO_ROOT / "deploy" / "nginx-location.conf").read_text(encoding="utf-8")
    nginx_match = re.search(r"client_max_body_size\s+(\d+)m;", nginx_config)
    assert nginx_match, "client_max_body_size not found in deploy/nginx-location.conf"
    assert int(nginx_match.group(1)) == default_upload_mb
