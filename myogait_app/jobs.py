"""Background extraction jobs.

Pose extraction on anything heavier than MediaPipe outlives a browser
session, so it cannot run inside a Streamlit script run. Jobs are pushed
to a worker pool and their state lives on disk, which buys two things:

* the user can close the tab and come back with a ticket;
* the UI polls a file rather than holding a future, so it keeps working
  across Streamlit reruns, which discard in-memory state constantly.

The pool is sized by ``Settings.max_concurrent_jobs`` -- one today.
Raising it is a configuration change, not a code change.

This module deliberately does not import Streamlit: it is the part that
must remain testable and runnable headless.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .settings import SETTINGS, Settings
from .storage import job_dir, new_ticket, read_json, write_json_atomic

logger = logging.getLogger(__name__)

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"

_TERMINAL = (DONE, FAILED, CANCELLED)


@dataclass
class Job:
    """A snapshot of one extraction job, as read from disk."""

    ticket: str
    status: str
    progress: float = 0.0
    message: str = ""
    video_name: str = ""
    model: str = ""
    params: dict = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0
    error: str = ""
    result_file: str = ""

    @property
    def finished(self) -> bool:
        return self.status in _TERMINAL

    @property
    def succeeded(self) -> bool:
        return self.status == DONE

    @property
    def age_seconds(self) -> float:
        return max(0.0, time.time() - self.created_at)

    @property
    def since_update_seconds(self) -> float:
        return max(0.0, time.time() - self.updated_at)

    def result_path(self, settings: Settings = SETTINGS) -> Path | None:
        if not self.result_file:
            return None
        candidate = job_dir(self.ticket, settings) / self.result_file
        return candidate if candidate.is_file() else None

    @classmethod
    def from_dict(cls, payload: dict) -> "Job":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in payload.items() if k in known})

    def to_dict(self) -> dict:
        return {
            "ticket": self.ticket,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "video_name": self.video_name,
            "model": self.model,
            "params": self.params,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "result_file": self.result_file,
        }


class JobManager:
    """Owns the worker pool and the on-disk job records."""

    def __init__(self, settings: Settings = SETTINGS) -> None:
        self.settings = settings
        settings.ensure_dirs()
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, settings.max_concurrent_jobs),
            thread_name_prefix="myogait-extract",
        )
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()

    # ── State access ─────────────────────────────────────────────────

    def _state_file(self, ticket: str) -> Path:
        return job_dir(ticket, self.settings) / "job.json"

    def _write(self, job: Job) -> None:
        job.updated_at = time.time()
        write_json_atomic(self._state_file(job.ticket), job.to_dict())

    def get(self, ticket: str) -> Job | None:
        """Read a job record, reconciling states the process cannot honour.

        A job left ``running`` with no progress update for longer than
        ``job_stale_minutes`` is reported as failed: the usual cause is
        the Streamlit server having been restarted under it, and showing
        an eternal spinner would be a lie.
        """
        try:
            payload = read_json(self._state_file(ticket))
        except ValueError:
            return None
        if not payload:
            return None

        job = Job.from_dict(payload)
        stale_after = self.settings.job_stale_minutes * 60
        if job.status == RUNNING and job.since_update_seconds > stale_after:
            job.status = FAILED
            job.error = (
                "No progress for "
                f"{int(job.since_update_seconds / 60)} min - the worker was "
                "most likely interrupted (server restart). Relaunch the extraction."
            )
            self._write(job)
        return job

    def list_jobs(self, limit: int = 50) -> list[Job]:
        """Most recent jobs first."""
        if not self.settings.jobs_dir.is_dir():
            return []
        jobs: list[Job] = []
        for entry in self.settings.jobs_dir.iterdir():
            if not entry.is_dir():
                continue
            payload = read_json(entry / "job.json")
            if payload:
                jobs.append(Job.from_dict(payload))
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs[:limit]

    def active_count(self) -> int:
        return sum(1 for job in self.list_jobs() if job.status in (QUEUED, RUNNING))

    def cancel(self, ticket: str) -> bool:
        """Ask a job to stop at its next progress callback.

        Cooperative rather than forced: myogait offers no interruption
        point beyond the progress callback, and killing a thread mid-write
        would leave a corrupt result file.
        """
        job = self.get(ticket)
        if job is None or job.finished:
            return False
        with self._lock:
            self._cancelled.add(ticket)
        job.message = "Cancellation requested..."
        self._write(job)
        return True

    def _is_cancelled(self, ticket: str) -> bool:
        with self._lock:
            return ticket in self._cancelled

    # ── Submission ───────────────────────────────────────────────────

    def submit(
        self,
        video_path: Path,
        model: str,
        extract_kwargs: dict[str, Any] | None = None,
        video_name: str = "",
    ) -> str:
        """Queue an extraction and return its ticket."""
        ticket = new_ticket()
        directory = job_dir(ticket, self.settings)
        directory.mkdir(parents=True, exist_ok=True)

        job = Job(
            ticket=ticket,
            status=QUEUED,
            video_name=video_name or Path(video_path).name,
            model=model,
            params=dict(extract_kwargs or {}),
            created_at=time.time(),
            message="Waiting for a free worker...",
        )
        self._write(job)

        self._pool.submit(
            self._run, ticket, Path(video_path), model, dict(extract_kwargs or {})
        )
        return ticket

    # ── Worker ───────────────────────────────────────────────────────

    def _run(
        self, ticket: str, video_path: Path, model: str, extract_kwargs: dict
    ) -> None:
        job = self.get(ticket)
        if job is None:
            return

        if self._is_cancelled(ticket):
            job.status = CANCELLED
            job.message = "Cancelled before starting."
            self._write(job)
            return

        job.status = RUNNING
        job.progress = 0.0
        job.message = f"Extracting with {model}..."
        self._write(job)

        last_flush = 0.0

        def on_progress(fraction: float) -> None:
            """Persist progress, throttled to avoid hammering the disk."""
            nonlocal last_flush
            if self._is_cancelled(ticket):
                raise _JobCancelled()
            now = time.time()
            # myogait can call this once per frame; a 25 fps 3-minute clip
            # would otherwise mean 4500 disk writes.
            if now - last_flush < 0.5 and fraction < 1.0:
                return
            last_flush = now
            job.progress = float(max(0.0, min(1.0, fraction)))
            job.message = f"Extracting with {model} - {job.progress:.0%}"
            self._write(job)

        try:
            from myogait import extract
            from myogait.schema import save_json

            data = extract(
                str(video_path),
                model=model,
                progress_callback=on_progress,
                show_progress=False,
                **extract_kwargs,
            )

            result_file = "result.json"
            save_json(data, str(job_dir(ticket, self.settings) / result_file))

            job.status = DONE
            job.progress = 1.0
            job.result_file = result_file
            n_frames = len(data.get("frames", []))
            job.message = f"Extraction complete - {n_frames} frames."
            self._write(job)

        except _JobCancelled:
            job.status = CANCELLED
            job.message = "Cancelled."
            self._write(job)
        except Exception as exc:  # noqa: BLE001 - surfaced to the user verbatim
            logger.exception("Extraction job %s failed", ticket)
            job.status = FAILED
            job.error = f"{type(exc).__name__}: {exc}"
            job.message = "Extraction failed."
            try:
                (job_dir(ticket, self.settings) / "traceback.txt").write_text(
                    traceback.format_exc(), encoding="utf-8"
                )
            except OSError:
                pass
            self._write(job)
        finally:
            with self._lock:
                self._cancelled.discard(ticket)


class _JobCancelled(Exception):
    """Raised inside the progress callback to unwind a cancelled job."""
