"""Getting data into the workbench.

Four ways in, in ascending order of cost: the synthetic dataset, a pivot
JSON, a video already sitting on the server, and a browser upload. The
last two run extraction as a background job and hand back a ticket,
because anything heavier than MediaPipe outlives the browser session.
"""

from __future__ import annotations

import time
from pathlib import Path

import streamlit as st

from ..demo import DEMO_PRESETS, make_demo_data
from ..jobs import DONE, FAILED, JobManager, RUNNING
from ..runtime import SAPIENS_BACKENDS, get_runtime
from ..settings import SETTINGS
from ..storage import is_ticket
from . import state
from .components import (
    empty_state,
    page_header,
    runtime_badge,
    source_summary,
    storage_banner,
)

#: Extensions myogait can open.
VIDEO_TYPES = ["mp4", "mov", "avi", "mkv", "m4v"]


@st.cache_resource
def job_manager() -> JobManager:
    """One pool per server process, surviving Streamlit reruns."""
    return JobManager(SETTINGS)


def render() -> None:
    page_header(
        "Data",
        "Load an extraction to explore, or run a new one. Nothing is stored "
        f"beyond {SETTINGS.retention_hours} hours.",
    )

    source = state.get_source()
    if source is not None:
        st.success(f"Loaded: **{source.name}** ({source.kind})")
        source_summary(source)
        if st.button("Unload"):
            state.clear_source()
            st.rerun()
        st.divider()

    tab_demo, tab_json, tab_video, tab_ticket = st.tabs(
        ["Synthetic data", "Pivot JSON", "Video -> extraction", "Recover a job"]
    )

    with tab_demo:
        _demo_tab()
    with tab_json:
        _json_tab()
    with tab_video:
        _video_tab()
    with tab_ticket:
        _ticket_tab()

    st.divider()
    storage_banner()


# ── Synthetic ────────────────────────────────────────────────────────


def _demo_tab() -> None:
    st.caption(
        "A generated gait-like signal. It exists so every control can be "
        "exercised before a real recording is committed to the app - and so the "
        "app can be tested without one."
    )
    preset_name = st.selectbox("Preset", list(DEMO_PRESETS))
    preset = DEMO_PRESETS[preset_name]
    st.info(preset["note"])

    columns = st.columns(2)
    n_frames = columns[0].slider("Frames", 100, 1200, 300, 50)
    fps = columns[1].select_slider("Frame rate", [25.0, 30.0, 50.0, 60.0], value=30.0)

    if st.button("Load synthetic dataset", type="primary", use_container_width=True):
        parameters = {k: v for k, v in preset.items() if k != "note"}
        data = make_demo_data(n_frames=n_frames, fps=fps, **parameters)
        state.set_source(
            state.Source(
                kind="demo",
                name=f"{preset_name} ({n_frames} frames)",
                data=data,
                key=state.source_key(preset_name, (n_frames, fps, tuple(sorted(parameters.items())))),
                model="synthetic",
                note=preset["note"],
            )
        )
        st.rerun()


# ── Pivot JSON ───────────────────────────────────────────────────────


def _json_tab() -> None:
    st.caption(
        "The fastest route: extraction is the expensive half, so a pivot file "
        "produced earlier by the CLI lets the whole downstream pipeline be "
        "explored instantly."
    )
    uploaded = st.file_uploader("myogait pivot JSON", type=["json"], key="json_upload")

    if uploaded is not None and st.button(
        "Load JSON", type="primary", use_container_width=True
    ):
        workspace = state.workspace()
        target = workspace.path_for(uploaded.name)
        target.write_bytes(uploaded.getbuffer())
        _load_pivot(target, uploaded.name)

    if SETTINGS.watch_dir and SETTINGS.watch_dir.is_dir():
        st.divider()
        candidates = sorted(SETTINGS.watch_dir.glob("*.json"))
        if candidates:
            choice = st.selectbox(
                "Or a JSON already on the server",
                candidates,
                format_func=lambda p: p.name,
                key="json_server_pick",
            )
            if st.button("Load from server", use_container_width=True):
                _load_pivot(Path(choice), Path(choice).name)


def _load_pivot(path: Path, name: str) -> None:
    """Read a pivot file and install it, reporting what it does not contain."""
    try:
        from myogait import load_json

        data = load_json(str(path))
    except Exception as exc:
        st.error(f"Could not read the pivot file: {type(exc).__name__}: {exc}")
        return

    if not data.get("frames"):
        st.error("This file has no frames - it is not a myogait pivot JSON.")
        return

    model = str((data.get("extraction") or {}).get("model") or "unknown")
    state.set_source(
        state.Source(
            kind="json",
            name=name,
            data=data,
            key=state.source_key(name, (path.stat().st_size, path.stat().st_mtime)),
            model=model,
            path=path,
        )
    )
    st.rerun()


# ── Video -> extraction ──────────────────────────────────────────────


def _video_tab() -> None:
    runtime = get_runtime()
    runtime_badge(runtime)

    backends = runtime.available_backends
    if not backends:
        st.error(
            "No pose backend is installed. Install at least one, for example: "
            "`pip install \"myogait[mediapipe]\"`."
        )
        return

    labels = {
        b.name: f"{b.label} - {b.keypoints} kp"
        + (f" [{b.weight}]" if b.weight != "light" else "")
        for b in backends
    }
    model = st.selectbox(
        "Pose model",
        [b.name for b in backends],
        format_func=lambda name: labels.get(name, name),
    )
    chosen = runtime.backend(model)

    if chosen and chosen.weight == "heavy" and not runtime.accelerated:
        st.warning(
            f"{chosen.label} on CPU will take a very long time on anything but a "
            "short clip. Consider MediaPipe or YOLO here, and run the heavy model "
            "from the CLI on a GPU machine."
        )
    if chosen and chosen.note:
        st.caption(chosen.note)

    columns = st.columns(2)
    with_depth = columns[0].checkbox(
        "Sapiens depth", value=False, disabled=model not in SAPIENS_BACKENDS
    )
    with_seg = columns[1].checkbox(
        "Sapiens segmentation", value=False, disabled=model not in SAPIENS_BACKENDS
    )
    max_frames = st.number_input(
        "Limit frames (0 = all)", min_value=0, max_value=200000, value=0, step=100,
        help="Useful to sanity-check a model on a long recording before committing "
             "to the full extraction.",
    )

    st.divider()
    source_path = _pick_video()
    if source_path is None:
        return

    active = job_manager().active_count()
    if active >= SETTINGS.max_concurrent_jobs:
        st.warning(
            f"{active} extraction already running and the server accepts "
            f"{SETTINGS.max_concurrent_jobs} at a time. Wait for it to finish, or "
            "recover it from the Recover a job tab."
        )

    if st.button("Start extraction", type="primary", use_container_width=True):
        kwargs: dict = {}
        if with_depth:
            kwargs["with_depth"] = True
        if with_seg:
            kwargs["with_seg"] = True
        if max_frames:
            kwargs["max_frames"] = int(max_frames)

        ticket = job_manager().submit(
            source_path, model, kwargs, video_name=source_path.name
        )
        state.remember_ticket(ticket)
        st.success(f"Started. Your ticket is **{ticket}** - keep it.")
        st.rerun()

    _live_jobs()


def _pick_video() -> Path | None:
    """Upload, or point at a file already on the server.

    The server-side option exists because a 2 GB push through the browser
    uploader is slow and fails often; dropping the file over a share and
    naming it here avoids the round trip entirely.
    """
    modes = ["Upload"]
    if SETTINGS.watch_dir:
        modes.append("Already on the server")
    mode = st.radio("Video source", modes, horizontal=True, key="video_mode")

    if mode == "Upload":
        st.caption(f"Up to {SETTINGS.max_upload_mb / 1024:.0f} GB.")
        uploaded = st.file_uploader("Video", type=VIDEO_TYPES, key="video_upload")
        if uploaded is None:
            return None
        size_mb = uploaded.size / (1024 * 1024)
        st.caption(f"{uploaded.name} - {size_mb:.0f} MB")
        if size_mb > 500:
            st.info(
                "Large upload. If this is slow or drops, copy the file to the "
                "server's drop folder instead and use the other option."
            )
        target = state.workspace().path_for(uploaded.name)
        if not target.exists() or target.stat().st_size != uploaded.size:
            target.write_bytes(uploaded.getbuffer())
        return target

    directory = SETTINGS.watch_dir
    if not directory or not directory.is_dir():
        st.error(f"The configured drop folder does not exist: {directory}")
        return None
    candidates = sorted(
        p for p in directory.iterdir()
        if p.is_file() and p.suffix.lower().lstrip(".") in VIDEO_TYPES
    )
    if not candidates:
        st.info(f"No video found in {directory}.")
        return None
    choice = st.selectbox(
        "File", candidates,
        format_func=lambda p: f"{p.name} ({p.stat().st_size / (1024**3):.2f} GB)",
        key="video_server_pick",
    )
    return Path(choice)


# ── Jobs ─────────────────────────────────────────────────────────────


def _live_jobs() -> None:
    """Progress for jobs started in this session."""
    tickets = state.known_tickets()
    if not tickets:
        return

    st.divider()
    st.markdown("**This session's extractions**")
    manager = job_manager()
    still_running = False

    for ticket in tickets:
        job = manager.get(ticket)
        if job is None:
            continue
        _render_job(job, manager)
        if job.status == RUNNING:
            still_running = True

    if still_running:
        # Polling rather than a callback: the worker runs in another
        # thread and Streamlit only redraws on a script run.
        time.sleep(2)
        st.rerun()


def _render_job(job, manager: JobManager) -> None:
    with st.container(border=True):
        columns = st.columns([3, 1])
        columns[0].markdown(f"**{job.ticket}** &middot; {job.video_name} &middot; `{job.model}`")

        if job.status == RUNNING:
            st.progress(job.progress, text=job.message)
            if columns[1].button("Cancel", key=f"cancel_{job.ticket}"):
                manager.cancel(job.ticket)
                st.rerun()
        elif job.status == DONE:
            st.success(job.message)
            if columns[1].button("Load", key=f"load_{job.ticket}", type="primary"):
                path = job.result_path(SETTINGS)
                if path:
                    _load_pivot(path, f"{job.video_name} [{job.model}]")
                else:
                    st.error("The result file is gone - it may have been purged.")
        elif job.status == FAILED:
            st.error(job.error or job.message)
        else:
            st.info(job.message or job.status)


def _ticket_tab() -> None:
    st.caption(
        "An extraction keeps running after you close the tab. Come back with the "
        f"ticket within {SETTINGS.retention_hours} hours to collect the result."
    )
    raw = st.text_input("Ticket", placeholder="MG-XXXX-XXXX").strip().upper()

    if raw:
        if not is_ticket(raw):
            st.error("That is not a valid ticket. The shape is MG-XXXX-XXXX.")
            return
        job = job_manager().get(raw)
        if job is None:
            st.warning(
                "No job under that ticket. It may have been purged after "
                f"{SETTINGS.retention_hours} hours."
            )
            return
        state.remember_ticket(raw)
        _render_job(job, job_manager())

    known = state.known_tickets()
    if known:
        st.divider()
        st.caption("Tickets issued in this session")
        for ticket in known:
            st.code(ticket, language=None)
    else:
        empty_state(
            "No ticket yet.",
            "Start an extraction from the Video tab and one will be issued.",
        )
