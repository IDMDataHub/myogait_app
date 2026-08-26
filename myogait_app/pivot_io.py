"""Safe bridge between browser uploads and myogait pivot readers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .storage import Workspace, store_uploaded_file


def load_uploaded_pivot(
    workspace: Workspace,
    upload: Any,
    original_name: str,
    loader: Callable[[str], dict] | None = None,
) -> dict:
    """Persist an uploaded pivot and load it through myogait's path-based API.

    ``myogait.load_json`` deliberately accepts filesystem paths, not browser
    streams. Keeping that boundary here avoids every Streamlit page inventing
    a subtly different upload-to-path workaround. ``loader`` is injectable
    solely for tests.
    """
    target = store_uploaded_file(workspace, upload, original_name)
    if loader is None:
        from myogait import load_json as loader
    return loader(str(target))
