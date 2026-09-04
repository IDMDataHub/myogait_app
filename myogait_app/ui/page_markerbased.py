"""Markerbased vs Monocular -- one video+C3D pair, every parameter, side
by side.

Analysis's "Accuracy vs C3D" answers *how far apart* markerless and Vicon
are, as numbers (bias, RMSE, r, CMC, ICC). This scope answers *where* and
*how* they differ, as curves: pick one ready video+C3D pair from job
history, run both pivots through the pipeline, and read the same families
Trial Explorer shows for a single trial -- kinematics, cycles,
spatio-temporal, range of motion, accelerometry -- with the monocular
(video) and the marker-based (C3D) result drawn together on each.

Colour carries the *source* here (a deliberate exception to the app's
"colour carries the side" rule, the same one ``charts.kinematics.
video_vs_reference_overlay`` already makes): video vs reference is the
comparison, side stays legible as solid (left) vs dashed (right).

Driven entirely by ``pooling.load_run`` -- ``RunResult`` carries the
cycles and stats every panel here needs, and its auto-detected recipe is
the right default when the sidebar's pipeline panel is not on screen (it
is hidden on Analysis).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ..charts import kinematics as K
from ..settings import SETTINGS
from .components import chart, is_dark, page_header
from .page_export import _ready_pairs

#: Flex/ext joints always attempted, then the ISB DOF that a given run's
#: cycles actually carry (C3D + ISB calibration only).
_BASE_JOINTS = ("hip", "knee", "ankle", "trunk", "pelvis_obliquity")

#: Spatio-temporal keys worth a side-by-side row, label -> stats key.
_SPATIOTEMPORAL_ROWS = {
    "Cadence (steps/min)": "cadence_steps_per_min",
    "Stride time (s)": "stride_time_mean_s",
    "Stance (% cycle, left)": "stance_pct_left",
    "Stance (% cycle, right)": "stance_pct_right",
    "Double support (% cycle)": "double_support_pct",
    "Walking speed (m/s)": "walking_speed_m_s",
}


def render() -> None:
    page_header(
        "Markerbased vs Monocular",
        "One video+C3D pair, every parameter, monocular vs marker-based "
        "together. The numbers behind the agreement are on Accuracy vs C3D.",
    )

    groups = _ready_pairs()
    if not groups:
        st.info(
            "No ready video+C3D pair in Recent jobs yet. Extract a video and "
            "import its Vicon C3D on New assessment, tagged with the **same "
            "Patient ID and Condition**, and they pair automatically."
        )
        return

    labels = {key: f"{key[0]} / {key[1]}" for key in groups}
    key = st.selectbox(
        "Pair", list(groups), format_func=lambda k: labels[k], key="mb_pair",
    )
    video_run, c3d_run = _load_pair(key, groups[key])

    if video_run is None or c3d_run is None:
        st.warning(
            "This pair is missing one side (both a video extraction and a C3D "
            "import must be finished for the same Patient ID / Condition)."
        )
        return
    for run, kind in ((video_run, "monocular video"), (c3d_run, "marker-based C3D")):
        if not run.ok:
            st.error(f"The {kind} side failed to analyse: {run.error}")
            return

    st.caption(
        "**Colour = source** — monocular (video) vs marker-based (C3D). "
        "Solid = left, dashed = right. "
        f"Recipe (auto-detected): video — {video_run.config_note or 'default'}; "
        f"C3D — {c3d_run.config_note or 'default'}."
    )

    joints = _shared_joints(video_run, c3d_run)
    tab_kin, tab_cyc, tab_st, tab_rom, tab_acc = st.tabs(
        ["Kinematics", "Cycles", "Spatio-temporal", "Range of motion", "Accelerometry"]
    )
    with tab_kin:
        _kinematics(video_run, c3d_run, joints)
    with tab_cyc:
        _cycles(video_run, c3d_run)
    with tab_st:
        _spatiotemporal(video_run, c3d_run)
    with tab_rom:
        _range_of_motion(video_run, c3d_run, joints)
    with tab_acc:
        _accelerometry(video_run, c3d_run)


# ── data ─────────────────────────────────────────────────────────────


def _load_pair(key: tuple[str, str], jobs: list):
    """(video RunResult, c3d RunResult) for one pair, cached per pair +
    file identity so switching tabs does not re-run the pipeline."""
    from ..jobs import C3D_IMPORT_MODEL_LABEL
    from ..pooling import load_run

    video_path = c3d_path = None
    for job in jobs:
        path = job.result_path(SETTINGS)
        if path is None:
            continue
        if job.model == C3D_IMPORT_MODEL_LABEL:
            c3d_path = path
        else:
            video_path = path
    if video_path is None or c3d_path is None:
        return None, None

    stamp = (
        str(key),
        video_path.stat().st_mtime if video_path.exists() else 0,
        c3d_path.stat().st_mtime if c3d_path.exists() else 0,
    )
    cached = st.session_state.get("_mb_pair_cache")
    if cached and cached[0] == stamp:
        return cached[1], cached[2]

    with st.spinner("Running both sides of the pair through the pipeline..."):
        video_run = load_run(video_path)
        c3d_run = load_run(c3d_path)
    st.session_state["_mb_pair_cache"] = (stamp, video_run, c3d_run)
    return video_run, c3d_run


def _shared_joints(video_run, c3d_run) -> list[str]:
    """Base flex/ext joints plus any ISB DOF both cycles carry."""
    joints = list(_BASE_JOINTS)
    v_sum = (video_run.cycles or {}).get("summary") or {}
    c_sum = (c3d_run.cycles or {}).get("summary") or {}

    def has(summary: dict, joint: str) -> bool:
        return any((summary.get(side) or {}).get(f"{joint}_mean") for side in ("left", "right"))

    joints = [j for j in joints if has(v_sum, j) or has(c_sum, j)]
    for dof in K.ISB_CYCLE_JOINTS:
        if has(c_sum, dof) or has(v_sum, dof):
            joints.append(dof)
    return joints


def _pooled(run) -> dict:
    """RunResult.cycles reshaped to what video_vs_reference_overlay reads."""
    return {"summary": (run.cycles or {}).get("summary") or {}}


# ── panels ───────────────────────────────────────────────────────────


def _kinematics(video_run, c3d_run, joints: list[str]) -> None:
    st.caption(
        "Mean cycle curve per joint, monocular vs marker-based. A constant "
        "vertical gap is an angle-definition offset (ISB vs sagittal), a "
        "shape difference is tracking."
    )
    if not joints:
        st.info("Neither side produced a usable cycle for any joint.")
        return
    sides = _side_picker("mb_kin_sides")
    video_pooled, c3d_pooled = _pooled(video_run), _pooled(c3d_run)
    for joint in joints:
        chart(
            K.video_vs_reference_overlay(
                video_pooled, c3d_pooled, joint=joint, sides=sides, dark=is_dark(),
            ),
            key=f"mb_kin_{joint}",
        )


def _cycles(video_run, c3d_run) -> None:
    st.caption("How many gait cycles each side yielded, and their mean duration.")
    rows = []
    for label, run in (("Monocular (video)", video_run), ("Marker-based (C3D)", c3d_run)):
        cycles = (run.cycles or {}).get("cycles") or []
        durations = [c.get("duration_s") for c in cycles if isinstance(c.get("duration_s"), (int, float))]
        rows.append({
            "Source": label,
            "Cycles": len(cycles),
            "Left": sum(1 for c in cycles if c.get("side") == "left"),
            "Right": sum(1 for c in cycles if c.get("side") == "right"),
            "Mean duration (s)": round(sum(durations) / len(durations), 3) if durations else None,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _spatiotemporal(video_run, c3d_run) -> None:
    st.caption("Every spatio-temporal parameter both sides report, with the difference.")
    v = (video_run.stats or {}).get("spatiotemporal") or {}
    c = (c3d_run.stats or {}).get("spatiotemporal") or {}

    rows = []
    for label, stat_key in _SPATIOTEMPORAL_ROWS.items():
        vv, cv = v.get(stat_key), c.get(stat_key)
        if vv is None and cv is None:
            continue
        rows.append({
            "Parameter": label,
            "Monocular": _round(vv),
            "Marker-based": _round(cv),
            "Difference": _round(vv - cv) if isinstance(vv, (int, float)) and isinstance(cv, (int, float)) else None,
        })

    v_step = _mean_step_length(video_run)
    c_step = c3d_run.marker_step_length_m if c3d_run.marker_step_length_m is not None else _mean_step_length(c3d_run)
    if v_step is not None or c_step is not None:
        rows.append({
            "Parameter": "Step length (m)",
            "Monocular": _round(v_step),
            "Marker-based": _round(c_step),
            "Difference": _round(v_step - c_step) if v_step is not None and c_step is not None else None,
        })
        st.caption("Marker-based step length is measured straight off the 3-D markers (no pixel calibration).")

    if not rows:
        st.info("Neither side reported spatio-temporal parameters.")
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _range_of_motion(video_run, c3d_run, joints: list[str]) -> None:
    st.caption("Cycle range of motion per joint and side, monocular vs marker-based.")
    v_sum = (video_run.cycles or {}).get("summary") or {}
    c_sum = (c3d_run.cycles or {}).get("summary") or {}
    rows = []
    for joint in joints:
        for side in ("left", "right"):
            vr = _rom(v_sum, joint, side)
            cr = _rom(c_sum, joint, side)
            if vr is None and cr is None:
                continue
            rows.append({
                "Joint": K.JOINT_LABELS.get(joint, joint.replace("_", " ").title()),
                "Side": side.title(),
                "Monocular (deg)": _round(vr),
                "Marker-based (deg)": _round(cr),
                "Difference (deg)": _round(vr - cr) if vr is not None and cr is not None else None,
            })
    if not rows:
        st.info("No joint produced a cycle range of motion on either side.")
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _accelerometry(video_run, c3d_run) -> None:
    st.caption(
        "Trunk-accelerometry-style biomarkers derived from the pelvis-centre "
        "trajectory. These are almost always monocular-only: a C3D's markers "
        "give the same pelvis path, but the value is only shown where that "
        "side actually produced one."
    )
    v = (video_run.stats or {}).get("accelerometric") or {}
    c = (c3d_run.stats or {}).get("accelerometric") or {}
    keys = sorted(set(v) | set(c))
    if not keys:
        st.info("Neither side produced accelerometry biomarkers for this pair.")
        return
    rows = [{
        "Biomarker": k.replace("_", " "),
        "Monocular": _round(v.get(k)),
        "Marker-based": _round(c.get(k)),
    } for k in keys]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ── helpers ──────────────────────────────────────────────────────────


def _side_picker(key: str) -> tuple[str, ...]:
    picked = st.multiselect(
        "Sides", ["left", "right"], default=["left", "right"],
        key=key, format_func=str.title,
    )
    return tuple(picked) or ("left", "right")


def _rom(summary: dict, joint: str, side: str) -> float | None:
    mean = (summary.get(side) or {}).get(f"{joint}_mean")
    if not mean:
        return None
    finite = [float(x) for x in mean if isinstance(x, (int, float))]
    return max(finite) - min(finite) if len(finite) >= 2 else None


def _mean_step_length(run) -> float | None:
    step = (run.stats or {}).get("step_length") or {}
    if step.get("unit") != "m":
        return None
    vals = [step.get("step_length_left"), step.get("step_length_right")]
    vals = [x for x in vals if isinstance(x, (int, float))]
    return sum(vals) / len(vals) if vals else None


def _round(value, ndigits: int = 3):
    return round(value, ndigits) if isinstance(value, (int, float)) else None
