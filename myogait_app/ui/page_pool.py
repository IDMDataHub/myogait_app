"""Cohort page: load many pivot JSONs and read a study by condition.

The Data page works one recording at a time; this page is the other end
-- point it at a whole folder of exported pivots and it groups them by the
condition each one carries (``data["study"]``), showing per condition the
same analyses as the validation report (kinematic curves, ROM, stance /
swing, spatio-temporal means) with every individual run still reachable
underneath.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from ..charts import kinematics as K
from ..clinical import VALIDITY_GRADES, normative_bands, validity
from ..pipeline import PipelineConfig
from ..pooling import (
    SAGITTAL_JOINTS,
    condition_agreement,
    condition_comparison,
    condition_summary,
    group_by_condition,
    load_runs,
    overall_agreement,
)
from ..settings import SETTINGS
from ..storage import store_uploaded_file
from . import state
from .components import chart, empty_state, is_dark, page_header

#: Where the loaded batch lives between reruns, so moving a widget does
#: not re-run every pipeline again.
_RUNS_KEY = "pool_runs"
_PATHS_KEY = "pool_paths"
_AUTO_RECIPE = "Auto-detect per recording (recommended)"
_SIDEBAR_RECIPE = "Sidebar configuration (shared)"


def _chosen_config() -> PipelineConfig | None:
    """The batch config: None means auto-detect the recipe per recording."""
    if st.session_state.get("pool_config_mode") == _SIDEBAR_RECIPE:
        return state.get_config()
    return None


def render(show_header: bool = True, mode: str = "single") -> None:
    """Render the cohort view. As a Data-page tab, pass ``show_header=False``.

    *mode* orders the cross-condition material for the guided Analysis
    scopes: ``"single"`` (one-group read, default), ``"compare"`` (the
    two-condition comparison leads) or ``"accuracy"`` (the vs-Vicon agreement
    leads). Every mode keeps the full content below -- the mode is emphasis,
    not a filter.
    """
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

    st.radio(
        "Pipeline recipe", [_AUTO_RECIPE, _SIDEBAR_RECIPE],
        key="pool_config_mode", horizontal=True,
        help="Auto-detect inspects each recording (marker vs video, standing "
             "vs mid-stride start, there-and-back) and picks its recipe; the "
             "sidebar option applies the current sidebar configuration "
             "identically to every recording.",
    )

    stored_paths = st.session_state.get(_PATHS_KEY) or []
    col_run, col_re, col_clear = st.columns([3, 2, 1])
    if col_run.button(
        f"Analyse {len(paths)} recording(s)" if paths else "Analyse",
        type="primary", use_container_width=True, disabled=not paths,
    ):
        with st.spinner(f"Running the pipeline on {len(paths)} recording(s)..."):
            st.session_state[_RUNS_KEY] = load_runs(paths, _chosen_config())
            st.session_state[_PATHS_KEY] = list(paths)
    if col_re.button(
        f"Re-analyse {len(stored_paths)}" if stored_paths else "Re-analyse",
        use_container_width=True, disabled=not stored_paths,
        help="Re-run the whole loaded batch with the recipe chosen above -- "
             "the way to change the analysis of many JSONs at once.",
    ):
        with st.spinner(f"Re-running the pipeline on {len(stored_paths)} recording(s)..."):
            st.session_state[_RUNS_KEY] = load_runs(stored_paths, _chosen_config())
    if col_clear.button("Clear", use_container_width=True):
        st.session_state.pop(_RUNS_KEY, None)
        st.session_state.pop(_PATHS_KEY, None)
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

    joints, sides = _joint_side_selection()

    if mode == "compare":
        _condition_comparison(groups, joints)
        _overview(groups, joints)
        _overall_accuracy(runs, joints, sides)
    elif mode == "accuracy":
        _overall_accuracy(runs, joints, sides)
        _overview(groups, joints)
        _condition_comparison(groups, joints)
    else:
        _overview(groups, joints)
        _condition_comparison(groups, joints)
        _overall_accuracy(runs, joints, sides)
    st.divider()

    labels = list(groups)
    for label, tab in zip(labels, st.tabs([f"{c} ({len(groups[c])})" for c in labels])):
        with tab:
            _condition_view(label, groups[label], joints, sides)


def _joint_side_selection() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The joints/sides every cohort view below honours (defaults: all)."""
    c1, c2 = st.columns([2, 1])
    joints = c1.multiselect(
        "Joints", list(SAGITTAL_JOINTS), default=list(SAGITTAL_JOINTS),
        key="pool_joints", format_func=str.title,
    )
    sides = c2.multiselect(
        "Sides", ["left", "right"], default=["left", "right"],
        key="pool_sides", format_func=str.title,
    )
    return tuple(joints) or SAGITTAL_JOINTS, tuple(sides) or ("left", "right")


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


def _overview(groups: dict, joints: tuple[str, ...] = SAGITTAL_JOINTS) -> None:
    st.subheader("Conditions at a glance")
    rows = []
    for label, runs in groups.items():
        summary = condition_summary(runs, joints)
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
        for joint in joints:
            row[f"{joint.title()} ROM (deg)"] = _round(summary["rom_deg"].get(joint))
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _condition_comparison(groups: dict, joints: tuple[str, ...] = SAGITTAL_JOINTS) -> None:
    """Two-condition comparison: per-joint ROM change vs the MDC.

    Only shown with at least two conditions. Tells a real change (beyond
    measurement noise) from repeatability, which is what a pre/post or
    condition-to-condition read needs.
    """
    labels = list(groups)
    if len(labels) < 2:
        return
    st.subheader("Compare two conditions")
    st.caption(
        "Is the difference between two conditions real, or within measurement "
        "noise? The 95% Minimal Detectable Change (MDC) is the repeatability "
        "threshold estimated from within-subject cycle-to-cycle spread; a "
        "difference below it is not distinguishable from noise. Joint-ROM "
        "parameters only (per-cycle spatiotemporal values are not pooled yet)."
    )
    c1, c2 = st.columns(2)
    a = c1.selectbox("Condition A", labels, index=0, key="cmp_a")
    b = c2.selectbox("Condition B", labels, index=1, key="cmp_b")
    if a == b:
        st.info("Pick two different conditions to compare.")
        return
    rows = condition_comparison(groups[a], groups[b], joints=joints)
    if not rows:
        st.info("Not enough shared joint data to compare these two conditions.")
        return
    table = []
    for row in rows:
        if row["exceeds"] is None:
            verdict = "insufficient data"
        elif row["exceeds"]:
            verdict = "real change (> MDC)"
        else:
            verdict = "within noise (< MDC)"
        table.append({
            "Parameter": row["parameter"],
            f"{a}": _round(row["a"]),
            f"{b}": _round(row["b"]),
            "Δ (A−B)": _round(row["delta"]),
            "MDC95": _round(row["mdc"]),
            "Verdict": verdict,
        })
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)


# ── One condition ────────────────────────────────────────────────────


def _condition_view(
    label: str,
    runs: list,
    joints: tuple[str, ...] = SAGITTAL_JOINTS,
    sides: tuple[str, ...] = ("left", "right"),
) -> None:
    summary = condition_summary(runs, joints)
    spatio = summary["spatiotemporal"]

    cols = st.columns(5)
    cols[0].metric("Patients", summary["n_patients"])
    cols[1].metric("Runs", f"{summary['n_runs']} ({summary['n_reference']} ref)")
    cols[2].metric("Cadence", _fmt(spatio.get("cadence_steps_per_min"), "steps/min"))
    cols[3].metric(
        "Step length", _fmt(summary.get("step_length_m"), "m"),
        help="Metric only when a subject height is set in the study identifiers.",
    )
    cols[4].metric("Duration", _fmt(summary.get("duration_s"), "s"))

    _scores_row(summary)

    pooled = summary["cycles"]
    dark = is_dark()
    bands = normative_bands(joints, summary.get("stratum", "adult"))

    st.markdown(
        "**Variability — kinematic curves (all runs pooled, mean +/- SD, "
        f"vs {summary.get('stratum', 'adult')} normative band)**"
    )
    joint_cols = st.columns(max(len(joints), 1))
    for column, joint in zip(joint_cols, joints):
        with column:
            chart(
                K.cycle_overlay(
                    pooled, joint=joint, show_individual=True,
                    normative=bands.get(joint), dark=dark, height=300,
                ),
                key=f"pool_{label}_{joint}",
            )
            _validity_caption(joint)

    left, right = st.columns(2)
    with left:
        st.markdown("**Range of motion**")
        chart(K.rom_summary(pooled, dark=dark), key=f"pool_{label}_rom")
    with right:
        st.markdown("**Stance / swing**")
        chart(K.stance_swing_bar(pooled, dark=dark), key=f"pool_{label}_stance")

    _accuracy_section(label, runs, joints, sides)

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
                "Pipeline recipe": run.config_note or "Explicit configuration",
            })
        st.dataframe(pd.DataFrame(run_rows), use_container_width=True, hide_index=True)


def _scores_row(summary: dict) -> None:
    """2-D clinical screening scores for the condition, if myogait exposes them."""
    scores = summary.get("scores")
    if not scores:
        return
    cols = st.columns(3)
    cols[0].metric(
        "GPS-2D", _fmt(scores.get("gps_2d_overall"), "deg"),
        help="2-D sagittal Gait Profile Score — screening only, not the "
             "validated 3-D GPS.",
    )
    cols[1].metric(
        "GDI-2D", _fmt(scores.get("gdi_2d_overall"), ""),
        help="Normal ~ 100; a z-score index, not the PCA-based 3-D GDI.",
    )
    gvs = scores.get("gvs_by_joint") or {}
    worst = max(gvs.items(), key=lambda kv: kv[1], default=None)
    if worst:
        cols[2].metric("Worst joint (GVS)", f"{worst[0].title()} {worst[1]:.1f} deg")


def _validity_caption(joint: str) -> None:
    entry = validity(joint)
    if entry:
        grade = VALIDITY_GRADES.get(entry.get("grade"), entry.get("grade", ""))
        st.caption(f"{grade}: {entry.get('note', '')}")


def _accuracy_section(
    label: str,
    runs: list,
    joints: tuple[str, ...] = SAGITTAL_JOINTS,
    sides: tuple[str, ...] = ("left", "right"),
) -> None:
    """Show accuracy vs the marker reference, when the condition has one.

    Video alone gives variability; a paired marker (Vicon) reference is what
    turns it into accuracy -- error and bias per joint. Without a reference in
    the condition, say so rather than showing an empty table.
    """
    agreement = condition_agreement(runs, joints, sides)
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
        "recording(s), pooled mean cycle curves compared per joint — the same "
        "battery as the validation report's single-trial Vicon benchmark. "
        "Bias is the signed mean offset (video minus reference); centred RMSE "
        "removes that offset; waveform r and CMC are shape matches (CMC, unlike "
        "r, is penalised by a constant offset)."
    )
    _agreement_table(agreement["by_joint"])


def _overall_accuracy(
    runs: list,
    joints: tuple[str, ...] = SAGITTAL_JOINTS,
    sides: tuple[str, ...] = ("left", "right"),
) -> None:
    """Automatic accuracy vs Vicon, paired by patient across the whole batch.

    Appears on its own whenever the loaded batch holds, for the same patient,
    both a markerless and a marker (C3D) recording -- no condition tagging
    needed. It complements the per-condition accuracy below.
    """
    agreement = overall_agreement(runs, joints, sides)
    if agreement is None:
        return
    st.divider()
    st.subheader("Accuracy vs Vicon — paired automatically by patient")
    st.caption(
        f"{agreement['n_patients']} patient(s) with both kinds: "
        f"{agreement['n_video']} markerless vs {agreement['n_reference']} marker "
        "recording(s). Each patient's mean markerless curve is compared with "
        "their own mean Vicon curve, then averaged per joint — the report's "
        "battery (bias signed, centred RMSE removes the offset, CMC is an "
        "offset-sensitive shape match)."
    )
    _agreement_table(agreement["by_joint"])


def _agreement_table(by_joint: dict) -> None:
    """Render one per-joint agreement battery as a table (shared)."""
    rows = []
    for joint, m in by_joint.items():
        rows.append({
            "Joint": joint.title(),
            "RMSE (deg)": round(m["rmse"], 1),
            "MAE (deg)": round(m["mae"], 1),
            "Bias (deg)": round(m["bias"], 1),
            "Centred RMSE (deg)": round(m["rmse_centered"], 1),
            "Waveform r": round(m["shape_r"], 2),
            "CMC": None if np.isnan(m.get("cmc", float("nan"))) else round(m["cmc"], 2),
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
