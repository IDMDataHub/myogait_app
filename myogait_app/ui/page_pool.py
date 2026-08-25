"""Cohort page: load many pivot JSONs and read a study by condition.

The Data page works one recording at a time; this page is the other end
-- point it at a whole folder of exported pivots and it groups them by the
condition each one carries (``data["study"]``), showing per condition the
same analyses as the validation report (kinematic curves, ROM, stance /
swing, spatio-temporal means) with every individual run still reachable
underneath.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..charts import kinematics as K
from ..pipeline import PipelineConfig
from ..pooling import (
    SAGITTAL_JOINTS,
    condition_agreement,
    condition_summary,
    group_by_condition,
    load_runs,
)
from ..settings import SETTINGS
from ..storage import store_uploaded_file
from . import state
from .components import chart, empty_state, is_dark, page_header

#: Where the loaded batch lives between reruns, so moving a widget does
#: not re-run every pipeline again.
_RUNS_KEY = "pool_runs"


def render(show_header: bool = True) -> None:
    """Render the cohort view. As a Data-page tab, pass ``show_header=False``."""
    if show_header:
        page_header(
            "Cohort",
            "Load many exported pivots at once and read the study by condition.",
        )
    else:
        st.caption(
            "Load many exported pivots at once and read the study by condition. "
            "Each recording is grouped by the identifiers saved into it "
            "(patient, run, group, condition)."
        )

    paths = _collect_inputs()

    col_run, col_clear = st.columns([3, 1])
    if col_run.button(
        f"Analyse {len(paths)} recording(s)" if paths else "Analyse",
        type="primary", use_container_width=True, disabled=not paths,
    ):
        with st.spinner(f"Running the pipeline on {len(paths)} recording(s)..."):
            st.session_state[_RUNS_KEY] = load_runs(paths, PipelineConfig())
    if col_clear.button("Clear", use_container_width=True):
        st.session_state.pop(_RUNS_KEY, None)
        st.rerun()

    runs = st.session_state.get(_RUNS_KEY)
    if not runs:
        empty_state(
            "No cohort loaded",
            "Upload two or more pivot JSONs (or pick them from the server "
            "folder) and press Analyse. Recordings without a recorded "
            "condition are grouped under 'unspecified'.",
        )
        return

    _report_failures(runs)
    groups = group_by_condition(runs)
    if not groups:
        st.warning("No recording produced a usable gait cycle.")
        return

    _overview(groups)
    st.divider()

    labels = list(groups)
    for label, tab in zip(labels, st.tabs([f"{c} ({len(groups[c])})" for c in labels])):
        with tab:
            _condition_view(label, groups[label])


# ── Inputs ───────────────────────────────────────────────────────────


def _collect_inputs() -> list:
    """Uploaded pivots plus, optionally, JSONs from the server folder."""
    paths: list = []
    uploads = st.file_uploader(
        "Pivot JSONs", type=["json"], accept_multiple_files=True,
        key="pool_upload",
    )
    if uploads:
        workspace = state.workspace()
        for upload in uploads:
            paths.append(store_uploaded_file(workspace, upload, upload.name))

    if SETTINGS.watch_dir and SETTINGS.watch_dir.is_dir():
        candidates = sorted(SETTINGS.watch_dir.glob("*.json"))
        if candidates:
            picked = st.multiselect(
                "Or JSONs already on the server",
                candidates, format_func=lambda p: p.name, key="pool_server_pick",
            )
            paths.extend(picked)
    return paths


def _report_failures(runs: list) -> None:
    failures = [r for r in runs if not r.ok]
    if not failures:
        return
    with st.expander(f"{len(failures)} recording(s) could not be analysed", expanded=False):
        for run in failures:
            st.caption(f"**{run.name}** - {run.error}")


# ── Overview across conditions ───────────────────────────────────────


def _overview(groups: dict) -> None:
    st.subheader("Conditions at a glance")
    rows = []
    for label, runs in groups.items():
        summary = condition_summary(runs)
        spatio = summary["spatiotemporal"]
        row = {
            "Condition": label,
            "Patients": summary["n_patients"],
            "Runs": summary["n_runs"],
            "Ref": summary["n_reference"],
            "Cycles": summary["n_cycles"],
            "Cadence (steps/min)": _round(spatio.get("cadence_steps_per_min")),
            "Duration (s)": _round(summary.get("duration_s")),
        }
        for joint in SAGITTAL_JOINTS:
            row[f"{joint.title()} ROM (deg)"] = _round(summary["rom_deg"].get(joint))
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ── One condition ────────────────────────────────────────────────────


def _condition_view(label: str, runs: list) -> None:
    summary = condition_summary(runs)
    spatio = summary["spatiotemporal"]

    cols = st.columns(4)
    cols[0].metric("Patients", summary["n_patients"])
    cols[1].metric("Runs", f"{summary['n_runs']} ({summary['n_reference']} ref)")
    cols[2].metric("Cadence", _fmt(spatio.get("cadence_steps_per_min"), "steps/min"))
    cols[3].metric("Duration", _fmt(summary.get("duration_s"), "s"))

    pooled = summary["cycles"]
    dark = is_dark()

    st.markdown("**Variability — kinematic curves (all runs pooled, mean +/- SD)**")
    joint_cols = st.columns(3)
    for column, joint in zip(joint_cols, SAGITTAL_JOINTS):
        with column:
            chart(
                K.cycle_overlay(pooled, joint=joint, show_individual=True, dark=dark, height=300),
                key=f"pool_{label}_{joint}",
            )

    left, right = st.columns(2)
    with left:
        st.markdown("**Range of motion**")
        chart(K.rom_summary(pooled, dark=dark), key=f"pool_{label}_rom")
    with right:
        st.markdown("**Stance / swing**")
        chart(K.stance_swing_bar(pooled, dark=dark), key=f"pool_{label}_stance")

    _accuracy_section(label, runs)

    with st.expander(f"Run by run ({summary['n_runs']} recordings)", expanded=False):
        run_rows = []
        for run in runs:
            rspatio = (run.stats or {}).get("spatiotemporal") or {}
            run_rows.append({
                "Patient": run.patient,
                "Run": run.run,
                "Group": run.group,
                "Kind": "reference" if run.is_reference else "video",
                "Cycles": run.n_cycles,
                "Cadence (steps/min)": _round(rspatio.get("cadence_steps_per_min")),
                "Duration (s)": _round(run.duration_s),
            })
        st.dataframe(pd.DataFrame(run_rows), use_container_width=True, hide_index=True)


def _accuracy_section(label: str, runs: list) -> None:
    """Show accuracy vs the marker reference, when the condition has one.

    Video alone gives variability; a paired marker (Vicon) reference is what
    turns it into accuracy -- error and bias per joint. Without a reference in
    the condition, say so rather than showing an empty table.
    """
    agreement = condition_agreement(runs)
    st.markdown("**Accuracy vs marker reference (Vicon)**")
    if agreement is None:
        st.caption(
            "No marker reference in this condition, so only variability is "
            "shown above. Add a C3D-derived pivot (a synchronised skeleton) "
            "tagged with the same patient and run to unlock error / bias here."
        )
        return

    st.caption(
        f"{agreement['n_video']} video vs {agreement['n_reference']} marker "
        "recording(s), pooled mean cycle curves compared per joint. "
        "Centred RMSE removes the constant offset (a calibratable zero "
        "difference); waveform r is the shape match."
    )
    rows = []
    for joint, m in agreement["by_joint"].items():
        rows.append({
            "Joint": joint.title(),
            "RMSE (deg)": round(m["rmse"], 1),
            "Centred RMSE (deg)": round(m["rmse_centered"], 1),
            "Waveform r": round(m["shape_r"], 2),
            "|ROM error| (deg)": round(m["rom_err_abs"], 1),
            "|Peak timing| (% cycle)": round(m["peak_t_err_abs"], 1),
            "Joint-sides": m["n"],
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.caption(
            "The video and reference curves did not correlate well enough "
            "(r <= 0.5) to report a meaningful error -- check tracking quality."
        )


# ── Formatting ───────────────────────────────────────────────────────


def _round(value, ndigits: int = 1):
    return round(float(value), ndigits) if isinstance(value, (int, float)) else None


def _fmt(value, unit: str) -> str:
    return f"{value:.1f} {unit}" if isinstance(value, (int, float)) else "-"
