"""The experimental section: VICON ground truth and the AIM benchmark.

myogait labels this block experimental and scoped to AIM benchmark work,
so the page says so and keeps it apart from the analysis pages rather
than blending it in.

One deliberate limit: the full benchmark grid is not run from here. It is
a cartesian product of backends, detectors, filters and degradations, and
a single cell can take minutes -- it belongs in a terminal on a GPU box,
not inside a web request. What this page does instead is build the exact
configuration, hand back the code to run it, and then visualise the
summary CSV it produces.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st

from ..runtime import BACKENDS, get_runtime
from ..settings import SETTINGS
from ..storage import path_is_within_root
from . import state
from .components import (
    backend_availability_refresh_button,
    cached_backend_availability,
    page_header,
    recording_switcher,
    source_loader,
)

DEGRADATION_HELP = {
    "target_fps": "Resample to this frame rate before extraction.",
    "downscale": "Spatial scale factor in (0, 1]. 0.5 halves each dimension.",
    "contrast": "Contrast multiplier in (0, 1]. Below 1 flattens the image.",
    "aspect_ratio": "Horizontal stretch. 1.0 leaves the geometry alone.",
    "perspective_x": "Horizontal keystone tilt in [-1, 1].",
    "perspective_y": "Vertical perspective tilt in [-1, 1].",
}


def render() -> None:
    runtime = get_runtime()
    page_header(
        "Method validation (research)",
        "The bench for validating the method itself: how accurate markerless is "
        "against a Vicon reference, how well it holds up when the video quality "
        "drops, and how parameters trade off. Not a clinical read — for the "
        "clinic use Cohort and Longitudinal.",
    )
    st.warning(
        "Research bench, myogait's own 'experimental' scope: these functions are "
        "not part of the standard pipeline and their outputs are not clinical "
        "results. For patient reading use the analysis pages."
    )

    tab_vicon, tab_degradation, tab_grid = st.tabs(
        ["Accuracy vs Vicon", "Video-quality robustness", "Parameter sweep"]
    )
    with tab_vicon:
        _vicon_tab(runtime)
    with tab_degradation:
        _degradation_tab(runtime)
    with tab_grid:
        _grid_tab(runtime)


# ── VICON ────────────────────────────────────────────────────────────


def _vicon_tab(runtime) -> None:
    if not runtime.has("vicon"):
        st.caption(runtime.missing_feature_hint("vicon"))
        return

    source = state.get_source()
    if source is None:
        source_loader(
            "Nothing loaded.",
            "The alignment compares a myogait result against a VICON trial - "
            "pick the myogait side below, or go to New assessment to load it.",
            slot="experimental",
        )
        return

    recording_switcher("experimental")
    st.caption(
        "Aligns one myogait result with one VICON trial by cross-correlation and "
        "attaches the comparison to the pivot data."
    )
    st.caption(
        "The trial directory is read on the server and must contain the trial's "
        "`.mat` files."
    )

    root = SETTINGS.vicon_root
    trial_path: Path | None = None
    advanced_path = False
    if root and root.is_dir():
        candidates = [root, *sorted(p for p in root.iterdir() if p.is_dir())]
        choice = st.selectbox(
            "VICON trial directory",
            candidates,
            format_func=lambda p: str(p.relative_to(root)) if p != root else ".",
        )
        trial_path = Path(choice)
        st.caption(f"Standard selection is limited to: `{root}`")
    else:
        st.info(
            "Set `MYOGAIT_APP_VICON_ROOT` to select a trial from a local "
            "project directory."
        )

    with st.expander("Advanced path", expanded=trial_path is None):
        advanced_path = st.checkbox("Use a path outside the configured VICON root")
        raw_path = st.text_input(
            "VICON trial directory (local path)",
            value="",
            placeholder="/data/vicon/trial_01_1",
            disabled=not advanced_path,
        )
        if advanced_path and raw_path.strip():
            trial_path = Path(raw_path.strip())

    columns = st.columns(2)
    vicon_fps = columns[0].number_input("VICON frame rate (Hz)", 20.0, 2000.0, 200.0, 10.0)
    max_lag = columns[1].number_input("Max search lag (s)", 0.5, 60.0, 10.0, 0.5)

    if not st.button("Run alignment", type="primary", use_container_width=True):
        return

    if trial_path is None or not trial_path.is_dir():
        st.error("Select a local VICON trial directory before running alignment.")
        return
    if root and not advanced_path and not path_is_within_root(trial_path, root):
        st.error("The selected directory must be inside the configured VICON root.")
        return

    config = state.get_config()
    result = state.get_runner().run(config)
    if not result.ok:
        st.error("Fix the pipeline on the explorer page first.")
        return

    try:
        from myogait import run_single_trial_vicon_benchmark

        with st.spinner("Aligning against VICON..."):
            enriched = run_single_trial_vicon_benchmark(
                result.data,
                trial_dir=str(trial_path),
                vicon_fps=float(vicon_fps),
                max_lag_seconds=float(max_lag),
            )
    except Exception as exc:
        st.error(f"Alignment failed: {type(exc).__name__}: {exc}")
        return

    _render_vicon_benchmark(enriched)


def _r(value, ndigits: int = 1):
    return round(float(value), ndigits) if isinstance(value, (int, float)) else None


def _render_vicon_benchmark(enriched: dict) -> None:
    """Present the single-trial VICON benchmark as readable tables.

    Same battery as the validation report -- per joint RMSE / MAE / signed
    bias / ROM difference / CMC, plus gait-event timing in milliseconds --
    shown as tables rather than a raw JSON dump so the numbers are legible.
    It stays a research/benchmark read, not a clinical result.
    """
    block = ((enriched.get("experimental") or {}).get("vicon_benchmark")) or {}
    if not block:
        st.warning("The run produced no vicon_benchmark block.")
        return

    st.success("Alignment complete.")
    alignment = block.get("alignment") or {}
    offset = alignment.get("offset_seconds")
    n_frames = alignment.get("n_aligned_frames")
    columns = st.columns(2)
    if offset is not None:
        columns[0].metric(
            "Temporal offset (video vs Vicon)", f"{offset:.3f} s",
            help="How far the two recordings had to be shifted in time to line "
                 "up. Estimated by cross-correlation, then removed before "
                 "comparing.",
        )
    if n_frames is not None:
        columns[1].metric("Overlapping frames compared", int(n_frames))

    metrics = block.get("metrics") or {}
    if metrics.get("status") != "ok":
        st.warning(f"No overlap to compare (status: {metrics.get('status')}).")

    angle = metrics.get("angle_metrics") or {}
    if angle:
        st.markdown("**Joint-angle accuracy — markerless vs Vicon**")
        st.caption(
            "Per joint and side. **Bias** is the signed mean (markerless minus "
            "Vicon) — the direction of the offset; **ROM diff** is the "
            "range-of-motion difference; **CMC** is the coefficient of multiple "
            "correlation (1.0 = identical curves, and unlike a plain "
            "correlation it is pulled down by a constant offset). This is the "
            "same battery as the validation report."
        )
        side_name = {"L": "Left", "R": "Right"}
        rows = []
        for name, m in angle.items():
            joint, _, side = name.partition("_")
            rows.append({
                "Joint": joint.title(),
                "Side": side_name.get(side, side),
                "RMSE (deg)": _r(m.get("rmse_deg")),
                "MAE (deg)": _r(m.get("mae_deg")),
                "Bias (deg)": _r(m.get("bias_deg")),
                "ROM diff (deg)": _r(m.get("rom_diff_deg")),
                "CMC": _r(m.get("cmc"), 2),
                "Frames": m.get("n"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    events = metrics.get("event_metrics_ms") or {}
    if events:
        st.markdown("**Gait-event timing accuracy (milliseconds)**")
        st.caption(
            "How closely markerless heel-strike (HS) and toe-off (TO) land on "
            "the Vicon events, per side."
        )
        event_name = {"left_hs": "Heel strike — Left", "right_hs": "Heel strike — Right",
                      "left_to": "Toe off — Left", "right_to": "Toe off — Right"}
        rows = []
        for key, m in events.items():
            rows.append({
                "Event": event_name.get(key, key),
                "MAE (ms)": _r(m.get("mae_ms")),
                "Median (ms)": _r(m.get("median_ms")),
                "n markerless": m.get("n_myogait"),
                "n Vicon": m.get("n_vicon"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with st.expander("Raw benchmark block (JSON)", expanded=False):
        st.json(block)
    st.download_button(
        "Download the enriched pivot JSON",
        _to_json_bytes(enriched),
        file_name="myogait_vicon.json",
        mime="application/json",
        use_container_width=True,
    )


# ── Degradation ──────────────────────────────────────────────────────


def _degradation_tab(runtime) -> None:
    if not runtime.has("degradation"):
        st.caption(runtime.missing_feature_hint("degradation"))
        return

    st.caption(
        "Deliberately degrades the input before extraction, to measure how far a "
        "backend holds up. Disabled by default and applying no change."
    )
    st.caption(
        "It acts on the *video*, so it needs a new extraction - the controls below "
        "produce the configuration and the command to run it."
    )

    enabled = st.checkbox("Enable degradation", value=False)
    columns = st.columns(2)
    with columns[0]:
        target_fps = st.number_input("target_fps (0 = unchanged)", 0.0, 120.0, 0.0, 1.0,
                                     help=DEGRADATION_HELP["target_fps"], disabled=not enabled)
        downscale = st.slider("downscale", 0.1, 1.0, 1.0, 0.05,
                              help=DEGRADATION_HELP["downscale"], disabled=not enabled)
        contrast = st.slider("contrast", 0.1, 1.0, 1.0, 0.05,
                             help=DEGRADATION_HELP["contrast"], disabled=not enabled)
    with columns[1]:
        aspect = st.slider("aspect_ratio", 0.5, 2.0, 1.0, 0.05,
                           help=DEGRADATION_HELP["aspect_ratio"], disabled=not enabled)
        perspective_x = st.slider("perspective_x", -1.0, 1.0, 0.0, 0.05,
                                  help=DEGRADATION_HELP["perspective_x"], disabled=not enabled)
        perspective_y = st.slider("perspective_y", -1.0, 1.0, 0.0, 0.05,
                                  help=DEGRADATION_HELP["perspective_y"], disabled=not enabled)

    config = {
        "enabled": enabled,
        "target_fps": float(target_fps) or None,
        "downscale": float(downscale),
        "contrast": float(contrast),
        "aspect_ratio": float(aspect),
        "perspective_x": float(perspective_x),
        "perspective_y": float(perspective_y),
    }

    st.markdown("**Python**")
    st.code(
        "from myogait import extract\n\n"
        "data = extract(\n"
        '    "video.mp4",\n'
        '    model="mediapipe",\n'
        f"    experimental={config!r},\n"
        ")",
        language="python",
    )

    st.markdown("**CLI**")
    flags = ["myogait extract video.mp4 -m mediapipe"]
    if enabled:
        flags.append("--exp-enable")
        if target_fps:
            flags.append(f"--exp-target-fps {target_fps:g}")
        for flag, value, default in (
            ("--exp-downscale", downscale, 1.0),
            ("--exp-contrast", contrast, 1.0),
            ("--exp-aspect-ratio", aspect, 1.0),
            ("--exp-perspective-x", perspective_x, 0.0),
            ("--exp-perspective-y", perspective_y, 0.0),
        ):
            if value != default:
                flags.append(f"{flag} {value:g}")
    st.code(" \\\n  ".join(flags), language="bash")


# ── Benchmark grid ───────────────────────────────────────────────────


def _grid_tab(runtime) -> None:
    if not runtime.has("benchmark"):
        st.caption(runtime.missing_feature_hint("benchmark"))
        return

    st.caption(
        "The grid crosses backends, detectors, filters and degradations. Even a "
        "small one runs for a long time, so it is built here and run in a terminal."
    )

    grid_availability = cached_backend_availability(runtime, key="grid_tab")
    available = [b.name for b in BACKENDS if grid_availability[b.name]]
    backend_availability_refresh_button(runtime, key="grid_tab")
    models = st.multiselect(
        "Models", available, default=available[: min(2, len(available))]
    )
    methods = st.multiselect(
        "Event methods", list(runtime.event_methods),
        default=list(runtime.event_methods)[:3],
    )
    columns = st.columns(2)
    with_filters = columns[0].checkbox("Include a no-filter variant", value=True)
    with_degradation = columns[1].checkbox("Include a degraded variant", value=False)

    cells = max(1, len(models)) * max(1, len(methods))
    cells *= 2 if with_filters else 1
    cells *= 2 if with_degradation else 1
    st.metric("Grid cells", cells)
    if cells > 20:
        st.warning(
            f"{cells} extractions. At a few minutes each on CPU this is an "
            "overnight run - launch it with nohup, not from a browser tab."
        )

    normalization = [{"name": "butterworth", "enabled": True,
                      "kwargs": {"filters": ["butterworth"]}}]
    if with_filters:
        normalization.insert(0, {"name": "none", "enabled": False, "kwargs": {}})

    degradation = [{"name": "none", "experimental": {"enabled": False}}]
    if with_degradation:
        degradation.append({
            "name": "lowres",
            "experimental": {"enabled": True, "downscale": 0.7, "target_fps": 15.0},
        })

    benchmark_config = {
        "models": models or ["mediapipe"],
        "event_methods": methods or ["zeni"],
        "normalization_variants": normalization,
        "degradation_variants": degradation,
        "continue_on_error": True,
    }

    st.code(
        "from myogait import run_single_pair_benchmark\n\n"
        "manifest = run_single_pair_benchmark(\n"
        '    video_path="video.mp4",\n'
        '    vicon_trial_dir="/path/to/trial_01_1",\n'
        '    output_dir="./benchmark_out",\n'
        f"    benchmark_config={benchmark_config!r},\n"
        ")\n"
        'print(manifest["summary_csv"])',
        language="python",
    )

    st.divider()
    st.markdown("**Read a finished run**")
    st.caption("Load the `benchmark_summary.csv` the runner writes.")
    uploaded = st.file_uploader("benchmark_summary.csv", type=["csv"], key="bench_csv")
    if uploaded is None:
        return

    try:
        frame = pd.read_csv(io.BytesIO(uploaded.getbuffer()))
    except Exception as exc:
        st.error(f"Could not read the CSV: {exc}")
        return

    st.dataframe(frame, use_container_width=True)
    numeric = frame.select_dtypes("number").columns.tolist()
    grouping = [c for c in frame.columns if c not in numeric]
    if numeric and grouping:
        columns = st.columns(2)
        metric = columns[0].selectbox("Metric", numeric, key="bench_metric")
        group = columns[1].selectbox("Group by", grouping, key="bench_group")
        st.bar_chart(frame.groupby(group)[metric].mean())


def _to_json_bytes(data: dict) -> bytes:
    from myogait.schema import dumps_json_safe

    return dumps_json_safe(data).encode("utf-8")
