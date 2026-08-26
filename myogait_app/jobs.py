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
import os
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .runtime import DEVICE_OVERRIDE_ENV
from .settings import SETTINGS, Settings
from .storage import is_ticket, job_dir, new_ticket, read_json, write_json_atomic

logger = logging.getLogger(__name__)

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"

_TERMINAL = (DONE, FAILED, CANCELLED)

#: Env vars are process-global, so two concurrent jobs with different
#: device overrides would clobber each other's setting. Serialising on
#: this lock is a non-issue at the default MYOGAIT_APP_MAX_JOBS=1; at a
#: higher setting, jobs with an explicit override queue briefly at
#: start rather than racing -- correct, if not maximally parallel.
_device_env_lock = threading.Lock()


@contextmanager
def _device_env(choice: str):
    """Temporarily set the env vars that steer myogait's device pick.

    myogait exposes no device parameter of its own -- every backend
    hardcodes ``torch.cuda.is_available() > xpu > cpu`` internally (see
    ``runtime.DEVICE_OVERRIDE_ENV``'s docstring). "auto" is a no-op:
    myogait's own detection already runs. Known limitation, stated in
    the Data page: once CUDA has initialised once in this long-lived
    server process, PyTorch caches that fact, so forcing "cpu" on a
    later job may not take effect without restarting the app.
    """
    overrides = DEVICE_OVERRIDE_ENV.get(choice, {})
    if not overrides:
        yield
        return
    with _device_env_lock:
        previous = {key: os.environ.get(key) for key in overrides}
        os.environ.update(overrides)
        try:
            yield
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


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
    #: Free-form study identifiers (patient ID, run, group, experiment)
    #: written into the extracted pivot under ``data["study"]`` so a pooled
    #: multi-recording analysis can group and label every output JSON.
    study: dict = field(default_factory=dict)
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
        """Return a result only when it is a direct file of this job directory."""
        if not self.result_file:
            return None
        root = job_dir(self.ticket, settings).resolve()
        try:
            candidate = (root / self.result_file).resolve()
        except OSError:
            return None
        if candidate.parent != root:
            return None
        return candidate if candidate.is_file() else None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Job":
        """Build a job only from a structurally valid on-disk record.

        Job files are polled while another thread replaces them atomically, but
        they can still be edited or damaged outside the app. Rejecting malformed
        records lets the Jobs page skip one bad directory rather than crashing.
        """
        if not isinstance(payload, Mapping):
            raise ValueError("Job record must be an object")
        ticket = payload.get("ticket")
        status = payload.get("status")
        if not isinstance(ticket, str) or not is_ticket(ticket):
            raise ValueError("Job record has an invalid ticket")
        if status not in (QUEUED, RUNNING, DONE, FAILED, CANCELLED):
            raise ValueError("Job record has an invalid status")
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
            "study": self.study,
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
        self._reconcile_orphans()

    def _reconcile_orphans(self) -> None:
        """Fail jobs left ``running``/``queued`` by a previous server process.

        A freshly created manager owns no in-flight work (its pool is empty),
        so any job still marked active on disk is an orphan from an earlier
        process -- e.g. the server was restarted mid-extraction. Left as-is it
        would block a new extraction (the one-at-a-time guard counts it) and
        show an eternal progress bar. Marking it failed clears both.
        """
        directory = self.settings.jobs_dir
        if not directory.is_dir():
            return
        try:
            entries = list(directory.iterdir())
        except OSError:
            return
        for entry in entries:
            if not entry.is_dir():
                continue
            payload = read_json(entry / "job.json")
            if not isinstance(payload, Mapping) or payload.get("status") not in (QUEUED, RUNNING):
                continue
            payload["status"] = FAILED
            payload["error"] = "Interrupted by a server restart - relaunch the extraction."
            payload["updated_at"] = time.time()
            try:
                write_json_atomic(entry / "job.json", payload)
            except OSError:
                pass

    # ── State access ─────────────────────────────────────────────────

    def _state_file(self, ticket: str) -> Path:
        return job_dir(ticket, self.settings) / "job.json"

    def _write(self, job: Job) -> bool:
        """Persist a state update without reviving an already terminal job.

        A stale worker can still return after the UI has marked its on-disk job
        failed. Reading the current record first prevents that late worker from
        overwriting ``failed`` or ``cancelled`` with ``done``.
        """
        state_file = self._state_file(job.ticket)
        existing = read_json(state_file)
        existing_status = existing.get("status") if isinstance(existing, Mapping) else None
        if existing_status in _TERMINAL and existing_status != job.status:
            return False
        job.updated_at = time.time()
        write_json_atomic(state_file, job.to_dict())
        return True

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

        try:
            job = Job.from_dict(payload)
        except (TypeError, ValueError):
            return None
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
            if not payload:
                continue
            try:
                jobs.append(Job.from_dict(payload))
            except (TypeError, ValueError):
                logger.warning("Ignoring malformed job record: %s", entry / "job.json")
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
        study: dict[str, Any] | None = None,
        device_override: str = "auto",
    ) -> str:
        """Queue an extraction and return its ticket.

        ``device_override`` steers myogait's own cuda>xpu>cpu
        auto-detection (see ``runtime.DEVICE_OVERRIDE_ENV``) -- it is
        applied as environment variables around the call, never passed
        as a kwarg to ``myogait.extract`` itself, since several
        extractors (MediaPipe's constructor, notably) accept no
        ``**kwargs`` at all and would raise ``TypeError`` on an unknown
        one.
        """
        ticket = new_ticket()
        directory = job_dir(ticket, self.settings)
        directory.mkdir(parents=True, exist_ok=True)

        job = Job(
            ticket=ticket,
            status=QUEUED,
            video_name=video_name or Path(video_path).name,
            model=model,
            params=dict(extract_kwargs or {}, device_override=device_override),
            study={k: v for k, v in (study or {}).items() if v not in (None, "")},
            created_at=time.time(),
            message="Waiting for a free worker...",
        )
        self._write(job)

        self._pool.submit(
            self._run,
            ticket,
            Path(video_path),
            model,
            dict(extract_kwargs or {}),
            device_override,
        )
        return ticket

    # ── Worker ───────────────────────────────────────────────────────

    def _run(
        self,
        ticket: str,
        video_path: Path,
        model: str,
        extract_kwargs: dict,
        device_override: str = "auto",
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

            from .runtime import (
                SAPIENS2_SIZES,
                sapiens2_seg_weights_ready,
                sapiens2_weights_ready,
            )

            with _device_env(device_override):
                # Sapiens 2's one-time trace (torch.jit.trace, inside
                # _fetch_sapiens2_weights) must run under the same device
                # override as extraction itself -- tracing on a backend
                # missing a required op (seen on Intel XPU: aten::empty.
                # memory_format has no XPU kernel in this torch build)
                # fails exactly the way extraction on that device would,
                # and "Force CPU" is the user's only escape hatch for it.
                if model in SAPIENS2_SIZES:
                    size = SAPIENS2_SIZES[model]
                    if not sapiens2_weights_ready(model):
                        self._fetch_sapiens2_weights(job, ticket, size, kind="pose")
                    # with_seg loads a second, independently-cached model
                    # file -- see _fetch_sapiens2_weights' docstring for
                    # how this was discovered.
                    if extract_kwargs.get("with_seg") and not sapiens2_seg_weights_ready(model):
                        self._fetch_sapiens2_weights(job, ticket, size, kind="seg")

                data = extract(
                    str(video_path),
                    model=model,
                    progress_callback=on_progress,
                    show_progress=False,
                    **extract_kwargs,
                )

            # Study identifiers travel with the pivot so a pooled,
            # multi-recording analysis can group and label each output JSON.
            if job.study:
                data["study"] = dict(job.study)

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

    # ── Sapiens 2 weight fetch (inline, no separate action) ─────────────

    def _fetch_sapiens2_weights(
        self, job: Job, ticket: str, size: str, kind: str = "pose"
    ) -> None:
        """Download + trace one Sapiens 2 model file, as part of *this* job.

        ``kind`` is ``"pose"`` or ``"seg"`` -- myogait's ``with_seg=True``
        option loads a completely separate cached file
        (``sapiens2_{size}_seg.*``) from the pose model
        (``sapiens2_{size}_pose.*``), independently downloaded and traced.
        Discovered live: fetching only the pose file let a size whose
        segmentation weights existed solely as ``.safetensors`` through as
        "ready" (see ``runtime.sapiens2_seg_weights_ready``), and picking
        it with segmentation on hit the exact same "needs Meta's sapiens
        package" ``ImportError`` this function exists to prevent -- so
        ``_run`` calls this once per model file actually needed, not once
        per backend.

        No separate setup step for the user to trigger first: myogait's
        own finder already downloads on first use regardless, so skipping
        this would not skip the download -- only the progress messaging
        around it, leaving the job's progress bar sitting at 0% for
        however long a multi-gigabyte fetch takes with no explanation.
        Runs once per (size, kind) (the same fetch as ``myogait
        setup-sapiens2`` for the pose case, minus the CLI's cleanup/
        uninstall flags, which had no UI control asking for them here);
        every later extraction needing the same file finds it cached via
        ``sapiens2_weights_ready``/``sapiens2_seg_weights_ready`` and
        skips straight past this.
        """
        import importlib.util
        import subprocess
        import sys

        if self._is_cancelled(ticket):
            raise _JobCancelled()

        label = "segmentation" if kind == "seg" else "pose"
        job.progress = 0.02
        job.message = (
            f"Sapiens 2 {size} {label}: one-time weight fetch before this "
            "extraction can start..."
        )
        self._write(job)

        if importlib.util.find_spec("sapiens") is None:
            job.progress = 0.05
            job.message = "Installing Meta's sapiens package from GitHub..."
            self._write(job)
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "git+https://github.com/facebookresearch/sapiens2.git",
            ])
            importlib.invalidate_caches()

        if self._is_cancelled(ticket):
            raise _JobCancelled()

        job.progress = 0.15
        job.message = f"Downloading Sapiens 2 {size} {label} weights (several GB)..."
        self._write(job)

        from myogait.models.sapiens2 import _get_device, _load_model

        if kind == "seg":
            from myogait.models.sapiens2_seg import _find_seg_model

            weights_path = _find_seg_model(size)
        else:
            from myogait.models.sapiens2 import _find_model

            weights_path = _find_model(size)
        device = _get_device()

        if self._is_cancelled(ticket):
            raise _JobCancelled()

        job.progress = 0.35
        job.message = f"Tracing on {device} (one-time, can take 1-3 min)..."
        self._write(job)

        try:
            traced = _load_model(weights_path, device)
            del traced
        except Exception as exc:
            device_str = str(device)
            if device_str != "cpu":
                raise RuntimeError(
                    f"Tracing Sapiens 2 {size} {label} failed on {device_str}: "
                    f"{type(exc).__name__}: {exc}\n\n"
                    "This can be a missing op for this device in the "
                    "installed PyTorch build (seen on Intel XPU: "
                    "aten::empty.memory_format has no XPU kernel here) -- "
                    "CPU supports every op, if slower. Retry this "
                    "extraction with the Data page's Compute device set to "
                    "\"Force CPU\"."
                ) from exc
            raise

        job.progress = 0.4
        job.message = f"Sapiens 2 {size} {label} ready..."
        self._write(job)


class _JobCancelled(Exception):
    """Raised inside the progress callback to unwind a cancelled job."""
