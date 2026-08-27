"""Machine-readable provenance attached to locally generated exports."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import platform
import sys
from pathlib import Path
from typing import Any

from .pipeline import PipelineConfig
from .quality import QualityAssessment, assess_quality
from .runtime import Runtime, get_runtime
from .storage import write_json_atomic


def build_provenance(
    config: PipelineConfig,
    runtime: Runtime | None = None,
    created_at: datetime | None = None,
    source_data: dict | None = None,
    source_key: str | None = None,
    source_kind: str | None = None,
    model: str | None = None,
    quality: QualityAssessment | None = None,
) -> dict[str, Any]:
    """Return the environment and pipeline state needed to reproduce an export."""
    runtime = runtime or get_runtime()
    timestamp = created_at or datetime.now(timezone.utc)
    assessment = quality or assess_quality(source_data, None)
    return {
        "schema_version": 2,
        "created_at": timestamp.isoformat(),
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {
            "myogait": runtime.myogait_version,
            "gaitkit": runtime.gaitkit_version,
        },
        "pipeline_config": config.to_dict(),
        "input": {
            "source_key": source_key,
            "kind": source_kind,
            "model": model,
            "sha256": fingerprint_pivot(source_data) if source_data is not None else None,
        },
        "quality_assessment": assessment.to_dict(),
    }


def fingerprint_pivot(data: dict) -> str:
    """Return a content fingerprint without writing source or patient data."""
    encoded = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=True,
        default=_json_value,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _json_value(value: Any) -> Any:
    """Convert common numerical containers while keeping fingerprints stable."""
    if hasattr(value, "tolist"):
        return value.tolist()
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Unsupported value in pivot fingerprint: {type(value).__name__}")


def write_provenance(
    path: Path,
    config: PipelineConfig,
    **context: Any,
) -> Path:
    """Write a sidecar provenance JSON and return its path."""
    write_json_atomic(path, build_provenance(config, **context))
    return path
