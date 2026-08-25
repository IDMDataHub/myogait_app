"""Machine-readable provenance attached to locally generated exports."""

from __future__ import annotations

from datetime import datetime, timezone
import platform
import sys
from pathlib import Path
from typing import Any

from .pipeline import PipelineConfig
from .runtime import Runtime, get_runtime
from .storage import write_json_atomic


def build_provenance(
    config: PipelineConfig,
    runtime: Runtime | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Return the environment and pipeline state needed to reproduce an export."""
    runtime = runtime or get_runtime()
    timestamp = created_at or datetime.now(timezone.utc)
    return {
        "schema_version": 1,
        "created_at": timestamp.isoformat(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {
            "myogait": runtime.myogait_version,
            "gaitkit": runtime.gaitkit_version,
        },
        "pipeline_config": config.to_dict(),
    }


def write_provenance(path: Path, config: PipelineConfig) -> Path:
    """Write a sidecar provenance JSON and return its path."""
    write_json_atomic(path, build_provenance(config))
    return path
