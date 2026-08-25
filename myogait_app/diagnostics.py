"""Local runtime diagnostics for installation and support."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .runtime import Runtime, get_runtime
from .settings import SETTINGS, Settings


def _path_status(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"configured": False}
    candidate = Path(path)
    return {
        "configured": True,
        "path": str(candidate),
        "exists": candidate.exists(),
        "is_directory": candidate.is_dir(),
        "readable": os.access(candidate, os.R_OK),
        "writable": os.access(candidate, os.W_OK),
    }


def build_diagnostic(
    settings: Settings = SETTINGS, runtime: Runtime | None = None
) -> dict[str, Any]:
    """Return JSON-safe local installation diagnostics without patient data."""
    runtime = runtime or get_runtime()
    settings.ensure_dirs()
    disk = shutil.disk_usage(settings.workspace_root)
    return {
        "workspace": {
            **_path_status(settings.workspace_root),
            "free_mb": round(disk.free / (1024 * 1024), 1),
            "total_mb": round(disk.total / (1024 * 1024), 1),
        },
        "watch_dir": _path_status(settings.watch_dir),
        "vicon_root": _path_status(settings.vicon_root),
        "runtime": {
            "myogait_version": runtime.myogait_version,
            "gaitkit_version": runtime.gaitkit_version,
            "device": runtime.device,
            "device_detail": runtime.device_detail,
            "accelerated": runtime.accelerated,
            "available_backends": [backend.name for backend in runtime.available_backends],
            "warnings": list(runtime.warnings),
        },
        "settings": {
            "retention_hours": settings.retention_hours,
            "max_upload_mb": settings.max_upload_mb,
            "max_concurrent_jobs": settings.max_concurrent_jobs,
        },
    }
