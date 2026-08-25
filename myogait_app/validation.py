"""Lightweight structural validation for myogait pivot data."""

from __future__ import annotations

import math
from typing import Any


def validate_pivot(data: Any) -> list[str]:
    """Return user-actionable structural errors for a loaded pivot."""
    if not isinstance(data, dict):
        return ["The pivot root must be a JSON object."]

    frames = data.get("frames")
    if not isinstance(frames, list) or not frames:
        return ["The pivot must contain a non-empty 'frames' list."]

    meta = data.get("meta")
    if meta is not None and not isinstance(meta, dict):
        return ["'meta' must be an object when present."]
    if isinstance(meta, dict) and "fps" in meta:
        try:
            fps = float(meta["fps"])
            if not math.isfinite(fps) or fps <= 0:
                return ["'meta.fps' must be a finite positive number."]
        except (TypeError, ValueError):
            return ["'meta.fps' must be a finite positive number."]

    for index, frame in enumerate(frames):
        if not isinstance(frame, dict):
            return [f"Frame {index} must be an object."]
        landmarks = frame.get("landmarks")
        if landmarks is not None and not isinstance(landmarks, dict):
            return [f"Frame {index} has a non-object 'landmarks' field."]
    return []
