"""Session state.

Streamlit re-runs the whole script on every interaction, so anything that
must survive a widget change lives here. Two things matter enough to be
explicit about:

* the **source** (the extraction being explored) and the **config** (the
  parameters applied to it) are kept apart, because the whole point of
  the workbench is to vary the second while holding the first;
* the :class:`~myogait_app.pipeline.PipelineRunner` and its stage cache
  are stored per source, so moving a slider reuses the cached upstream
  stages instead of recomputing from the landmarks every rerun.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit as st

from ..pipeline import PipelineConfig, PipelineRunner
from ..settings import SETTINGS
from ..storage import Workspace, get_workspace

#: Session-state keys, named once so a typo is a NameError not a silent
#: second variable.
K_SOURCE = "mg_source"
K_CONFIG = "mg_config"
K_RUNNER = "mg_runner"
K_COMPARE = "mg_compare_results"
K_TICKETS = "mg_known_tickets"
K_LONGITUDINAL = "mg_longitudinal_sessions"


@dataclass
class Source:
    """The extraction currently loaded into the workbench."""

    kind: str  # demo | json | video | c3d
    name: str
    data: dict
    key: str
    model: str = "unknown"
    path: Path | None = None
    note: str = ""
    #: C3D-specific loading parameters (marker_mapping, axes, aspect-ratio
    #: fix, matched/missing landmarks) -- set only when kind == "c3d", so
    #: the reproducibility panel can regenerate the exact load_c3d call.
    c3d_options: dict | None = None
    #: ISB reconstruction inputs, decided once at load time -- see
    #: PipelineRunner.__init__'s docstring for the shape. None/empty for
    #: any non-ISB-capable source (unchanged behaviour). Not part of
    #: c3d_options: those are plain, JSON-safe metadata for the
    #: reproducibility panel, these carry raw numpy arrays and dataclass
    #: objects that have no business in a codegen'd snippet.
    isb_context: dict | None = None
    #: Small, display-only summary of isb_context's capability -- what
    #: marker_presets.resolve_isb_mapping (and, for tiers 2/3, whether a
    #: static/.vsk/.prot file was attached) found for this source. Kept
    #: separate from isb_context so the UI can show it without touching
    #: the raw calibration data.
    isb_diagnostics: dict | None = None

    @property
    def n_frames(self) -> int:
        return len(self.data.get("frames") or [])

    @property
    def fps(self) -> float:
        return float((self.data.get("meta") or {}).get("fps") or 30.0)

    @property
    def duration_s(self) -> float:
        return self.n_frames / self.fps if self.fps else 0.0

    @property
    def resolution(self) -> str:
        meta = self.data.get("meta") or {}
        width, height = meta.get("width"), meta.get("height")
        return f"{width}x{height}" if width and height else "unknown"

    @property
    def is_demo(self) -> bool:
        return self.kind == "demo"

    @property
    def is_c3d(self) -> bool:
        return self.kind == "c3d"


def source_key(name: str, payload: Any) -> str:
    """Stable identifier for a source, used as the cache root.

    Hashes the identity of the extraction rather than its full contents:
    digesting several hundred megabytes of landmarks on every rerun would
    cost more than the pipeline it is meant to protect.
    """
    digest = hashlib.sha256()
    digest.update(str(name).encode("utf-8"))
    digest.update(str(payload).encode("utf-8"))
    return digest.hexdigest()[:16]


def resolve_pivot_kind_and_path(data: dict, default_path: Path) -> tuple[str, Path]:
    """Whether a loaded pivot's own source video is still on disk here.

    Every pivot JSON that came from a video extraction, once loaded (by
    ticking it in Recent jobs and pressing Analyse, or via
    ``components.source_loader``/``recording_switcher``), used to install
    as ``kind="json"`` unconditionally -- the *only* two call sites that
    ever build a loaded ``Source`` (``page_data._load_pivot``,
    ``components._install_pivot``) never checked. That silently broke
    every video-dependent export (the skeleton overlay, and the new video
    report): both gate on ``source.kind == "video"``, a value nothing in
    the app ever actually produced through that path -- ``kind="video"``
    was previously only reachable, if at all, by constructing a ``Source``
    by hand.

    ``myogait.extract`` records the exact path it was given in
    ``data["meta"]["video_path"]``. When that file still exists on this
    machine (the ordinary case: loading a just-finished extraction in the
    same session/server that ran it), the pivot should behave as a video
    source. A pivot re-uploaded standalone, moved to a different machine,
    or sourced from C3D falls back to the pre-existing "json" kind with
    *default_path* (the pivot file's own path) -- unchanged behaviour.
    """
    meta = data.get("meta") or {}
    if str(meta.get("source") or "").lower() == "video":
        video_path = meta.get("video_path")
        if video_path:
            candidate = Path(str(video_path))
            if candidate.is_file():
                return "video", candidate
    return "json", default_path


def init() -> None:
    """Seed every key once per session."""
    st.session_state.setdefault(K_SOURCE, None)
    st.session_state.setdefault(K_CONFIG, PipelineConfig())
    st.session_state.setdefault(K_RUNNER, None)
    st.session_state.setdefault(K_COMPARE, {})
    st.session_state.setdefault(K_TICKETS, [])
    st.session_state.setdefault(K_LONGITUDINAL, [])


# ── Source ───────────────────────────────────────────────────────────


def get_source() -> Source | None:
    return st.session_state.get(K_SOURCE)


def set_source(source: Source) -> None:
    """Install a new source and drop the runner built for the old one."""
    current = st.session_state.get(K_SOURCE)
    st.session_state[K_SOURCE] = source
    if current is None or current.key != source.key:
        st.session_state[K_RUNNER] = None
        # Comparator results describe the previous extraction and would be
        # misleading next to a new one.
        st.session_state[K_COMPARE] = {}


def clear_source() -> None:
    st.session_state[K_SOURCE] = None
    st.session_state[K_RUNNER] = None
    st.session_state[K_COMPARE] = {}


def has_source() -> bool:
    return st.session_state.get(K_SOURCE) is not None


# ── Config ───────────────────────────────────────────────────────────


def get_config() -> PipelineConfig:
    return st.session_state.get(K_CONFIG) or PipelineConfig()


def set_config(config: PipelineConfig) -> None:
    st.session_state[K_CONFIG] = config


def reset_config() -> None:
    st.session_state[K_CONFIG] = PipelineConfig()


# ── Runner ───────────────────────────────────────────────────────────


def get_runner() -> PipelineRunner | None:
    """Return the runner for the current source, building it on demand."""
    source = get_source()
    if source is None:
        return None
    runner: PipelineRunner | None = st.session_state.get(K_RUNNER)
    if runner is None or runner.source_key != source.key:
        runner = PipelineRunner(source.data, source.key, isb_context=source.isb_context)
        st.session_state[K_RUNNER] = runner
    return runner


# ── Comparator ───────────────────────────────────────────────────────


def get_compare() -> dict:
    return st.session_state.get(K_COMPARE) or {}


def set_compare(results: dict) -> None:
    st.session_state[K_COMPARE] = results


# ── Longitudinal ─────────────────────────────────────────────────────


def get_longitudinal_sessions() -> list[dict]:
    return st.session_state.get(K_LONGITUDINAL) or []


def set_longitudinal_sessions(sessions: list[dict]) -> None:
    st.session_state[K_LONGITUDINAL] = sessions


# ── Job tickets ──────────────────────────────────────────────────────


def remember_ticket(ticket: str) -> None:
    """Keep tickets issued in this session, so they are one click away."""
    tickets: list[str] = st.session_state.get(K_TICKETS) or []
    if ticket not in tickets:
        tickets.insert(0, ticket)
    st.session_state[K_TICKETS] = tickets[:20]


def known_tickets() -> list[str]:
    return st.session_state.get(K_TICKETS) or []


# ── Workspace ────────────────────────────────────────────────────────


def workspace() -> Workspace:
    """The scratch directory for this browser session.

    Streamlit's per-session identifier is not part of the public API and
    has moved between releases, so it is read defensively and falls back
    to a stable per-session token.
    """
    session_id = st.session_state.get("_mg_session_id")
    if not session_id:
        try:
            from streamlit.runtime.scriptrunner import get_script_run_ctx

            ctx = get_script_run_ctx()
            session_id = getattr(ctx, "session_id", None)
        except Exception:
            session_id = None
        if not session_id:
            import uuid

            session_id = uuid.uuid4().hex
        st.session_state["_mg_session_id"] = session_id
    return get_workspace(str(session_id), SETTINGS)
