"""Ephemeral workspaces and recoverable job tickets.

The app keeps nothing by design: a browser session gets a scratch
directory that dies with it, and the only thing that outlives a session
is a *job ticket* -- the pointer to a long extraction that may still be
running when the user closes the tab.

Both are purged on a fixed clock (``Settings.retention_hours``). Purging
runs at startup and on every visit to a page that touches storage, so an
app that is used regularly never accumulates video files, and an app that
is left idle is cleaned the next time anyone opens it.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .settings import SETTINGS, Settings

#: Ticket alphabet without characters that are ambiguous when read aloud
#: or copied by hand (no O/0, no I/1).
_TICKET_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_TICKET_RE = re.compile(r"^MG-[A-Z2-9]{4}-[A-Z2-9]{4}$")

#: Written next to a workspace so the purge knows when it was last used
#: rather than when it was created -- an analysis session open for hours
#: should not be deleted underneath the user.
_TOUCH_FILE = ".last_seen"


def new_ticket() -> str:
    """Return a fresh, human-transcribable job ticket."""
    left = "".join(secrets.choice(_TICKET_ALPHABET) for _ in range(4))
    right = "".join(secrets.choice(_TICKET_ALPHABET) for _ in range(4))
    return f"MG-{left}-{right}"


def is_ticket(value: str) -> bool:
    """True when *value* has the shape of a ticket.

    Validated before it is ever used to build a path, so a crafted string
    cannot escape the jobs directory.
    """
    return bool(_TICKET_RE.match(str(value).strip().upper()))


def write_json_atomic(path: Path, payload: Any) -> None:
    """Write JSON so a concurrent reader never sees a half-written file.

    The extraction worker updates progress from a background thread while
    the UI thread polls it; a plain write would occasionally be read
    mid-flush and raise a decode error.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    tmp.replace(path)


def read_json(path: Path) -> Any | None:
    """Read JSON, returning None on any failure.

    Callers are polling files written by another thread, so a transient
    failure is expected and is not worth an exception.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


@dataclass(frozen=True)
class Workspace:
    """A scratch directory bound to one browser session."""

    session_id: str
    root: Path

    @property
    def uploads(self) -> Path:
        return self.root / "uploads"

    @property
    def outputs(self) -> Path:
        return self.root / "outputs"

    def ensure(self) -> "Workspace":
        for path in (self.root, self.uploads, self.outputs):
            path.mkdir(parents=True, exist_ok=True)
        self.touch()
        return self

    def touch(self) -> None:
        """Mark the workspace as still in use."""
        try:
            (self.root / _TOUCH_FILE).write_text(str(time.time()), encoding="utf-8")
        except OSError:
            pass

    def path_for(self, filename: str) -> Path:
        """Return a path inside the workspace for *filename*.

        The name is reduced to its stem so an uploaded file cannot write
        outside the workspace through a crafted path.
        """
        safe = Path(str(filename)).name or "file"
        return self.uploads / safe

    def size_bytes(self) -> int:
        return sum(f.stat().st_size for f in self.root.rglob("*") if f.is_file())

    def clear(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)


def get_workspace(session_id: str, settings: Settings = SETTINGS) -> Workspace:
    """Return (and create) the workspace for *session_id*."""
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(session_id))[:64] or "anonymous"
    settings.ensure_dirs()
    return Workspace(session_id=safe, root=settings.sessions_dir / safe).ensure()


def job_dir(ticket: str, settings: Settings = SETTINGS) -> Path:
    """Return the directory backing *ticket*.

    Raises
    ------
    ValueError
        If *ticket* is not a well-formed ticket. Guards path traversal.
    """
    normalised = str(ticket).strip().upper()
    if not is_ticket(normalised):
        raise ValueError(f"Malformed job ticket: {ticket!r}")
    return settings.jobs_dir / normalised


def _age_seconds(path: Path) -> float:
    """Age of *path*, preferring the touch file when one exists."""
    touch = path / _TOUCH_FILE
    try:
        if touch.is_file():
            return time.time() - float(touch.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pass
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return 0.0


def _expired_dirs(parent: Path, max_age: float) -> Iterator[Path]:
    if not parent.is_dir():
        return
    for child in parent.iterdir():
        if child.is_dir() and _age_seconds(child) > max_age:
            yield child


def purge_expired(settings: Settings = SETTINGS) -> dict:
    """Delete workspaces and job tickets past the retention window.

    Returns a small report so the interface can state plainly what was
    removed rather than deleting silently.
    """
    settings.ensure_dirs()
    max_age = settings.retention_hours * 3600
    removed_sessions = 0
    removed_jobs = 0
    freed_bytes = 0

    for directory, counter in (
        (settings.sessions_dir, "sessions"),
        (settings.jobs_dir, "jobs"),
    ):
        for stale in list(_expired_dirs(directory, max_age)):
            try:
                freed_bytes += sum(
                    f.stat().st_size for f in stale.rglob("*") if f.is_file()
                )
            except OSError:
                pass
            shutil.rmtree(stale, ignore_errors=True)
            if counter == "sessions":
                removed_sessions += 1
            else:
                removed_jobs += 1

    return {
        "sessions_removed": removed_sessions,
        "jobs_removed": removed_jobs,
        "freed_mb": round(freed_bytes / (1024 * 1024), 1),
        "retention_hours": settings.retention_hours,
    }


def workspace_usage(settings: Settings = SETTINGS) -> dict:
    """Total footprint of the workspace root, for the storage banner."""
    settings.ensure_dirs()
    total = 0
    for path in settings.workspace_root.rglob("*"):
        if path.is_file():
            try:
                total += path.stat().st_size
            except OSError:
                pass
    n_jobs = sum(1 for p in settings.jobs_dir.iterdir() if p.is_dir()) if settings.jobs_dir.is_dir() else 0
    n_sessions = (
        sum(1 for p in settings.sessions_dir.iterdir() if p.is_dir())
        if settings.sessions_dir.is_dir()
        else 0
    )
    return {
        "total_mb": round(total / (1024 * 1024), 1),
        "n_jobs": n_jobs,
        "n_sessions": n_sessions,
    }
