"""The parametric explorer.

The screen the app exists for. Every control in the sidebar re-runs only
the stages downstream of it, and the figures redraw against the same
data, so the question "what does this parameter actually change" gets a
visible answer in a fraction of a second rather than a rerun of the whole
chain.
"""

from __future__ import annotations

import copy
import io

import numpy as np
import pandas as pd
import streamlit as st

from ..charts import advanced as A
from ..charts import kinematics as K
from ..pipeline import PipelineResult
from ..quality import assess_quality
from ..runtime import get_runtime
from . import state
from .components import (
    chart,
    empty_state,
    is_dark,
    page_header,
    recording_switcher,
    reproducibility_panel,
    source_loader,
    source_summary,
    stage_status,
)

#: Column layout expected from a user-supplied normative file.
NORMATIVE_COLUMNS = ("joint", "percent", "mean", "sd")


def render() -> None:
    source = state.get_source()
    if source is None:
        page_header("Pipeline explorer")
        source_loader(
            "Nothing loaded.",
            "Pick a finished extraction below, or go to New assessment to load "
            "a pivot JSON or a video.",
            slot="pipeline",
        )
        return

    config = state.get_config()
    runner = state.get_runner()
    page_header(
        "Pipeline explorer",
        "Move any control on the left. Only the stages below it are recomputed.",
    )
    recording_switcher("pipeline")
    source_summary(source)

    result = runner.run(config)
    stage_status(result)

    if not result.ok:
        st.stop()

    assessment = assess_quality(result.data, result.cycles)
    if assessment.status == "rejected":
        st.error(
            "Derived metrics should not be interpreted for this recording: "
            + " ".join(assessment.reasons)
        )
    elif assessment.status == "warning":
        st.warning(" ".join(assessment.reasons))

    tab_kinematics, tab_cycles, tab_spatio, tab_advanced, tab_quality = st.tabs(
        ["Kinematics", "Cycles", "Spatio-temporal", "Advanced analysis", "Signal quality"]
    )

    with tab_kinematics:
        _kinematics_tab(result)
    with tab_cycles:
        _cycles_tab(result, config)
    with tab_spatio:
        _spatiotemporal_tab(result, config)
    with tab_advanced:
        _advanced_tab(result, config)
    with tab_quality:
        _quality_tab(result, runner)

    st.divider()
    reproducibility_panel(
        config,
        source_name=source.name if source.kind in ("json", "c3d") else "video.mp4",
        model=source.model,
        from_json=source.kind in ("json", "demo", "c3d"),
        c3d_options=source.c3d_options if source.kind == "c3d" else None,
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
        "Joints", list(K.SAGITTAL_JOINTS) + ["trunk", "pelvis_obliquity"],
        default=list(K.SAGITTAL_JOINTS), key="kin_joints",
        help="Trunk and pelvis obliquity are once-per-frame values, not "
             "per-side -- shown as a single trace regardless of the Sides "
             "selection below.",
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

    isb_joints = _available_isb_cycle_joints(result.cycles)
    joint_options = list(K.SAGITTAL_JOINTS) + isb_joints

    columns = st.columns([1, 1, 1, 1])
    joint = columns[0].selectbox(
        "Joint", joint_options, index=1, key="cyc_joint",
        format_func=lambda j: K.JOINT_LABELS.get(j, j.title()),
        help="Hip/knee/ankle abd-add and rotation appear here once ISB "
             "reconstruction (Angles section, sidebar) is on and the loaded "
             "source has the marker convention it needs." if not isb_joints
             else None,
    )
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


def _available_isb_cycle_joints(cycles: dict) -> list[str]:
    """Which of K.ISB_CYCLE_JOINTS actually have data in *cycles*.

    pipeline._enrich_cycles_with_isb_dof is a no-op whenever ISB
    reconstruction did not run (or the source lacked the landmarks it
    needs), so this checks the summary it would have written rather than
    assuming the keys exist -- keeps the joint picker honest about what
    this particular run actually has.
    """
    summary = (cycles or {}).get("summary") or {}
    left, right = summary.get("left") or {}, summary.get("right") or {}
    return [
        j for j in K.ISB_CYCLE_JOINTS
        if f"{j}_mean" in left or f"{j}_mean" in right
    ]


def _resolve_normative(choice: str, joint: str, config) -> dict | None:
    """Return the reference band for *joint*, from whichever source is picked."""
    if choice == "None":
        return None

    # ISB DOF use myogait's own, differently-named normative joints where
    # one exists (K.ISB_NORMATIVE_JOINT) -- ankle abd/add and every
    # rotation DOF have none, so this falls through to get_normative_band
    # raising ValueError below, caught the same way as any other unknown
    # joint name.
    normative_joint = K.ISB_NORMATIVE_JOINT.get(joint, joint)

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
            return get_normative_band(normative_joint, stratum=stratum)
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


def _spatiotemporal_tab(result: PipelineResult, config) -> None:
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

    if speed.get("speed_mean") is not None:
        if speed.get("unit") != "m/s":
            st.caption(
                "Speed is in normalised units - set the subject height or measured "
                "femur length in the sidebar to get metres per second."
            )
        elif config.subject.femur_length_mm:
            st.caption(
                "Calibrated from the measured femur length (sidebar) - takes "
                "priority over height whenever both are set."
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

    _extra_screens_panel(result)
    _clinical_scores_panel(result, config)
    _segment_calibration_panel(result, config)


def _extra_screens_panel(result: PipelineResult) -> None:
    """Three targeted screens myogait keeps separate from detect_pathologies().

    Each looks for one specific pattern rather than several at once, so
    they are shown next to it rather than folded in - flagging one does
    not mean the others were checked and cleared.
    """
    with st.expander("Additional targeted screens", expanded=False):
        st.caption(
            "Heuristic screening, not a diagnosis - read alongside the curves, "
            "never instead of them."
        )
        if not result.n_cycles:
            st.caption("No segmented cycle to screen.")
            return

        from myogait import detect_antalgic, detect_equinus, detect_parkinsonian

        equinus = detect_equinus(result.cycles)
        antalgic = detect_antalgic(result.cycles)
        parkinsonian = detect_parkinsonian(result.data, result.cycles)

        columns = st.columns(3)
        with columns[0]:
            st.markdown("**Equinus**")
            if equinus["detected"]:
                st.error("Flagged")
                for entry in equinus["details"]:
                    st.caption(
                        f"{entry['side']}: peak stance dorsiflexion "
                        f"{entry['peak_dorsiflexion']} deg ({entry['severity']})"
                    )
            else:
                st.success("Not flagged")

        with columns[1]:
            st.markdown("**Antalgic**")
            details = antalgic["details"]
            if antalgic["detected"]:
                st.error("Flagged")
                st.caption(
                    f"Short side: {details['short_side']} - stance L "
                    f"{details['stance_left_pct']}% / R {details['stance_right_pct']}%"
                )
            else:
                st.success("Not flagged")
                if details:
                    st.caption(
                        f"Stance L {details['stance_left_pct']}% / "
                        f"R {details['stance_right_pct']}%"
                    )

        with columns[2]:
            st.markdown("**Parkinsonian**")
            if parkinsonian["detected"]:
                st.error("Flagged")
                st.caption(", ".join(parkinsonian.get("features", [])))
            else:
                st.success("Not flagged")


def _clinical_scores_panel(result: PipelineResult, config) -> None:
    """GVS / GPS-2D / SDI / MAP, against both an age-matched and a chosen stratum.

    Both are computed rather than one defaulting to the other: seeing how
    much the scores move between the age-based reference and a different
    one is itself informative - a score that swings a lot between strata
    is a weaker signal than one that does not.
    """
    runtime = get_runtime()
    with st.expander("Clinical profile scores (GVS / GPS-2D / SDI / MAP)", expanded=False):
        if not runtime.has("scores") or not runtime.has("sdi"):
            st.caption(runtime.missing_feature_hint("scores"))
            return
        st.caption(
            "2D sagittal-plane adaptations of the Baker et al. (2009) GPS/MAP, "
            "screening use only - not the full 9-variable 3D GPS. SDI is a "
            "simplified z-score index derived from the GPS-2D, and is explicitly "
            "not the Schwartz & Rozumalski GDI despite the historical name."
        )
        if not result.n_cycles:
            st.caption("No segmented cycle to score.")
            return

        from myogait import (
            gait_profile_score_2d,
            list_strata,
            movement_analysis_profile,
            sagittal_deviation_index,
            select_stratum,
        )

        strata = list(list_strata())
        age = config.subject.age
        age_stratum = select_stratum(age) if age else "adult"

        columns = st.columns(2)
        columns[0].metric(
            "Age-based stratum", age_stratum,
            help=f"select_stratum(age={age})" if age
            else "No Subject age set - select_stratum() defaults to adult.",
        )
        chosen_stratum = columns[1].selectbox(
            "Compare against", strata,
            index=strata.index(age_stratum) if age_stratum in strata else 0,
            key="scores_compare_stratum",
            help="An independent choice, so the columns below show how much the "
                 "scores move when scored against a different normative reference.",
        )

        strata_to_show = [("Age-based", age_stratum)]
        if chosen_stratum != age_stratum:
            strata_to_show.append(("Selected", chosen_stratum))
        else:
            st.caption(f"Selected stratum matches the age-based one ({age_stratum}).")

        score_columns = st.columns(len(strata_to_show))
        map_rows = []
        for col, (label, stratum) in zip(score_columns, strata_to_show):
            gps = gait_profile_score_2d(result.cycles, stratum=stratum)
            sdi = sagittal_deviation_index(result.cycles, stratum=stratum)
            with col:
                st.markdown(f"**{label}** (`{stratum}`)")
                st.metric("GPS-2D overall", _fmt(gps.get("gps_2d_overall")))
                st.metric("SDI overall", _fmt(sdi.get("gdi_2d_overall")))
                sub = st.columns(2)
                sub[0].metric("GPS-2D L", _fmt(gps.get("gps_2d_left")))
                sub[1].metric("GPS-2D R", _fmt(gps.get("gps_2d_right")))

            profile = movement_analysis_profile(result.cycles, stratum=stratum)
            joints = profile.get("joints", [])
            left_vals = profile.get("left", [])
            right_vals = profile.get("right", [])
            for i, joint in enumerate(joints):
                map_rows.append(
                    {
                        "reference": f"{label} ({stratum})",
                        "joint": joint,
                        "GVS left": left_vals[i] if i < len(left_vals) else None,
                        "GVS right": right_vals[i] if i < len(right_vals) else None,
                    }
                )

        if map_rows:
            st.caption("Movement Analysis Profile - GVS per joint and side.")
            st.dataframe(pd.DataFrame(map_rows), use_container_width=True, hide_index=True)


def _segment_calibration_panel(result: PipelineResult, config) -> None:
    """Cross-check the femur-driven calibration against the other segments.

    The step length and walking speed shown above already calibrate from
    the measured femur when one is set (see SubjectConfig.calibration_height_m
    - it feeds myogait's own height_m x 0.245 formula backwards so myogait
    computes from the real femur instead of a population estimate). This
    panel additionally computes an independent scale from every other
    measured segment (tibia, arms, trunk) and flags disagreement between
    them, which is a data-quality signal the single femur-only number
    above cannot give on its own.
    """
    from ..calibration import calibrated_metrics, compute_scales

    measured = config.subject.measured_segments_mm
    with st.expander("Segment-based calibration cross-check", expanded=False):
        st.caption(
            "Step length and walking speed above are already calibrated from the "
            "measured femur when one is set. This table adds every other measured "
            "segment as an independent scale estimate, to catch a measurement or "
            "extraction error the femur alone would not reveal."
        )
        if not measured:
            st.caption(
                "No segment length measured yet. Enter at least one (femur, tibia, "
                "upper arm, forearm, trunk) on the Subject panel to see this."
            )
            return

        calibration = compute_scales(result.data, measured)
        if not calibration.segments:
            st.warning(
                "None of the measured segments could be matched to landmarks in "
                "this recording."
            )
            return

        rows = [
            {
                "segment": s.segment,
                "measured_mm": s.measured_mm,
                "pixel_mean": round(s.pixel_mean, 4),
                "pixel_cv_%": s.pixel_cv,
                "scale_mm_per_unit": round(s.scale_m_per_unit * 1000, 3),
                "unstable": s.unstable,
            }
            for s in calibration.segments
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        if calibration.flagged:
            st.warning(
                f"Segments disagree by {calibration.disagreement_pct:.1f}% on the "
                "derived scale - check the measurements and the extraction quality "
                "before trusting the combined estimate below."
            )

        if not calibration.combined_scale or not result.n_cycles:
            return
        st.caption(
            "Below: the same metrics recomputed from the combined multi-segment "
            "scale (all rows above, weighted by stability) - compare against the "
            "femur-only numbers at the top of this tab."
        )
        metrics = calibrated_metrics(
            result.data,
            result.cycles,
            calibration.combined_scale,
            isotropic=get_runtime().step_length_isotropic_native,
        )
        columns = st.columns(3)
        columns[0].metric("Step length (L), multi-segment", _fmt(metrics.step_length_left_m, "m"))
        columns[1].metric("Step length (R), multi-segment", _fmt(metrics.step_length_right_m, "m"))
        columns[2].metric("Walking speed, multi-segment", _fmt(metrics.speed_mean_m_s, "m/s"))


# ── Advanced analysis ────────────────────────────────────────────────


def _advanced_tab(result: PipelineResult, config) -> None:
    """Twelve myogait analysis functions with no other home in this app.

    None of these feed analyze_gait()'s own summary - they are called
    directly, each behind its own expander so an empty result on one
    (too few cycles for PCA, no height for Froude normalisation) does
    not block the others.
    """
    st.caption(
        "Functions myogait exposes but does not run automatically - each is "
        "computed on demand here, independent of the Spatio-temporal tab above."
    )
    if not result.n_cycles:
        empty_state("No segmented cycle - most of these need one.")
        return

    _screening_metrics_panel(result, config)
    _cadence_panel(result)
    _com_panel(result)
    _sway_panel(result)
    _derivatives_panel(result)
    _time_frequency_panel(result)
    _pca_panel(result)


def _screening_metrics_panel(result: PipelineResult, config) -> None:
    from myogait import (
        arm_swing_analysis,
        compute_rom_summary,
        single_support_time,
        speed_normalized_params,
        stride_variability,
        toe_clearance,
    )

    blocks = [
        ("Single support time", single_support_time(result.data, result.cycles)),
        ("Toe clearance (minimum, swing phase)", toe_clearance(result.data, result.cycles)),
        ("Stride variability (CV of multiple parameters)", stride_variability(result.data, result.cycles)),
        ("Arm swing", arm_swing_analysis(result.data, result.cycles)),
    ]

    height_m = config.subject.height_m
    if height_m:
        blocks.append(
            ("Speed-normalised (Froude)", speed_normalized_params(result.data, result.cycles, height_m))
        )
    else:
        blocks.append(("Speed-normalised (Froude)", None))

    with st.expander("Screening metrics", expanded=False):
        for title, block in blocks:
            st.markdown(f"**{title}**")
            if block is None:
                st.caption("Needs the Subject height (sidebar) to normalise by leg length.")
                continue
            st.dataframe(_flatten(block), use_container_width=True, hide_index=True)

        st.divider()
        st.markdown("**Range of motion per cycle**")
        rom = compute_rom_summary(result.data, result.cycles)
        rows = [
            {"joint_side": key, **{k: v for k, v in stats.items() if k != "rom_per_cycle"}}
            for key, stats in rom.items()
        ]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _cadence_panel(result: PipelineResult) -> None:
    from myogait import instantaneous_cadence

    with st.expander("Instantaneous cadence", expanded=False):
        st.caption(
            "Step time between every consecutive heel strike, regardless of side - "
            "shows cadence drift within the trial that an averaged number hides."
        )
        cadence = instantaneous_cadence(result.data)
        if not cadence.get("cadence"):
            st.caption("Not enough heel-strike events.")
            return
        chart(A.cadence_timeline(cadence, dark=is_dark()), key="fig_cadence")
        columns = st.columns(3)
        columns[0].metric("Mean", _fmt(cadence.get("mean"), "steps/min"))
        columns[1].metric("CV", _fmt(cadence.get("cv"), "%"))
        columns[2].metric("Trend", _fmt(cadence.get("trend_slope"), "steps/min per s"))


def _com_panel(result: PipelineResult) -> None:
    from myogait import estimate_center_of_mass

    with st.expander("Center of mass", expanded=False):
        st.caption(
            "Segmental estimate from Winter's body-segment-parameter tables - "
            "vertical excursion and path smoothness (inverse jerk)."
        )
        com = estimate_center_of_mass(result.data)
        if not com.get("com_y"):
            st.caption("Not enough landmark coverage to estimate a center of mass.")
            return
        fps = result.data.get("meta", {}).get("fps", 30.0)
        chart(A.com_timeline(com, fps, dark=is_dark()), key="fig_com")
        columns = st.columns(2)
        columns[0].metric("Vertical excursion", _fmt(com.get("vertical_excursion"), "norm."))
        columns[1].metric("Smoothness (0-1)", _fmt(com.get("smoothness")))


def _sway_panel(result: PipelineResult) -> None:
    from myogait import postural_sway

    with st.expander("Postural sway (ankle-midpoint proxy)", expanded=False):
        st.caption(
            "Uses the ankle midpoint as a centre-of-pressure approximation - built "
            "for a standing trial, so on a walking trial it mostly reflects stride "
            "width and progression rather than balance."
        )
        sway = postural_sway(result.data)
        if not sway.get("cop_x"):
            st.caption("Not enough valid frames.")
            return
        chart(A.sway_scatter(sway, dark=is_dark()), key="fig_sway")
        columns = st.columns(4)
        columns[0].metric("95% ellipse area", _fmt(sway.get("ellipse_area"), "norm.²"))
        columns[1].metric("Sway velocity", _fmt(sway.get("sway_velocity"), "norm./s"))
        columns[2].metric("ML range", _fmt(sway.get("ml_range"), "norm."))
        columns[3].metric("AP range", _fmt(sway.get("ap_range"), "norm."))


_DERIVATIVE_JOINTS = ("hip_L", "hip_R", "knee_L", "knee_R", "ankle_L", "ankle_R")


def _derivatives_panel(result: PipelineResult) -> None:
    from myogait import compute_derivatives

    with st.expander("Angular velocity & acceleration", expanded=False):
        st.caption(
            "Central-difference derivatives of the joint angle curves. Computed on "
            "a copy of the data - it does not add a derivatives block to what the "
            "other tabs see."
        )
        columns = st.columns([2, 1])
        joints = columns[0].multiselect(
            "Joints", list(_DERIVATIVE_JOINTS), default=["knee_L", "knee_R"], key="adv_deriv_joints"
        )
        order = columns[1].radio(
            "Order", ["velocity", "acceleration"], key="adv_deriv_order", horizontal=True
        )
        if not joints:
            st.caption("Select at least one joint.")
            return

        derivatives = compute_derivatives(copy.deepcopy(result.data), joints=list(joints))
        velocity = {j: d["velocity"] for j, d in derivatives.items()}
        acceleration = {
            j: d["acceleration"] for j, d in derivatives.items() if "acceleration" in d
        }
        fps = result.data.get("meta", {}).get("fps", 30.0)
        chart(
            A.derivatives_timeline(velocity, acceleration, fps, tuple(joints), order=order, dark=is_dark()),
            key="fig_derivatives",
        )


def _time_frequency_panel(result: PipelineResult) -> None:
    from myogait import time_frequency_analysis

    with st.expander("Time-frequency analysis", expanded=False):
        st.caption(
            "Continuous wavelet (or short-time Fourier) transform of one joint's "
            "angle signal - where in the recording a given frequency concentrates, "
            "rather than one number for the whole trial."
        )
        columns = st.columns(2)
        joint = columns[0].selectbox(
            "Joint", list(_DERIVATIVE_JOINTS), index=2, key="adv_tf_joint"
        )
        method = columns[1].radio(
            "Method", ["cwt", "stft"], key="adv_tf_method", horizontal=True,
            help="cwt: continuous wavelet transform (Morlet). stft: short-time "
                 "Fourier transform.",
        )
        try:
            tf = time_frequency_analysis(result.data, joints=[joint], method=method)
        except Exception as exc:
            st.error(f"{type(exc).__name__}: {exc}")
            return
        chart(A.spectrogram(tf[joint], dark=is_dark()), key="fig_spectrogram")
        st.metric("Dominant frequency", _fmt(tf[joint].get("dominant_frequency"), "Hz"))


def _pca_cycles_compat(cycles: dict) -> dict:
    """Work around a key mismatch in myogait's pca_waveform_analysis().

    Its own docstring says it reads ``cycle["angles"][joint_side]``, but
    segment_cycles() only ever produces ``cycle["angles_normalized"][joint]``
    (unsuffixed - a cycle already belongs to one side). Called as
    documented, pca_waveform_analysis() therefore always finds zero
    waveforms. This rebuilds the side-suffixed view it expects, on a copy,
    so the cached cycles this app keeps elsewhere are never touched.
    """
    patched = copy.deepcopy(cycles)
    for cycle in patched.get("cycles", []):
        suffix = "L" if cycle.get("side") == "left" else "R"
        cycle["angles"] = {
            f"{joint}_{suffix}": values
            for joint, values in (cycle.get("angles_normalized") or {}).items()
        }
    return patched


def _pca_panel(result: PipelineResult) -> None:
    from myogait import pca_waveform_analysis

    with st.expander("PCA waveform analysis", expanded=False):
        st.caption(
            "Principal components of the time-normalised joint-angle waveforms "
            "across cycles - the dominant patterns of cycle-to-cycle variation, "
            "and how far each cycle deviates along them. Needs at least 3 valid "
            "cycles for the chosen joint."
        )
        joint = st.selectbox(
            "Joint", list(_DERIVATIVE_JOINTS), index=2, key="adv_pca_joint"
        )
        try:
            pca = pca_waveform_analysis(_pca_cycles_compat(result.cycles), joints=[joint])
        except ValueError as exc:
            st.caption(str(exc))
            return
        chart(A.pca_components(pca[joint], dark=is_dark()), key="fig_pca")
        st.caption(
            f"{pca[joint]['n_cycles_used']} cycle(s) used. Explained variance: "
            + ", ".join(
                f"PC{i + 1} {v * 100:.0f}%"
                for i, v in enumerate(pca[joint]["explained_variance_ratio"])
            )
        )


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
