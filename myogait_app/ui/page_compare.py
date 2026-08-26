"""The comparator.

Two questions, two tabs.

**Sweep** holds the recording fixed and varies one pipeline parameter, so
the difference in the output is attributable to that parameter and
nothing else. It runs on the shared stage cache, which makes sweeping an
event detector or a filter cutoff nearly free.

**Models** compares separate extractions of the same walk by different
pose backends. Those cannot be produced on the fly here -- the server
takes one extraction at a time -- so they are loaded as pivot files and
put through an identical downstream pipeline, which is the only way the
comparison isolates the backend.

Colour carries the series in both tabs; the side moves to a facet.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from ..charts import comparison as C
from ..charts import kinematics as K
from ..pipeline import (
    PipelineRunner,
)
from ..runtime import get_runtime
from . import state
from .components import chart, empty_state, is_dark, page_header

#: Parameters a sweep can vary, each as (label, stage, field, values-builder).
SWEEP_SPECS = {
    "Event detection method": ("events", "method", "choice"),
    "Angle method": ("angles", "method", "choice"),
    "Butterworth cutoff (Hz)": ("normalize", "butterworth_cutoff", "numeric"),
    "2D ROM correction factor": ("angles", "correction_factor", "numeric"),
    "Min cycle duration (s)": ("cycles", "min_duration", "numeric"),
    "Calibration frames": ("angles", "calibration_frames", "numeric"),
}


def render() -> None:
    page_header(
        "Comparator",
        "Vary one thing at a time and see what it changes.",
    )
    tab_sweep, tab_models = st.tabs(["Parameter sweep", "Compare extractions"])
    with tab_sweep:
        _sweep_tab()
    with tab_models:
        _models_tab()


# ── Sweep ────────────────────────────────────────────────────────────


def _sweep_tab() -> None:
    source = state.get_source()
    if source is None:
        empty_state(
            "Nothing loaded.",
            "A sweep varies one parameter on a fixed recording - load one first.",
        )
        return

    runtime = get_runtime()
    config = state.get_config()
    runner = state.get_runner()

    st.caption(
        "Everything except the swept parameter stays exactly as configured in the "
        "sidebar, so any difference below is attributable to that parameter alone."
    )

    which = st.selectbox("Parameter to sweep", list(SWEEP_SPECS), key="sweep_param")
    stage, field, kind = SWEEP_SPECS[which]
    values = _sweep_values(which, stage, field, kind, runtime, config)

    if len(values) < 2:
        st.info("Pick at least two values.")
        return
    if len(values) > C.MAX_SERIES:
        st.warning(
            f"{len(values)} values selected; only the first {C.MAX_SERIES} are drawn - "
            "beyond that the palette can no longer keep the series apart."
        )
        values = values[: C.MAX_SERIES]

    results, failures = _run_sweep(runner, config, stage, field, values)
    for label, reason in failures.items():
        st.caption(f"`{label}` produced nothing: {reason}")

    if len(results) < 2:
        st.warning("Fewer than two values produced usable cycles.")
        return

    _render_comparison(results, key_prefix="sweep")


def _sweep_values(which, stage, field, kind, runtime, config) -> list:
    """Widget for the value set, matched to the parameter's type."""
    if kind == "choice":
        options = (
            list(runtime.event_methods) if stage == "events" else list(runtime.angle_methods)
        )
        default = options[: min(3, len(options))]
        return st.multiselect("Values", options, default=default, key=f"sweep_vals_{field}")

    current = float(getattr(getattr(config, stage), field))
    bounds = {
        "butterworth_cutoff": (0.5, 15.0, 0.5),
        "correction_factor": (0.5, 1.2, 0.05),
        "min_duration": (0.2, 2.0, 0.05),
        "calibration_frames": (5.0, 120.0, 5.0),
    }[field]
    low, high, step = bounds

    columns = st.columns(3)
    start = columns[0].number_input("From", low, high, max(low, current - 2 * step), step)
    stop = columns[1].number_input("To", low, high, min(high, current + 2 * step), step)
    count = columns[2].number_input("Steps", 2, C.MAX_SERIES, 4, 1)

    if stop <= start:
        return []
    values = np.linspace(float(start), float(stop), int(count))
    if field == "calibration_frames":
        return sorted({int(round(v)) for v in values})
    return [round(float(v), 3) for v in values]


def _run_sweep(runner: PipelineRunner, config, stage: str, field: str, values: list):
    """Run the pipeline once per value, reusing every shared upstream stage."""
    from dataclasses import replace

    results: dict[str, dict] = {}
    failures: dict[str, str] = {}
    progress = st.progress(0.0, text="Running sweep...")

    for index, value in enumerate(values):
        label = f"{field}={value}"
        stage_config = replace(getattr(config, stage), **{field: value})
        candidate = config.with_stage(stage, stage_config)

        outcome = runner.run(candidate)
        if not outcome.ok:
            failed = outcome.failed_stage
            failures[label] = failed.error if failed else "unknown error"
        elif not outcome.n_cycles:
            failures[label] = "no cycle survived segmentation"
        else:
            results[label] = {
                "cycles": outcome.cycles,
                "events": (outcome.data or {}).get("events") or {},
                "stats": outcome.stats,
                "seconds": outcome.total_seconds,
            }
        progress.progress((index + 1) / len(values), text=f"Running sweep... {label}")

    progress.empty()
    return results, failures


# ── Compare separate extractions ─────────────────────────────────────


def _models_tab() -> None:
    st.caption(
        "Load one pivot JSON per pose backend - the same walk, extracted "
        "differently. Each is put through an identical downstream pipeline (the "
        "sidebar's), so the only thing varying is the backend."
    )
    st.caption(
        "Produce them from the CLI, for example: "
        "`myogait extract walk.mp4 -m yolo -o walk_yolo.json`"
    )

    uploaded = st.file_uploader(
        "Pivot JSON files", type=["json"], accept_multiple_files=True, key="cmp_files"
    )
    if not uploaded:
        empty_state("No file loaded yet.")
        return

    if len(uploaded) > C.MAX_SERIES:
        st.warning(f"Only the first {C.MAX_SERIES} files are used.")
        uploaded = uploaded[: C.MAX_SERIES]

    config = state.get_config()
    workspace = state.workspace()
    results: dict[str, dict] = {}

    progress = st.progress(0.0, text="Processing...")
    for index, item in enumerate(uploaded):
        target = workspace.path_for(item.name)
        target.write_bytes(item.getbuffer())
        try:
            from myogait import load_json

            data = load_json(str(target))
        except Exception as exc:
            st.caption(f"`{item.name}` could not be read: {exc}")
            continue

        label = str((data.get("extraction") or {}).get("model") or item.name)
        if label in results:
            label = f"{label} ({item.name})"

        runner = PipelineRunner(data, state.source_key(item.name, item.size))
        outcome = runner.run(config)
        if not outcome.ok:
            failed = outcome.failed_stage
            st.caption(f"`{label}` failed at {failed.name}: {failed.error}")
        elif not outcome.n_cycles:
            st.caption(f"`{label}` produced no cycle.")
        else:
            results[label] = {
                "cycles": outcome.cycles,
                "events": (outcome.data or {}).get("events") or {},
                "stats": outcome.stats,
                "seconds": outcome.total_seconds,
            }
        progress.progress((index + 1) / len(uploaded), text=f"Processing {item.name}...")
    progress.empty()

    if len(results) < 2:
        st.warning("At least two usable extractions are needed to compare.")
        return

    _render_comparison(results, key_prefix="models")


# ── Shared rendering ─────────────────────────────────────────────────


def _render_comparison(results: dict, key_prefix: str) -> None:
    labels = list(results)
    dark = is_dark()

    columns = st.columns([1, 1, 1])
    joint = columns[0].selectbox(
        "Joint", K.SAGITTAL_JOINTS, index=1, key=f"{key_prefix}_joint"
    )
    reference = columns[1].selectbox(
        "Reference series", labels, key=f"{key_prefix}_ref"
    )
    side = columns[2].selectbox(
        "Side for difference", ["left", "right"], key=f"{key_prefix}_side"
    )

    series = {label: results[label]["cycles"] for label in labels}

    chart(
        C.compare_cycles(series, joint=joint, reference=reference, dark=dark),
        key=f"{key_prefix}_fig_cycles",
    )

    st.markdown("**Where they diverge**")
    st.caption(
        "Difference against the reference, point by point. A flat line on zero is "
        "agreement; the shape of any departure says which phase of the cycle they "
        "disagree about."
    )
    chart(
        C.difference_from_reference(series, reference, joint, side, dark=dark),
        key=f"{key_prefix}_fig_diff",
    )

    left, right = st.columns(2)
    with left:
        matrix, matrix_labels = C.rms_matrix(series, joint, side)
        chart(
            C.agreement_heatmap(
                matrix, matrix_labels, f"RMS difference - {joint}, {side} (deg)", dark=dark
            ),
            key=f"{key_prefix}_fig_heat",
        )
    with right:
        metric = st.selectbox(
            "Metric",
            ["Cycles detected", "Cadence (steps/min)", "Stride time (s)", f"{joint} ROM (deg)"],
            key=f"{key_prefix}_metric",
        )
        values = _metric_values(results, metric, joint, side)
        chart(
            C.metric_bars(values, metric, reference=reference, dark=dark),
            key=f"{key_prefix}_fig_metric",
        )

    st.markdown("**Event timing**")
    st.caption(
        "Filled marks are heel strikes, open marks toe offs. Vertical alignment "
        "means the series agree on when the event happened."
    )
    events = {label: results[label]["events"] for label in labels}
    chart(C.event_raster(events, side, dark=dark), key=f"{key_prefix}_fig_raster")

    with st.expander("Summary table"):
        st.dataframe(
            _summary_table(results, joint, side), use_container_width=True, hide_index=True
        )


def _metric_values(results: dict, metric: str, joint: str, side: str) -> dict:
    values = {}
    for label, payload in results.items():
        spatio = (payload.get("stats") or {}).get("spatiotemporal") or {}
        if metric == "Cycles detected":
            values[label] = float(len(payload["cycles"].get("cycles", [])))
        elif metric.startswith("Cadence"):
            values[label] = float(spatio.get("cadence_steps_per_min") or np.nan)
        elif metric.startswith("Stride"):
            values[label] = float(spatio.get("stride_time_mean_s") or np.nan)
        else:
            values[label] = _rom(payload["cycles"], joint, side)
    return values


def _rom(cycles: dict, joint: str, side: str) -> float:
    mean = ((cycles.get("summary") or {}).get(side) or {}).get(f"{joint}_mean")
    if not mean:
        return float("nan")
    array = np.asarray(mean, dtype=float)
    return float(np.nanmax(array) - np.nanmin(array))


def _summary_table(results: dict, joint: str, side: str) -> pd.DataFrame:
    rows = []
    for label, payload in results.items():
        spatio = (payload.get("stats") or {}).get("spatiotemporal") or {}
        cycles = payload["cycles"]
        rows.append(
            {
                "series": label,
                "cycles": len(cycles.get("cycles", [])),
                "cadence": spatio.get("cadence_steps_per_min"),
                "stride_time_s": spatio.get("stride_time_mean_s"),
                f"{joint}_ROM_{side}": round(_rom(cycles, joint, side), 2),
                "pipeline_s": round(payload.get("seconds", 0.0), 3),
            }
        )
    return pd.DataFrame(rows)
