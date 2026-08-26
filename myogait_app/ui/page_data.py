"""Getting data into the workbench.

Three ways in, in ascending order of cost: a pivot JSON, a video already
sitting on the server, and a browser upload. The last two run extraction
as a background job and hand back a ticket, because anything heavier
than MediaPipe outlives the browser session.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import streamlit as st

from ..jobs import DONE, FAILED, QUEUED, JobManager, RUNNING
from ..runtime import (
    BACKENDS,
    DEVICE_CHOICES,
    DEVICE_LABELS,
    SAPIENS2_SIZES,
    SAPIENS_BACKENDS,
    get_runtime,
    sapiens2_seg_weights_ready,
    sapiens2_weights_ready,
    xpu_upgrade_hint,
)
from ..settings import SETTINGS
from ..validation import validate_pivot
from ..storage import exceeds_in_memory_warning, store_uploaded_file
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

#: The full mediapipe-style landmark set the pipeline expects. A C3D
#: marker mapping rarely covers all of them (the package default has no
#: elbow or wrist, for instance), so this is the reference used to report
#: what a loaded file actually matched.
def _warn_large_browser_upload(upload, label: str) -> None:
    """Point large local files to the watch directory before processing."""
    if not exceeds_in_memory_warning(upload.size, SETTINGS.in_memory_warn_mb):
        return
    size_mb = upload.size / (1024 * 1024)
    message = (
        f"{label} is {size_mb:.0f} MB, above the local browser-upload guidance "
        f"of {SETTINGS.in_memory_warn_mb} MB."
    )
    if SETTINGS.watch_dir:
        message += " Copy it to the configured watch directory to avoid browser-memory pressure."
    else:
        message += " Configure MYOGAIT_APP_WATCH_DIR to load large local files directly."
    st.warning(message)


MEDIAPIPE_LANDMARKS = (
    "NOSE", "LEFT_EYE", "RIGHT_EYE", "LEFT_EAR", "RIGHT_EAR",
    "LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW",
    "LEFT_WRIST", "RIGHT_WRIST", "LEFT_HIP", "RIGHT_HIP",
    "LEFT_KNEE", "RIGHT_KNEE", "LEFT_ANKLE", "RIGHT_ANKLE",
    "LEFT_HEEL", "RIGHT_HEEL", "LEFT_FOOT_INDEX", "RIGHT_FOOT_INDEX",
)


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

    tab_json, tab_cohort, tab_c3d, tab_video, tab_ticket = st.tabs(
        ["Pivot JSON", "Cohort", "C3D", "Video -> extraction", "Jobs"]
    )

    with tab_json:
        _json_tab()
    with tab_cohort:
        from . import page_pool

        page_pool.render(show_header=False)
    with tab_c3d:
        _c3d_tab()
    with tab_video:
        _video_tab()
    with tab_ticket:
        _ticket_tab()

    st.divider()
    storage_banner()


# ── Pivot JSON ───────────────────────────────────────────────────────


def _json_tab() -> None:
    st.caption(
        "The fastest route: extraction is the expensive half, so a pivot file "
        "produced earlier by the CLI lets the whole downstream pipeline be "
        "explored instantly."
    )
    uploaded = st.file_uploader("myogait pivot JSON", type=["json"], key="json_upload")

    if uploaded is not None:
        _warn_large_browser_upload(uploaded, "This JSON")
    if uploaded is not None and st.button(
        "Load JSON", type="primary", use_container_width=True
    ):
        target = store_uploaded_file(state.workspace(), uploaded, uploaded.name)
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

    errors = validate_pivot(data)
    if errors:
        st.error("Invalid myogait pivot: " + " ".join(errors))
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


# ── C3D ──────────────────────────────────────────────────────────────


def _c3d_tab() -> None:
    runtime = get_runtime()
    if not runtime.has("c3d_import"):
        st.caption(runtime.missing_feature_hint("c3d_import"))
        return

    st.caption(
        "Loads 3-D marker trajectories from a motion-capture trial and projects "
        "them into the same sagittal-plane pivot format a video extraction "
        "produces, so the whole downstream pipeline runs on it unchanged."
    )
    if runtime.c3d_isotropic_native:
        st.caption(
            f"myogait {runtime.myogait_version} normalises the antero-posterior "
            "and vertical axes isotropically inside load_c3d itself (fixed in "
            "0.8.0), so no aspect-ratio recovery is needed or offered here."
        )
    else:
        st.warning(
            f"myogait {runtime.myogait_version or ''} normalises the "
            "antero-posterior and vertical axes independently, but reports a "
            "square virtual canvas - so compute_angles' own aspect-ratio "
            "correction never triggers for a C3D source. This can bias angles "
            "and segment lengths whenever the two axes cover different "
            "physical ranges, which is typically true for a walking trial. "
            "The option below corrects it by reading the true ranges back out "
            "of the file. Upgrading to myogait >= 0.8.0 fixes this upstream "
            "instead."
        )

    uploaded = st.file_uploader("C3D file", type=["c3d"], key="c3d_upload")

    from myogait.experimental_vicon import DEFAULT_C3D_MARKER_MAP

    target: Path | None = None
    labels: list[str] = []
    detected_mapping: dict[str, list[str]] = {}
    diagnostics = None
    if uploaded is not None:
        _warn_large_browser_upload(uploaded, "This C3D file")
        target = store_uploaded_file(state.workspace(), uploaded, uploaded.name)
        try:
            from ..marker_presets import read_c3d_labels, resolve_c3d_mapping

            labels = read_c3d_labels(target)
            detected_mapping, diagnostics = resolve_c3d_mapping(labels)
        except Exception as exc:
            st.caption(f"Could not pre-scan marker labels: {type(exc).__name__}: {exc}")

    with st.expander("Marker mapping and axes", expanded=False):
        if uploaded is not None and diagnostics is not None:
            _c3d_diagnostics(diagnostics, len(labels))
            st.dataframe(
                [
                    {
                        "Landmark": lm,
                        "Matched marker(s)": ", ".join(detected_mapping.get(lm, [])) or "—",
                        "Via": (
                            f"native: {diagnostics.convention}"
                            if diagnostics.method == "native" and lm in detected_mapping
                            else (diagnostics.source or {}).get(lm, "—")
                            if diagnostics.method == "fuzzy"
                            else "—"
                        ),
                    }
                    for lm in MEDIAPIPE_LANDMARKS
                ],
                use_container_width=True,
                hide_index=True,
            )
            st.divider()

        mapping_mode = st.radio(
            "Marker mapping",
            [
                "Auto-detect (recommended)",
                "Force myogait default (iso_biomechanics only)",
                "Structured fields",
                "Raw JSON",
            ],
            horizontal=True,
            key="c3d_map_mode",
            help="Auto-detect tries myogait's own detect_c3d_convention first "
                 "(5 registered conventions, scored) and falls back to this "
                 "app's own alias-plus-keyword scan only when that cannot "
                 "resolve enough landmarks -- see the diagnostics above once "
                 "a file is uploaded. 'Force myogait default' pins the "
                 "package's original CAST-style set regardless of what "
                 "auto-detect finds, useful to sanity-check a file you know "
                 "uses it. Neither has elbow or wrist by default, so "
                 "arm-swing analysis needs Structured fields or Raw JSON.",
        )
        mapping = _c3d_marker_mapping(
            mapping_mode, DEFAULT_C3D_MARKER_MAP, detected_mapping or None
        )

        st.caption(
            "3-D ankle reference (recovers the ankle from load_c3d's 3-D "
            "marker positions instead of the 2-D sagittal projection) is a "
            "pipeline setting, not a load-time one -- see 'Joint kinematics' "
            "in the sidebar once this trial is loaded."
        )

        st.divider()
        columns = st.columns(2)
        axis_labels = {0: "0 (X)", 1: "1 (Y)", 2: "2 (Z)"}
        ap_axis = columns[0].selectbox(
            "Antero-posterior axis", [0, 1, 2], index=1,
            format_func=lambda i: axis_labels[i], key="c3d_ap_axis",
            help="Vicon standard: Y (1).",
        )
        vertical_axis = columns[1].selectbox(
            "Vertical axis", [0, 1, 2], index=2,
            format_func=lambda i: axis_labels[i], key="c3d_vert_axis",
            help="Vicon standard: Z (2).",
        )

        st.divider()
        if runtime.c3d_isotropic_native:
            fix_aspect = False
            st.caption(
                "Aspect-ratio recovery: not offered - load_c3d already "
                "normalises isotropically on this myogait version (see above)."
            )
        else:
            fix_aspect = st.checkbox(
                "Correct the aspect ratio from the file (recommended)",
                value=True,
                key="c3d_fix_aspect",
                help="Re-reads the file to recover the true antero-posterior "
                     "and vertical ranges and sets them as meta.width/height, "
                     "so compute_angles' aspect-ratio correction has something "
                     "to act on. Turn off to reproduce the package's raw "
                     "behaviour.",
            )

    if uploaded is not None and target is not None and st.button(
        "Load C3D", type="primary", use_container_width=True, key="c3d_load"
    ):
        if not mapping:
            st.error("Fix the marker mapping above before loading.")
            return
        _load_c3d(target, uploaded.name, mapping, int(ap_axis), int(vertical_axis), fix_aspect)


def _c3d_diagnostics(diagnostics, n_labels: int) -> None:
    """Explain how the marker mapping was resolved, for the file just uploaded."""
    from ..marker_presets import REQUIRED_LANDMARKS

    n_required = len(REQUIRED_LANDMARKS)
    if diagnostics.method == "native":
        st.caption(
            f"myogait's own detect_c3d_convention picked **{diagnostics.convention}** "
            f"({diagnostics.n_resolved}/{n_required} required landmarks) from "
            f"{n_labels} markers in the file."
        )
        scored = sorted((diagnostics.scores or {}).items(), key=lambda kv: -kv[1])
        st.caption(
            "Convention scores: "
            + ", ".join(f"{name} {score}/{n_required}" for name, score in scored)
        )
    else:
        st.caption(
            f"myogait's own detect_c3d_convention could not resolve enough "
            f"landmarks on its own (or predates 0.7.0) - falling back to this "
            f"app's alias-plus-keyword scan, which resolved "
            f"{diagnostics.n_resolved}/{n_required} required landmarks from "
            f"{n_labels} markers."
        )
    if diagnostics.n_resolved < 4:
        st.warning(
            f"Only {diagnostics.n_resolved}/{n_required} required lower-limb "
            "landmarks resolved - loading will likely fail. Check the table "
            "below, or switch to Structured fields / Raw JSON to map manually."
        )


def _c3d_marker_mapping(
    mode: str, defaults: dict, detected: dict[str, list[str]] | None
) -> dict | None:
    """Return the mapping for *mode*."""
    if mode == "Force myogait default (iso_biomechanics only)":
        return defaults

    if mode == "Auto-detect (recommended)":
        if not detected:
            st.error(
                "No markers were auto-detected yet - upload a file first, "
                "or switch to a manual mapping mode."
            )
            return None
        return detected

    # Structured fields and Raw JSON both seed from whatever auto-detect
    # already found, so a manual edit starts from a working mapping instead
    # of the package default's own (narrower) landmark set.
    seed = detected or defaults

    if mode == "Structured fields":
        st.caption(
            "One row per myogait landmark, pre-filled from auto-detection "
            "where available. Comma-separated candidate marker names - all "
            "that are found in the file are averaged."
        )
        mapping: dict[str, list[str]] = {}
        for landmark in sorted(set(defaults) | set(seed)):
            candidates = seed.get(landmark) or defaults.get(landmark, [])
            raw = st.text_input(
                landmark, value=", ".join(candidates), key=f"c3d_map_{landmark}"
            )
            names = [c.strip() for c in raw.split(",") if c.strip()]
            if names:
                mapping[landmark] = names
        return mapping

    st.caption('`{"LANDMARK_NAME": ["MARKER1", "MARKER2"], ...}`')
    raw_json = st.text_area(
        "Mapping JSON", value=json.dumps(seed, indent=2), height=240,
        key="c3d_map_json",
    )
    try:
        return json.loads(raw_json)
    except Exception as exc:
        st.error(f"Invalid JSON: {exc}")
        return None


def _load_c3d(
    path: Path,
    name: str,
    mapping: dict | None,
    ap_axis: int,
    vertical_axis: int,
    fix_aspect: bool,
) -> None:
    """Load a C3D trial and install it, correcting the aspect ratio if asked."""
    try:
        from myogait import load_c3d

        data = load_c3d(
            str(path), marker_mapping=mapping, ap_axis=ap_axis, vertical_axis=vertical_axis
        )
    except Exception as exc:
        # InvalidC3DError (myogait >= 0.8.1) is raised specifically for an
        # unresolved marker mapping -- point back at the controls that fix
        # it rather than just the generic message every other failure gets.
        try:
            from myogait.exceptions import InvalidC3DError
        except ImportError:
            InvalidC3DError = ()  # myogait < 0.8.1: no dedicated type to check
        if InvalidC3DError and isinstance(exc, InvalidC3DError):
            st.error(
                f"{exc}\n\nTry Structured fields or Raw JSON above to map the "
                "unmatched landmarks by hand."
            )
        else:
            st.error(f"Could not read the C3D file: {type(exc).__name__}: {exc}")
        return

    if not data.get("frames"):
        st.error("This file produced no frames - check the marker mapping.")
        return

    from myogait.experimental_vicon import DEFAULT_C3D_MARKER_MAP

    effective_mapping = mapping or DEFAULT_C3D_MARKER_MAP
    ranges: tuple[float, float] | None = None
    if fix_aspect:
        try:
            from ..c3d_utils import marker_axis_ranges

            ranges = marker_axis_ranges(path, effective_mapping, ap_axis, vertical_axis)
            data["meta"]["width"], data["meta"]["height"] = ranges
        except Exception as exc:
            st.warning(
                f"Could not recover the true axis ratio, keeping the file's "
                f"raw (square) canvas: {type(exc).__name__}: {exc}"
            )

    matched = sorted((data["frames"][0].get("landmarks") or {}).keys())
    missing = [lm for lm in MEDIAPIPE_LANDMARKS if lm not in matched]

    state.set_source(
        state.Source(
            kind="c3d",
            name=name,
            data=data,
            key=state.source_key(
                name,
                (path.stat().st_size, path.stat().st_mtime, ap_axis, vertical_axis, fix_aspect),
            ),
            model="vicon",
            path=path,
            c3d_options={
                "marker_mapping": mapping,
                "ap_axis": ap_axis,
                "vertical_axis": vertical_axis,
                "fix_aspect_ratio": fix_aspect,
                "matched_landmarks": matched,
                "missing_landmarks": missing,
                "ranges": ranges,
            },
        )
    )
    st.rerun()


# ── Video -> extraction ──────────────────────────────────────────────


def _video_tab() -> None:
    runtime = get_runtime()
    runtime_badge(runtime)

    if not runtime.available_backends:
        st.warning(
            "No pose backend's package is installed yet -- pick one below and "
            "install it, for example: `pip install \"myogait[mediapipe]\"`."
        )

    labels = {
        b.name: f"{b.label} - {b.keypoints} kp"
        + (f" [{b.weight}]" if b.weight != "light" else "")
        + ("" if b.available else " (not installed)")
        for b in BACKENDS
    }
    model = st.selectbox(
        "Pose model",
        [b.name for b in BACKENDS],
        format_func=lambda name: labels.get(name, name),
        help="Every backend myogait implements, whether or not it is installed "
             "on this machine yet. Picking an uninstalled one shows what to run "
             "next instead of hiding it.",
    )
    chosen = runtime.backend(model)

    if chosen and chosen.weight == "heavy" and not runtime.accelerated:
        st.warning(
            f"{chosen.label} on CPU will take a very long time on anything but a "
            "short clip. Consider MediaPipe or YOLO here, and run the heavy model "
            "from the CLI on a GPU machine, or force GPU below if this "
            "machine has one that was not auto-detected."
        )
    if chosen and chosen.note:
        st.caption(chosen.note)

    if chosen and not chosen.available:
        st.warning(f"**{chosen.label}** is not installed. {chosen.install_hint}")

    device_choice = st.selectbox(
        "Compute device",
        DEVICE_CHOICES,
        format_func=lambda c: DEVICE_LABELS[c],
        help=(
            f"Auto-detected on this machine: {runtime.device} "
            f"({runtime.device_detail}). Override forces a backend's device "
            "pick for this extraction, for a GPU the auto-detection missed "
            "or to keep a heavy model off one it should not touch. Known "
            "limit: once this server has run one GPU extraction, forcing CPU "
            "on a later job can require restarting the app to take effect -- "
            "PyTorch caches CUDA availability per process; this app cannot "
            "override that from the outside."
        ),
    )
    xpu_hint = xpu_upgrade_hint()
    if xpu_hint:
        st.info(
            "An Intel GPU looks present, but the installed PyTorch is the "
            "CPU-only build. Stop this app, then run `python scripts/setup_gpu.py` "
            "from the project root and restart -- it detects and installs the "
            "right build automatically, no command to look up or type by hand. "
            "This app never runs that upgrade for you while running: myogait's "
            "own auto-upgrade path replaces the current process, which would "
            "kill this server out from under every connected session."
        )

    # Sapiens 2's depth head was renamed upstream (Meta ships a "pointmap"
    # repo for v2 instead) and myogait's sapiens2_depth module still points
    # at the old facebook/sapiens2-depth-* name, which no longer exists --
    # every sapiens2-* extraction with this checked fails with a 404
    # RepositoryNotFoundError. Confirmed against HuggingFace directly:
    # sapiens2-{pose,seg}-* are real, published repos; sapiens2-depth-* is
    # not, for any size. Sapiens v1's depth repos are real and unaffected.
    depth_broken = model in SAPIENS2_SIZES
    columns = st.columns(2)
    with_depth = columns[0].checkbox(
        "Sapiens depth",
        value=False,
        disabled=model not in SAPIENS_BACKENDS or depth_broken,
        help=(
            "Broken upstream for Sapiens 2: myogait still requests "
            "facebook/sapiens2-depth-* from HuggingFace, a repo Meta never "
            "published (they ship a differently-shaped \"pointmap\" repo "
            "for v2 instead). Available for Sapiens v1 only, until "
            "myogait's own sapiens2_depth module is updated to match."
        ) if depth_broken else None,
    )
    with_seg = columns[1].checkbox(
        "Sapiens segmentation", value=False, disabled=model not in SAPIENS_BACKENDS
    )

    if chosen and model in SAPIENS2_SIZES:
        needs_pose = not sapiens2_weights_ready(model)
        needs_seg = with_seg and not sapiens2_seg_weights_ready(model)
        if needs_pose or needs_seg:
            _sapiens2_first_use_note(chosen, pose=needs_pose, seg=needs_seg)

    max_frames = st.number_input(
        "Limit frames (0 = all)", min_value=0, max_value=200000, value=0, step=100,
        help="Useful to sanity-check a model on a long recording before committing "
             "to the full extraction.",
    )

    st.divider()
    source_path = _pick_video()
    if source_path is None:
        return

    study = _study_form(source_path)

    active = job_manager().active_count()
    busy = active >= SETTINGS.max_concurrent_jobs
    if busy:
        st.warning(
            f"{active} extraction already running (the server runs "
            f"{SETTINGS.max_concurrent_jobs} at a time). Its progress is in the "
            "bar at the top of the page. Wait for it to finish, or Stop it there, "
            "before starting another."
        )

    if st.button(
        "Start extraction", type="primary", use_container_width=True, disabled=busy,
    ):
        kwargs: dict = {}
        if with_depth:
            kwargs["with_depth"] = True
        if with_seg:
            kwargs["with_seg"] = True
        if max_frames:
            kwargs["max_frames"] = int(max_frames)

        ticket = job_manager().submit(
            source_path,
            model,
            kwargs,
            video_name=source_path.name,
            study=study,
            device_override=device_choice,
        )
        state.remember_ticket(ticket)
        st.success(f"Started. Your ticket is **{ticket}** - keep it.")
        st.rerun()

    _live_jobs()


def _study_form(source_path: Path) -> dict:
    """Study identifiers written into the output JSON for pooled analysis.

    Every field carries a default so a quick run needs no typing. The values
    are stored under ``data["study"]`` in the extracted pivot, so that when
    many recordings are later pooled, each output can be grouped and
    labelled for the statistical analysis (by patient, run, group and
    condition). The run defaults to the video's own name.
    """
    stem = Path(source_path).stem
    with st.expander("Study identifiers (saved in the output)", expanded=True):
        st.caption(
            "Stored under `study` in the exported JSON, so several pooled "
            "recordings can be grouped and labelled for statistical analysis."
        )
        c1, c2 = st.columns(2)
        patient_id = c1.text_input("Patient ID", value="P001", key="study_patient")
        # Keyed on the video stem so a different video resets the default.
        run = c2.text_input("Run", value=stem, key=f"study_run::{stem}")
        c3, c4 = st.columns(2)
        group = c3.text_input("Group", value="control", key="study_group")
        condition = c4.text_input(
            "Condition", value="baseline", key="study_condition"
        )
        c5, c6 = st.columns(2)
        # Height (and optionally age) travel with the JSON so the cohort can
        # report step length in metres and pick an age-matched normative band.
        height_m = c5.number_input(
            "Height (m)", min_value=0.0, max_value=2.5, value=0.0, step=0.01,
            format="%.2f", key="study_height",
            help="0 = unknown. Needed for step length in metres.",
        )
        age = c6.number_input(
            "Age (years)", min_value=0, max_value=120, value=0, step=1,
            key="study_age", help="0 = unknown. Selects the normative stratum.",
        )
    study = {
        "patient_id": patient_id.strip(),
        "run": run.strip(),
        "group": group.strip(),
        "condition": condition.strip(),
    }
    if height_m and height_m > 0:
        study["height_m"] = float(height_m)
    if age and age > 0:
        study["age"] = int(age)
    return study


def _sapiens2_first_use_note(chosen, *, pose: bool, seg: bool) -> None:
    """Say what Start extraction will do the first time, nothing to click first.

    No separate setup action: myogait's own weight lookup already
    downloads on first use regardless of anything this app does, so the
    fetch is folded into the extraction job itself
    (``JobManager._fetch_sapiens2_weights``) rather than gated behind an
    extra button. This is purely informational, so a multi-gigabyte,
    multi-minute first run does not come as a surprise.

    ``pose``/``seg`` say which of the two independently-cached model
    files still need fetching -- pose is what the size itself needs;
    seg is separate and only relevant when the Sapiens segmentation
    checkbox is on (see ``sapiens2_seg_weights_ready``'s docstring for
    how this two-file split was discovered).
    """
    parts = []
    if pose:
        parts.append("pose")
    if seg:
        parts.append("segmentation")
    st.info(
        f"**{chosen.label}**'s packages are installed, but its {' / '.join(parts)} "
        f"{'weights are' if len(parts) > 1 else 'model is'} not on this machine yet. "
        "Starting extraction will fetch them first, automatically -- several "
        "gigabytes, a few minutes, one time only. Every later extraction with "
        "this size skips straight to the video. Meta's Sapiens 2 license "
        "excludes biometric processing and unlicensed medical/health "
        "practice; see the README before using it here."
    )


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
        _warn_large_browser_upload(uploaded, "This video")
        return store_uploaded_file(state.workspace(), uploaded, uploaded.name)

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


def active_jobs_banner() -> None:
    """Persistent extraction status, shown on every page.

    An extraction outlives the page it was launched from, so its progress
    must be visible wherever the user navigates -- start it, work elsewhere,
    come back and see where it is. Rendered by ``app.main`` above the page
    body. Shows running/queued jobs with a live bar and a Stop button, plus
    a one-click load for anything that has just finished, and polls while
    something is still running.
    """
    tickets = state.known_tickets()
    if not tickets:
        return
    manager = job_manager()
    jobs = [j for j in (manager.get(t) for t in tickets) if j is not None]
    active = [j for j in jobs if j.status in (QUEUED, RUNNING)]
    just_done = [j for j in jobs if j.status == DONE]

    if not active and not just_done:
        return

    with st.container(border=True):
        for job in active:
            cols = st.columns([5, 1])
            cols[0].progress(
                job.progress if job.status == RUNNING else 0.0,
                text=f"{job.video_name} · {job.model} — {job.message}",
            )
            if cols[1].button("Stop", key=f"banner_stop_{job.ticket}"):
                manager.cancel(job.ticket)
                st.rerun()
        for job in just_done:
            source = state.get_source()
            already = source is not None and source.name.startswith(job.video_name)
            cols = st.columns([5, 1])
            cols[0].caption(f"✓ {job.video_name} · {job.model} — ready")
            label = "Loaded" if already else "Analyse"
            if cols[1].button(label, key=f"banner_load_{job.ticket}", disabled=already):
                path = job.result_path(SETTINGS)
                if path:
                    _load_pivot(path, f"{job.video_name} [{job.model}]")

    if active:
        # Poll only while something is actually running.
        time.sleep(2)
        st.rerun()


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
            if columns[1].button("Analyse", key=f"load_{job.ticket}", type="primary"):
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
    """Every extraction, listed directly -- no ticket to type or remember.

    An extraction keeps running after you close the tab; results are kept for
    the retention window. Newest first, each with Analyse / Stop inline.
    """
    st.caption(
        "Every extraction on this machine, newest first. Kept for "
        f"{SETTINGS.retention_hours} h. Analyse a finished one, or stop a "
        "running one, right here."
    )
    manager = job_manager()
    jobs = manager.list_jobs()
    if not jobs:
        empty_state(
            "No extraction yet.",
            "Start one from the Video tab; it will appear here and in the bar "
            "at the top of the page.",
        )
        return
    for job in jobs:
        _render_job(job, manager)
