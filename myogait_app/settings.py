"""Application settings.

Every value can be overridden with an environment variable so the same
code runs unchanged on a researcher's laptop and on the lab server.
Nothing here is specific to a site, a branding, or a patient population.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


def _env_str(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "").strip() or default)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _default_workspace_root() -> Path:
    """Workspace root, defaulting to a temp directory.

    Deliberately outside the source tree: the app stores nothing it is
    not prepared to delete, and a temp location makes that explicit.
    """
    return Path(tempfile.gettempdir()) / "myogait_app"


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the app."""

    # ── Storage ──────────────────────────────────────────────────────
    workspace_root: Path = field(default_factory=_default_workspace_root)
    #: How long a job ticket and its artefacts survive before purge.
    #: The app keeps no personal data beyond this window.
    retention_hours: int = 24
    #: Largest accepted upload, in megabytes. Must stay in sync with
    #: ``.streamlit/config.toml`` and with nginx ``client_max_body_size``.
    max_upload_mb: int = 2048
    #: Suggest the local watch directory above this browser-upload size.
    #: This is guidance, not a second hard upload limit.
    in_memory_warn_mb: int = 512

    # ── Jobs ─────────────────────────────────────────────────────────
    #: Concurrent extraction jobs. One today; raise when the server can
    #: take it — the queue itself needs no change.
    max_concurrent_jobs: int = 1
    #: A job that has produced no progress update for this long is
    #: considered dead and is reported as failed rather than running.
    job_stale_minutes: int = 120

    # ── Server-side input ────────────────────────────────────────────
    #: Optional directory the app may read videos from directly. Lets a
    #: 2 GB file be dropped over SMB or scp instead of pushed through
    #: the browser uploader, which is fragile at that size.
    watch_dir: Path | None = None
    #: Optional root containing local VICON trial directories. The standard
    #: experimental UI only lets the researcher select folders below it.
    vicon_root: Path | None = None

    # ── Behaviour ────────────────────────────────────────────────────
    #: Show the experimental VICON / AIM benchmark section.
    enable_experimental: bool = True
    #: Show the equivalent YAML config and Python snippet on every page.
    show_reproducibility: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        watch_raw = _env_str("MYOGAIT_APP_WATCH_DIR", "")
        vicon_raw = _env_str("MYOGAIT_APP_VICON_ROOT", "")
        return cls(
            workspace_root=Path(
                _env_str("MYOGAIT_APP_WORKSPACE", str(_default_workspace_root()))
            ),
            retention_hours=_env_int("MYOGAIT_APP_RETENTION_HOURS", 24),
            max_upload_mb=_env_int("MYOGAIT_APP_MAX_UPLOAD_MB", 2048),
            in_memory_warn_mb=_env_int("MYOGAIT_APP_INMEMORY_WARN_MB", 512),
            max_concurrent_jobs=_env_int("MYOGAIT_APP_MAX_JOBS", 1),
            job_stale_minutes=_env_int("MYOGAIT_APP_JOB_STALE_MINUTES", 120),
            watch_dir=Path(watch_raw) if watch_raw else None,
            vicon_root=Path(vicon_raw) if vicon_raw else None,
            enable_experimental=_env_bool("MYOGAIT_APP_EXPERIMENTAL", True),
            show_reproducibility=_env_bool("MYOGAIT_APP_SHOW_CODE", True),
        )

    @property
    def jobs_dir(self) -> Path:
        return self.workspace_root / "jobs"

    @property
    def sessions_dir(self) -> Path:
        return self.workspace_root / "sessions"

    def ensure_dirs(self) -> None:
        for path in (self.workspace_root, self.jobs_dir, self.sessions_dir):
            path.mkdir(parents=True, exist_ok=True)


SETTINGS = Settings.from_env()
