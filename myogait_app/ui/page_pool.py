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
from ..pipeline import AnglesConfig, PipelineConfig
from ..pooling import (
    SAGITTAL_JOINTS,
    UNSPECIFIED,
    condition_agreement,
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
#: Whether the batch currently in _RUNS_KEY was loaded with ISB reconstruction
#: on -- accuracy sections read this to caption the hip/knee definitional
#: offset (see _isb_caveat) rather than silently mixing conventions.
_ISB_KEY = "pool_runs_isb"


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

    isb_on = st.checkbox(
        "ISB reconstruction for Vicon/C3D references", value=True, key="pool_isb",
        help="On by default, matching the rest of the app -- recomputes a C3D "
             "reference's hip/knee/ankle from proper ISB anatomical frames "
             "instead of the sagittal method the video side always uses "
             "(markerless has no 3-D markers to reconstruct from, so this is "
             "a no-op for video either way). Turn off before comparing "
             "accuracy against Vicon if you want hip/knee bias to reflect "
             "pure markerless tracking error rather than also the ISB-vs-"
             "sagittal angle-definition offset (see the caption under "
             "Accuracy below).",
    )

    col_run, col_clear = st.columns([3, 1])
    if col_run.button(
        f"Analyse {len(paths)} recording(s)" if paths else "Analyse",
        type="primary", use_container_width=True, disabled=not paths,
    ):
        config = PipelineConfig(angles=AnglesConfig(isb_reconstruction=isb_on))
        with st.spinner(f"Running the pipeline on {len(paths)} recording(s)..."):
            st.session_state[_RUNS_KEY] = load_runs(paths, config)
            st.session_state[_ISB_KEY] = isb_on
    if col_clear.button("Clear", use_container_width=True):
        st.session_state.pop(_RUNS_KEY, None)
        st.session_state.pop(_ISB_KEY, None)
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
    _overall_accuracy(runs)
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
    bands = normative_bands(SAGITTAL_JOINTS, summary.get("stratum", "adult"))

    st.markdown(
        "**Variability — kinematic curves (all runs pooled, mean +/- SD, "
        f"vs {summary.get('stratum', 'adult')} normative band)**"
    )
    joint_cols = st.columns(3)
    for column, joint in zip(joint_cols, SAGITTAL_JOINTS):
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


def _accuracy_section(label: str, runs: list) -> None:
    """Show accuracy vs the marker reference, when the condition has one.

    Video alone gives variability; a paired marker (Vicon) reference is what
    turns it into accuracy -- error and bias per joint. Without a reference in
    the condition, say so rather than showing an empty table.
    """
    st.markdown("**Accuracy vs marker reference (Vicon)**")

    if label == UNSPECIFIED:
        # UNSPECIFIED is not a real shared condition -- it is where every
        # untagged recording lands, from every patient. Pairing across it
        # would silently compare unrelated patients' video and Vicon curves
        # as if that meant something (verified: two untagged, unrelated
        # pivots land here together and condition_agreement pairs them with
        # no identity check at all). Refuse rather than mislead.
        st.caption(
            "This group holds every recording with no condition tag, "
            "possibly from different patients -- pairing them for accuracy "
            "here would risk comparing unrelated patients' video and Vicon "
            "curves. Tag your recordings with a Patient ID and Condition "
            "(New assessment page, or the C3D tab's Study identifiers) so "
            "they group by real identity instead."
        )
        return

    agreement = condition_agreement(runs)
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
    _isb_caveat(agreement["by_joint"])
    _accuracy_charts(agreement, key_prefix=f"pool_{label}_accuracy")


def _overall_accuracy(runs: list) -> None:
    """Automatic accuracy vs Vicon, paired by patient across the whole batch.

    Appears on its own whenever the loaded batch holds, for the same patient,
    both a markerless and a marker (C3D) recording -- no condition tagging
    needed. It complements the per-condition accuracy below.
    """
    agreement = overall_agreement(runs)
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
    _isb_caveat(agreement["by_joint"])
    _accuracy_charts(agreement, key_prefix="pool_overall_accuracy")


def _accuracy_charts(agreement: dict, key_prefix: str) -> None:
    """Mean video vs Vicon curves, one per sagittal joint.

    See ``charts.kinematics.video_vs_reference_overlay`` for why this is a
    second, dedicated colour rather than the usual side colouring. Only
    joints the agreement's ``by_joint`` battery actually judged trustworthy
    (shape_r > 0.5, see ``agreement.TRACKED_OK_R``) get a chart -- an
    untrustworthy pair is exactly the case a comparison chart would
    mislead on rather than clarify.
    """
    video_pooled = agreement.get("video_pooled")
    vicon_pooled = agreement.get("vicon_pooled")
    if not video_pooled or not vicon_pooled:
        return
    dark = is_dark()
    joints = [j for j in SAGITTAL_JOINTS if j in agreement.get("by_joint", {})]
    if not joints:
        return
    st.caption("**Video vs Vicon — mean cycle curves**")
    cols = st.columns(len(joints))
    for column, joint in zip(cols, joints):
        with column:
            chart(
                K.video_vs_reference_overlay(
                    video_pooled, vicon_pooled, joint=joint, dark=dark, height=280,
                ),
                key=f"{key_prefix}_{joint}",
            )


def _isb_caveat(by_joint: dict) -> None:
    """Warn that hip/knee bias also carries the ISB-vs-sagittal offset.

    ISB reconstruction (the toggle above, on by default) recomputes a Vicon
    reference's hip/knee/ankle from proper anatomical frames instead of the
    sagittal method the video side always uses -- a different *definition*,
    not just added precision (CLAUDE.md documents a 10-17 deg hip / 8-9 deg
    knee constant level-shift between the two on the same trial). Verified
    directly on P03: hip bias flips from -6.1 deg with ISB on to +4.9 deg
    with it off on the identical pair -- the sign of the reported error can
    depend entirely on this toggle, so it must never be silent.
    """
    if not st.session_state.get(_ISB_KEY, True):
        return
    if not ({"hip", "knee"} & set(by_joint)):
        return
    st.caption(
        "⚠️ ISB reconstruction is on for the Vicon/C3D side above (default) "
        "but is a no-op for markerless video (no 3-D markers to reconstruct "
        "from) -- hip/knee bias here also carries the ISB-vs-sagittal angle-"
        "definition offset (~10-17° hip, ~8-9° knee; see CLAUDE.md), not "
        "only markerless tracking error. Turn the toggle above off and "
        "re-analyse to isolate pure tracking accuracy."
    )


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
