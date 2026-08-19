"""The parametric explorer.

The screen the app exists for. Every control in the sidebar re-runs only
the stages downstream of it, and the figures redraw against the same
data, so the question "what does this parameter actually change" gets a
visible answer in a fraction of a second rather than a rerun of the whole
chain.
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd
import streamlit as st

from ..charts import kinematics as K
from ..pipeline import PipelineResult
from ..runtime import get_runtime
from . import state
from .components import (
    chart,
    empty_state,
    is_dark,
    page_header,
    reproducibility_panel,
    source_summary,
    stage_status,
)

#: Column layout expected from a user-supplied normative file.
NORMATIVE_COLUMNS = ("joint", "percent", "mean", "sd")


def render() -> None:
    source = state.get_source()
    if source is None:
        page_header("Pipeline explorer")
        empty_state(
            "Nothing loaded.",
            "Open the Data page and load the synthetic dataset, a pivot JSON, or a video.",
        )
        return

    config = state.get_config()
    runner = state.get_runner()
    page_header(
        "Pipeline explorer",
        "Move any control on the left. Only the stages below it are recomputed.",
    )
    source_summary(source)

    result = runner.run(config)
    stage_status(result)

    if not result.ok:
        st.stop()

    tab_kinematics, tab_cycles, tab_spatio, tab_quality = st.tabs(
        ["Kinematics", "Cycles", "Spatio-temporal", "Signal quality"]
    )

    with tab_kinematics:
        _kinematics_tab(result)
    with tab_cycles:
        _cycles_tab(result, config)
    with tab_spatio:
        _spatiotemporal_tab(result)
    with tab_quality:
        _quality_tab(result, runner)

    st.divider()
    reproducibility_panel(
        config,
        source_name=source.name if source.kind == "json" else "video.mp4",
        model=source.model,
        from_json=source.kind in ("json", "demo"),
        key="pipeline",
    )


# ── Tabs ─────────────────────────────────────────────────────────────


def _kinematics_tab(result: PipelineResult) -> None:
    st.caption(
        "Raw joint angles against time, with detected events overlaid. Solid rules "
        "are heel strikes, dotted are toe offs."
    )
    columns = st.columns([2, 1, 1])
    joints = columns[0].multiselect(
        "Joints", list(K.SAGITTAL_JOINTS) + ["trunk"],
        default=list(K.SAGITTAL_JOINTS), key="kin_joints",
    )
    sides = columns[1].multiselect(
        "Sides", ["left", "right"], default=["left", "right"], key="kin_sides"
    )
    show_events = columns[2].checkbox("Show events", value=True, key="kin_events")

    if not joints or not sides:
        st.info("Select at least one joint and one side.")
        return

    chart(
        K.angle_timeline(
            result.data,
            joints=tuple(joints),
            sides=tuple(sides),
            show_events=show_events,
            dark=is_dark(),
        ),
        key="fig_timeline",
    )

    events = (result.data or {}).get("events") or {}
    counts = {
        "Left HS": len(events.get("left_hs") or []),
        "Right HS": len(events.get("right_hs") or []),
        "Left TO": len(events.get("left_to") or []),
        "Right TO": len(events.get("right_to") or []),
    }
    metric_columns = st.columns(len(counts))
    for column, (label, value) in zip(metric_columns, counts.items()):
        column.metric(label, value)


def _cycles_tab(result: PipelineResult, config) -> None:
    if not result.n_cycles:
        st.warning(
            "No cycle survived segmentation. Widen the duration window in the "
            "sidebar, or try another event detector."
        )
        return

    columns = st.columns([1, 1, 1, 1])
    joint = columns[0].selectbox("Joint", K.SAGITTAL_JOINTS, index=1, key="cyc_joint")
    show_individual = columns[1].checkbox("Individual cycles", value=True, key="cyc_ind")
    show_sd = columns[2].checkbox("SD band", value=True, key="cyc_sd")
    reference = columns[3].selectbox(
        "Reference band", ["None", "Perry & Burnfield", "Custom CSV"], key="cyc_ref"
    )

    normative = _resolve_normative(reference, joint, config)

    chart(
        K.cycle_overlay(
            result.cycles,
            joint=joint,
            show_individual=show_individual,
            show_sd=show_sd,
            normative=normative,
            dark=is_dark(),
        ),
        key="fig_cycles",
    )

    left, right = st.columns(2)
    with left:
        chart(K.rom_summary(result.cycles, dark=is_dark()), key="fig_rom")
    with right:
        chart(K.stance_swing_bar(result.cycles, dark=is_dark()), key="fig_stance")

    with st.expander("Per-cycle table"):
        rows = [
            {
                "id": c.get("cycle_id"),
                "side": c.get("side"),
                "start": c.get("start_frame"),
                "end": c.get("end_frame"),
                "duration_s": c.get("duration"),
                "stance_%": c.get("stance_pct"),
                "swing_%": c.get("swing_pct"),
            }
            for c in result.cycles.get("cycles", [])
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _resolve_normative(choice: str, joint: str, config) -> dict | None:
    """Return the reference band for *joint*, from whichever source is picked."""
    if choice == "None":
        return None

    if choice == "Perry & Burnfield":
        runtime = get_runtime()
        if not runtime.has("normative"):
            st.caption(runtime.missing_feature_hint("normative"))
            return None
        try:
            from myogait import get_normative_band, list_strata, select_stratum

            strata = list(list_strata())
            default = select_stratum(config.subject.age) if config.subject.age else "adult"
            stratum = st.selectbox(
                "Stratum", strata,
                index=strata.index(default) if default in strata else 0,
                key="norm_stratum",
            )
            return get_normative_band(joint, stratum=stratum)
        except Exception as exc:
            st.caption(f"No normative band for {joint}: {exc}")
            return None

    return _custom_normative(joint)


def _custom_normative(joint: str) -> dict | None:
    """Load a user-supplied reference band.

    Long format, one row per joint and cycle percentage, so a single file
    can carry every joint and the app does not have to guess at column
    ordering.
    """
    st.caption(
        "CSV with columns `joint,percent,mean,sd` - one row per joint and cycle "
        "percentage (0-100). Any joint not present is simply not drawn."
    )
    uploaded = st.file_uploader("Normative CSV", type=["csv"], key="norm_csv")
    if uploaded is None:
        return None

    try:
        frame = pd.read_csv(io.BytesIO(uploaded.getbuffer()))
    except Exception as exc:
        st.error(f"Could not read the CSV: {exc}")
        return None

    frame.columns = [str(c).strip().lower() for c in frame.columns]
    missing = [c for c in NORMATIVE_COLUMNS if c not in frame.columns]
    if missing:
        st.error(f"Missing column(s): {', '.join(missing)}")
        return None

    subset = frame[frame["joint"].astype(str).str.lower() == joint].sort_values("percent")
    if subset.empty:
        st.warning(f"The file has no rows for `{joint}`.")
        return None

    mean = subset["mean"].astype(float).to_numpy()
    sd = subset["sd"].astype(float).to_numpy()
    return {
        "mean": mean.tolist(),
        "upper": (mean + sd).tolist(),
        "lower": (mean - sd).tolist(),
    }


def _spatiotemporal_tab(result: PipelineResult) -> None:
    stats = result.stats
    if not stats:
        empty_state("No statistics available for this configuration.")
        return

    spatio = stats.get("spatiotemporal") or {}
    speed = stats.get("walking_speed") or {}

    columns = st.columns(4)
    columns[0].metric("Cadence", _fmt(spatio.get("cadence_steps_per_min"), "steps/min"))
    columns[1].metric("Stride time", _fmt(spatio.get("stride_time_mean_s"), "s"))
    columns[2].metric("Cycles", spatio.get("n_cycles_total", result.n_cycles))
    columns[3].metric("Walking speed", _fmt(speed.get("speed_mean"), "m/s"))

    if speed.get("speed_mean") is not None and not _has_height(result):
        st.caption(
            "Speed is in normalised units - set the subject height in the sidebar "
            "to get metres per second."
        )

    for title, key in (
        ("Spatio-temporal", "spatiotemporal"),
        ("Symmetry", "symmetry"),
        ("Variability", "variability"),
        ("Walking speed", "walking_speed"),
        ("Step length", "step_length"),
        ("Regularity", "regularity"),
        ("Harmonic ratio", "harmonic_ratio"),
    ):
        block = stats.get(key)
        if isinstance(block, dict) and block:
            with st.expander(title, expanded=(key == "spatiotemporal")):
                st.dataframe(_flatten(block), use_container_width=True, hide_index=True)

    # analyze_gait returns pathologies as a list of finding dicts, one per
    # detected pattern, so it is a table in its own right rather than a
    # flattened key/value block.
    pathologies = stats.get("pathologies") or []
    with st.expander(f"Pathology detectors ({len(pathologies)} finding(s))"):
        st.caption(
            "Heuristic screening from myogait, not a diagnosis. Read it alongside "
            "the curves, never instead of them."
        )
        if pathologies:
            st.dataframe(
                pd.DataFrame(pathologies), use_container_width=True, hide_index=True
            )
        else:
            st.caption("No pattern flagged for this configuration.")


def _quality_tab(result: PipelineResult, runner) -> None:
    st.caption(
        "Diagnostics of the extraction, not of the gait. A dip here usually "
        "explains a suspicious excursion in the kinematics."
    )
    show_components = st.checkbox(
        "Break coherence into its components", value=False, key="qual_components",
        help="Segment stability, velocity and angular continuity fail in different "
             "ways and have different fixes.",
    )
    chart(
        K.quality_timeline(result.data, show_components=show_components, dark=is_dark()),
        key="fig_quality",
    )

    summary = (result.data or {}).get("coherence_summary") or {}
    if summary:
        columns = st.columns(4)
        columns[0].metric("Mean coherence", _fmt(summary.get("mean_score")))
        columns[1].metric("Min coherence", _fmt(summary.get("min_score")))
        columns[2].metric("SD", _fmt(summary.get("std_score")))
        columns[3].metric("Low-coherence frames", summary.get("low_coherence_frames", 0))

    try:
        from myogait import data_quality_score

        quality = data_quality_score(result.data)
        st.metric("Overall data quality", f"{quality.get('score', 0):.0f} / 100")
        if quality.get("issues"):
            for issue in quality["issues"]:
                st.caption(f"- {issue}")
    except Exception as exc:
        st.caption(f"Quality score unavailable: {exc}")

    with st.expander("Cache behaviour"):
        st.caption(
            "Stage results are memoised on everything upstream of them, which is "
            "why moving a late control is near-instant."
        )
        st.json(runner.cache_stats)
        if st.button("Clear stage cache"):
            runner.clear_cache()
            st.rerun()


# ── Helpers ──────────────────────────────────────────────────────────


def _fmt(value, unit: str = "") -> str:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return "n/a"
    if isinstance(value, (int, float)):
        return f"{value:.2f} {unit}".strip()
    return str(value)


def _has_height(result: PipelineResult) -> bool:
    subject = (result.data or {}).get("subject") or {}
    return bool(subject.get("height_m"))


def _flatten(block) -> pd.DataFrame:
    """Render a stats block as a flat two-column table.

    ``analyze_gait`` mixes shapes: most blocks are flat mappings, a few
    nest one level, and some are lists of records. Handling all three here
    keeps every caller from having to know which is which.
    """
    if isinstance(block, (list, tuple)):
        if block and all(isinstance(item, dict) for item in block):
            return pd.DataFrame(list(block))
        return pd.DataFrame({"value": [_fmt(item) for item in block]})

    rows = []
    for key, value in (block or {}).items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                rows.append({"metric": f"{key}.{sub_key}", "value": _fmt(sub_value)})
        elif isinstance(value, (list, tuple)):
            rows.append({"metric": key, "value": f"{len(value)} value(s)"})
        else:
            rows.append({"metric": key, "value": _fmt(value)})
    return pd.DataFrame(rows)
