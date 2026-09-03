"""The control panel.

Every lever myogait exposes downstream of extraction lives here, grouped
in pipeline order so the sidebar reads top-to-bottom the way the data
flows. Controls whose backing function is missing from the installed
myogait are disabled rather than hidden, with the reason attached -- a
greyed-out control that explains itself teaches the version boundary;
a hidden one just looks like the feature does not exist.
"""

from __future__ import annotations

from dataclasses import replace

import streamlit as st

from ..branding import BRANDING
from ..glossary import find_one
from ..pipeline import (
    AnglesConfig,
    BiasConfig,
    CyclesConfig,
    EventsConfig,
    NormalizeConfig,
    PipelineConfig,
    SubjectConfig,
    study_from_data,
)
from ..runtime import get_runtime
from . import components

_SEE_REFERENCE = " See the Index page for what each option actually does."

#: Smoothing steps from myogait.normalize.NORMALIZE_STEPS, with the
#: optional dependency each one needs.
FILTER_CHOICES = {
    "butterworth": "",
    "savgol": "",
    "moving_mean": "",
    "median": "",
    "spline": "",
    "kalman": "",
    "loess": "statsmodels",
    "wavelet": "pywt",
}


def _available_filters() -> list[str]:
    import importlib.util

    available = []
    for name, requirement in FILTER_CHOICES.items():
        if requirement and importlib.util.find_spec(requirement) is None:
            continue
        available.append(name)
    return available


#: Session-state key tracking the last Subject femur value seen, so the
#: sync into Events fires only on a real change (see _sync_femur below).
_K_LAST_SUBJECT_FEMUR = "mg_last_subject_femur_mm"


def render(config: PipelineConfig, source=None) -> PipelineConfig:
    """Draw the controls and return the configuration they describe.

    *source* (a ``ui.state.Source``, optional) is read-only here, for the
    one control that needs to know something about the loaded source
    itself rather than just the installed myogait -- whether it resolved
    the paired landmarks ISB reconstruction needs (see the isb_reconstruction
    checkbox in ``_angles_section``). Every other section stays config-only
    on purpose; do not grow this into a general escape hatch.
    """
    runtime = get_runtime()

    config = _seed_metadata_from_source(config, source)
    subject = _subject_section(config.subject)
    _study_section()
    normalize = _normalize_section(config.normalize)
    angles = _angles_section(config.angles, runtime, source)
    restore_ankle = _ankle_dynamics_toggle(config.restore_ankle_dynamics, runtime)
    bias = _bias_section(config.bias, angles, runtime)
    events = _events_section(_sync_femur_from_subject(config.events, subject), runtime)
    cycles = _cycles_section(config.cycles, runtime)

    return PipelineConfig(
        normalize=normalize,
        angles=angles,
        events=events,
        cycles=cycles,
        bias=bias,
        subject=subject,
        restore_ankle_dynamics=restore_ankle,
    )


def _ankle_dynamics_toggle(current: bool, runtime) -> bool:
    """The ankle push-off restoration toggle.

    Unlike the ISB reconstruction (a no-op on anything but a full-marker
    C3D), this correction acts on *every* source, patient video included --
    it re-adds the fast plantar-flexion the pose estimator's low-pass
    attenuates. It is on by default because it is validated
    (leave-one-subject-out) and cannot fabricate a push-off that is not
    there (cadence-adaptive, frequency-domain, no template), but it stays a
    visible switch precisely because it changes the primary measurement.
    """
    ok = runtime.has("ankle_dynamics")
    with st.expander("Ankle dynamics", expanded=False):
        return st.checkbox(
            "Restore ankle push-off (deconvolution)",
            value=current and ok,
            disabled=not ok,
            help="The 2-D pose estimator acts as a low-pass filter on the ankle "
                 "waveform and flattens the fast push-off, under-reading ankle "
                 "ROM by ~11 deg vs Vicon. This inverts that filter (calibrated "
                 "once against Vicon, applied cadence-adaptively in Hz) and adds "
                 "the systematic per-phase deficit back to every cycle, leaving "
                 "inter-cycle variability untouched. It makes no healthy-gait "
                 "assumption and will not invent a push-off that is absent, so it "
                 "is safe on pathological gait -- but it does change the ankle "
                 "numbers on every source, so it is left switchable. Halves the "
                 "ankle ROM bias (|error| 10.8 -> 6.7 deg, leave-one-subject-out)."
            if ok else runtime.missing_feature_hint("ankle_dynamics"),
        )


#: Session-state slots for the metadata round-trip.
_K_META_SEEDED = "mg_meta_seeded_key"  # the source key we last pre-filled from
K_STUDY_EDIT = "mg_study_edit"          # the edited study dict, read at export
#: Every Subject + Study widget key, cleared when a new source is loaded so the
#: controls re-initialise from the freshly seeded config instead of showing the
#: previous file's values (Streamlit keeps keyed-widget state across reruns).
_METADATA_WIDGET_KEYS = (
    "subj_height", "subj_age", "subj_weight", "subj_sex", "subj_pathology",
    "subj_femur", "subj_tibia", "subj_upper_arm", "subj_forearm",
    "subj_trunk", "subj_foot",
    "study_patient_edit", "study_run_edit", "study_group_edit",
    "study_condition_edit",
)


def _seed_metadata_from_source(config: PipelineConfig, source) -> PipelineConfig:
    """Pre-fill Subject + Study from a newly loaded pivot's stored metadata.

    Runs once per source (guarded on ``source.key``): it seeds the Subject
    config from ``data["subject"]`` (incl. the measured segments myogait now
    persists) and the Study editor from ``data["study"]``, then clears the
    metadata widget keys so the controls show the loaded values rather than
    the previous file's. On later reruns for the same source it is a no-op, so
    the user's own edits are preserved.
    """
    if source is None:
        return config
    key = getattr(source, "key", None) or getattr(source, "name", None)
    if st.session_state.get(_K_META_SEEDED) == key:
        return config
    data = getattr(source, "data", None) or {}
    config = replace(config, subject=SubjectConfig.from_subject_dict(data.get("subject")))
    st.session_state[K_STUDY_EDIT] = study_from_data(data)
    for widget_key in _METADATA_WIDGET_KEYS:
        st.session_state.pop(widget_key, None)
    st.session_state[_K_META_SEEDED] = key
    return config


def _study_section() -> None:
    """Editable study identifiers, pre-filled from the loaded pivot.

    Kept in ``st.session_state[K_STUDY_EDIT]`` (not in ``PipelineConfig`` --
    study is metadata, not a pipeline input, so editing it must not
    invalidate the analysis cache). Applied onto the pivot at export time.
    """
    study = dict(st.session_state.get(K_STUDY_EDIT) or {})
    with st.expander("Study / condition (saved in the JSON on export)", expanded=False):
        st.caption(
            "Pre-filled from the loaded pivot. Editing here changes what the "
            "exported JSON carries and how the Cohort tab groups recordings; "
            "it does not affect the kinematic analysis."
        )
        c1, c2 = st.columns(2)
        patient = c1.text_input("Patient ID", value=study.get("patient_id", ""),
                                key="study_patient_edit")
        run = c2.text_input("Run", value=study.get("run", ""), key="study_run_edit")
        c3, c4 = st.columns(2)
        group = c3.text_input("Group", value=study.get("group", ""),
                              key="study_group_edit")
        condition = c4.text_input("Condition", value=study.get("condition", ""),
                                  key="study_condition_edit")
    updated = dict(study)
    for name, value in (("patient_id", patient), ("run", run),
                        ("group", group), ("condition", condition)):
        if value.strip():
            updated[name] = value.strip()
        else:
            updated.pop(name, None)
    st.session_state[K_STUDY_EDIT] = updated


def _subject_section(cfg: SubjectConfig) -> SubjectConfig:
    with st.expander("Subject", expanded=False):
        st.caption(
            "Height or measured femur length is what changes results: without "
            "one of the two, step length and walking speed stay in normalised "
            "units instead of metres. The femur below takes priority when both "
            "are set - it calibrates from this subject's actual anatomy instead "
            "of a population ratio."
        )
        height = st.number_input(
            "Height (m)",
            min_value=0.0,
            max_value=2.5,
            value=float(cfg.height_m or 0.0),
            step=0.01,
            format="%.2f",
            help="0 leaves it unset.",
            key="subj_height",
        )
        columns = st.columns(2)
        age = columns[0].number_input(
            "Age", min_value=0, max_value=120, value=int(cfg.age or 0), step=1,
            key="subj_age",
        )
        weight = columns[1].number_input(
            "Weight (kg)", min_value=0.0, max_value=250.0,
            value=float(cfg.weight_kg or 0.0), step=0.5, key="subj_weight",
        )
        sex = st.selectbox(
            "Sex", ["", "M", "F", "X"],
            index=["", "M", "F", "X"].index(cfg.sex or ""),
            key="subj_sex",
        )
        pathology = st.text_input("Pathology", value=cfg.pathology or "",
                                  key="subj_pathology")

        st.divider()
        st.markdown("**Measured segment lengths (mm) - optional**")
        st.caption(
            "myogait calibrates step length and speed from height alone by "
            "default (a fixed 24.5% femur-to-height ratio) - a population "
            "estimate that can be wrong for an individual, especially outside "
            "typical adult proportions. Femur below takes priority over height "
            "for that calibration whenever it is set: step length, stride "
            "length and walking speed on the Spatio-temporal tab all use it. "
            "The other segments (tibia, arms, trunk) do not replace anything - "
            "they only feed the cross-check panel on that same tab, comparing "
            "several independent scale estimates against each other. 0 leaves a "
            "segment unmeasured. Femur also pre-fills the gk_* detector "
            "reference below."
        )
        columns = st.columns(2)
        femur = columns[0].number_input(
            "Femur (hip-knee)", min_value=0.0, max_value=600.0,
            value=float(cfg.femur_length_mm or 0.0), step=5.0, key="subj_femur",
        )
        tibia = columns[1].number_input(
            "Tibia (knee-ankle)", min_value=0.0, max_value=600.0,
            value=float(cfg.tibia_length_mm or 0.0), step=5.0, key="subj_tibia",
        )
        columns = st.columns(2)
        upper_arm = columns[0].number_input(
            "Upper arm (shoulder-elbow)", min_value=0.0, max_value=500.0,
            value=float(cfg.upper_arm_length_mm or 0.0), step=5.0, key="subj_upper_arm",
        )
        forearm = columns[1].number_input(
            "Forearm (elbow-wrist)", min_value=0.0, max_value=500.0,
            value=float(cfg.forearm_length_mm or 0.0), step=5.0, key="subj_forearm",
        )
        columns = st.columns(2)
        trunk = columns[0].number_input(
            "Trunk (shoulder-hip)", min_value=0.0, max_value=800.0,
            value=float(cfg.trunk_length_mm or 0.0), step=5.0, key="subj_trunk",
        )
        foot = columns[1].number_input(
            "Foot (heel-toe)", min_value=0.0, max_value=400.0,
            value=float(cfg.foot_length_mm or 0.0), step=5.0, key="subj_foot",
            help="Averaged with femur for the tightest calibration myogait "
                 "documents (myogait >= 0.7.0). Does not feed the cross-check "
                 "panel below (segment_lengths() has no foot entry).",
        )

    return SubjectConfig(
        age=int(age) or None,
        sex=sex or None,
        height_m=float(height) or None,
        weight_kg=float(weight) or None,
        pathology=pathology or None,
        femur_length_mm=float(femur) or None,
        tibia_length_mm=float(tibia) or None,
        upper_arm_length_mm=float(upper_arm) or None,
        forearm_length_mm=float(forearm) or None,
        trunk_length_mm=float(trunk) or None,
        foot_length_mm=float(foot) or None,
    )


def _sync_femur_from_subject(cfg: EventsConfig, subject: SubjectConfig) -> EventsConfig:
    """Push a *changed* Subject femur measurement into the Events reference.

    Events keeps its own field -- it needs a plausible value even with no
    subject data at all (400 mm default). The sync fires only when the
    Subject value changes between reruns, so a manual override on the
    Events slider is not fought back on a rerun where the Subject value
    stayed the same.
    """
    last = st.session_state.get(_K_LAST_SUBJECT_FEMUR)
    current = subject.femur_length_mm
    st.session_state[_K_LAST_SUBJECT_FEMUR] = current
    if current is not None and current != last:
        return replace(cfg, femur_length_mm=float(current))
    return cfg


def _normalize_section(cfg: NormalizeConfig) -> NormalizeConfig:
    components.sidebar_section_marker("01", BRANDING.primary_red)
    with st.expander("1. Signal conditioning", expanded=True):
        options = _available_filters()
        filters = st.multiselect(
            "Filters (applied in order)",
            options=options,
            default=[f for f in cfg.filters if f in options],
            help="Leave empty to work on the raw landmarks. Each one is a "
                 "different smoothing/denoising method - butterworth is the "
                 "default." + _SEE_REFERENCE,
        )

        cutoff = cfg.butterworth_cutoff
        order = cfg.butterworth_order
        if "butterworth" in filters:
            cutoff = st.slider(
                "Butterworth cutoff (Hz)", 0.5, 15.0, float(cfg.butterworth_cutoff), 0.5,
                help="Lower is smoother. Too low removes real gait content.",
            )
            order = st.slider("Butterworth order", 1, 6, int(cfg.butterworth_order))

        st.divider()
        st.caption("Quality gates, applied before filtering.")
        use_confidence = st.checkbox(
            "Drop low-confidence landmarks", value=cfg.confidence_threshold is not None,
            help=(find_one("confidence_filter") or find_one("normalize")).summary,
        )
        confidence = (
            st.slider("Confidence threshold", 0.0, 1.0,
                      float(cfg.confidence_threshold or 0.3), 0.05)
            if use_confidence else None
        )
        use_outliers = st.checkbox(
            "Interpolate outliers", value=cfg.outlier_z is not None,
            help=find_one("detect_outliers").summary,
        )
        outlier_z = (
            st.slider("Outlier threshold (SD)", 1.0, 6.0, float(cfg.outlier_z or 3.0), 0.5)
            if use_outliers else None
        )
        gap = st.slider(
            "Max interpolated gap (frames)", 0, 60, int(cfg.gap_max_frames),
            help="Passed to normalize() - short runs of missing landmark data up "
                 "to this many frames are interpolated rather than left as gaps.",
        )

        st.divider()
        columns = st.columns(2)
        center = columns[0].checkbox(
            "Center on torso", value=cfg.center,
            help=find_one("center_on_torso").summary,
        )
        align = columns[1].checkbox(
            "Align skeleton", value=cfg.align, disabled=center,
            help=find_one("center_on_torso").summary,
        )
        correct_limbs = st.checkbox(
            "Correct bilateral swaps", value=cfg.correct_limbs,
            help=find_one("correct_bilateral").summary,
        )
        coherence = st.checkbox(
            "Score frame coherence", value=cfg.coherence,
            help=find_one("frame_coherence_score").summary,
        )

    return NormalizeConfig(
        filters=tuple(filters),
        butterworth_cutoff=float(cutoff),
        butterworth_order=int(order),
        center=center,
        align=align and not center,
        correct_limbs=correct_limbs,
        gap_max_frames=int(gap),
        confidence_threshold=confidence,
        outlier_z=outlier_z,
        coherence=coherence,
    )


def _angles_section(cfg: AnglesConfig, runtime, source=None) -> AnglesConfig:
    components.sidebar_section_marker("02", BRANDING.primary_blue)
    with st.expander("2. Joint kinematics", expanded=True):
        methods = list(runtime.angle_methods)
        method = st.selectbox(
            "Angle method", methods,
            index=methods.index(cfg.method) if cfg.method in methods else 0,
            help=find_one("compute_angles").summary,
        )
        correction = st.slider(
            "2D ROM correction factor", 0.5, 1.2, float(cfg.correction_factor), 0.05,
            help="myogait suggests 0.8 for MediaPipe and 1.0 for 3D-capable models.",
        )

        # Split at 13 controls: what you are here to explore (calibration
        # method and its thresholds) against what you almost never touch
        # (correctness fixes myogait 0.8.x ships on by default, plus the
        # opt-in projection/drift corrections). Density was the actual
        # problem this tab split fixes, not spacing -- see DESIGN.md.
        tab_calibration, tab_corrections = st.tabs(["Calibration", "Corrections"])

        with tab_calibration:
            calibrate = st.checkbox(
                "Neutral calibration", value=cfg.calibrate,
                help="Uses the first calibration_frames frames as a neutral-pose "
                     "reference, so angles read as flexion/extension from a "
                     "standing baseline rather than from the raw geometric angle. "
                     "Ankle is myogait's default calibrated joint.",
            )
            calibration_frames = (
                st.slider("Calibration frames", 5, 120, int(cfg.calibration_frames))
                if calibrate else cfg.calibration_frames
            )
            calibration_dynamic_fallback = (
                st.checkbox(
                    "Dynamic calibration fallback", value=cfg.calibration_dynamic_fallback,
                    help="If those first calibration_frames show no meaningful motion "
                         "(angle std below the threshold below), calibrate from the "
                         "median of all valid frames instead - a patient who starts "
                         "standing in a pathological or asymmetric pose would "
                         "otherwise shift the whole cycle by that offset. Rule this "
                         "out before reading a persistent ankle error as a hardware "
                         "or measurement ceiling.",
                )
                if calibrate else cfg.calibration_dynamic_fallback
            )
            calibration_min_std_deg = (
                st.slider(
                    "Static-window threshold (deg)", 0.1, 5.0,
                    float(cfg.calibration_min_std_deg), 0.1,
                    help="Below this angle std over the calibration window, the "
                         "window is treated as static and the dynamic fallback "
                         "above kicks in.",
                )
                if calibrate and calibration_dynamic_fallback else cfg.calibration_min_std_deg
            )
            max_offset_ok = runtime.calibration_guard_supported
            calibration_max_offset_deg = (
                st.slider(
                    "Max plausible calibration offset (deg)", 5.0, 60.0,
                    float(cfg.calibration_max_offset_deg), 1.0,
                    disabled=not max_offset_ok,
                    help="Skips calibration for a joint (with a warning, instead of "
                         "shifting the whole cycle) when the estimated neutral-pose "
                         "offset exceeds this - the guard against a clip whose "
                         "'neutral' window actually caught mid-gait motion."
                    if max_offset_ok
                    else f"compute_angles(calibration_max_offset_deg=) is not "
                         f"available in myogait {runtime.myogait_version or 'unknown'} "
                         "(needs 0.8.0+).",
                )
                if calibrate else cfg.calibration_max_offset_deg
            )

        with tab_corrections:
            st.caption(
                "canonicalize_signs and the C3D ankle reference are myogait "
                "0.8.x correctness fixes, on by default - leave them alone "
                "unless you have a specific reason not to. Everything below "
                "that divider is opt-in and off by default."
            )
            columns = st.columns(2)
            ankle_sliding = columns[0].checkbox(
                "Ankle sliding fix", value=cfg.correct_ankle_sliding,
                help=find_one("detect_ankle_swap").summary,
            )
            aspect = columns[1].checkbox(
                "Aspect ratio", value=cfg.apply_aspect_ratio,
                help=find_one("apply_aspect_ratio").summary,
            )

            signs_ok = runtime.has("canonicalize_signs")
            canonicalize_signs = st.checkbox(
                "Canonical flexion-positive signs", value=cfg.canonicalize_signs and signs_ok,
                disabled=not signs_ok,
                help="Enforces a flexion-positive sagittal convention independent of "
                     "walking direction, so two passes in opposite directions - or a "
                     "video compared against its C3D reference - cannot disagree in "
                     "sign. A correctness fix: leave this on unless you specifically "
                     "need myogait's raw, direction-dependent sign."
                if signs_ok else runtime.missing_feature_hint("canonicalize_signs"),
            )

            c3d_ref_ok = runtime.has("c3d_reference_angles")
            c3d_reference_ankle = st.checkbox(
                "3-D ankle reference for C3D sources",
                value=cfg.c3d_reference_ankle and c3d_ref_ok,
                disabled=not c3d_ref_ok,
                help="The 2-D sagittal projection is faithful for hip/knee (r >= "
                     "0.99 vs a Vicon 3-D reference) but collapses the ankle (r ~ "
                     "0.4, ROM halved) - recomputes it from load_c3d's 3-D marker "
                     "positions instead. A no-op on a video or JSON source (no 3-D "
                     "markers to recompute from), so safe to leave on."
                if c3d_ref_ok else runtime.missing_feature_hint("c3d_reference_angles"),
            )

            isb_supported = runtime.has("isb_reconstruction")
            isb_diag = (getattr(source, "isb_diagnostics", None) or {}) if source else {}
            isb_capable = bool(isb_diag.get("capable"))
            isb_ok = isb_supported and isb_capable
            isb_tier_label = {
                "tier1": "direct, no calibration file",
                "tier2": "static trial only",
                "tier3": "VSK + static + protocol, calibrated",
            }.get(isb_diag.get("tier"), "direct, no calibration file")
            if isb_supported and source is not None and not isb_capable:
                isb_hint = (
                    "This source did not resolve the paired medial/lateral "
                    "landmarks ISB needs (see the C3D tab's status message) "
                    "-- one point per joint isn't enough to build an "
                    "anatomical frame from."
                )
            elif not isb_supported:
                isb_hint = runtime.missing_feature_hint("isb_reconstruction")
            else:
                isb_hint = (
                    f"Recomputes hip/knee/ankle from proper ISB pelvis/thigh/"
                    f"shank/foot anatomical frames instead of this method's "
                    f"trunk-referenced 2-D projection -- a different "
                    f"definition of the angle, not just a precision gap "
                    f"(audit: r>=0.99 between the two, but a 10-17 degree "
                    f"constant offset on hip/knee; confirmed for hip/knee "
                    f"specifically across the Bath BioCV cohort, 356 trial x "
                    f"joint x side -- a clean, subject-specific level shift, "
                    f"waveform r=0.975 preserved). Tier available for this "
                    f"source: {isb_tier_label}, decided by which calibration "
                    f"files were attached in the C3D tab. A no-op on any "
                    f"source that doesn't resolve the paired landmarks, so "
                    f"safe to leave on."
                )
            # Deliberately a separate on/off from the Cohort page's own ISB
            # checkbox (page_pool.py) -- this one applies only to the single
            # recording open here (Trial Explorer, Comparator, etc), that
            # one to every recording loaded into a cohort. The two are not
            # linked; changing one does not change the other. Flagged by the
            # audit (UX-03) as a source of confusion given the near-identical
            # wording -- full unification is deferred, this note is the
            # interim fix.
            isb_hint += (
                " This is a separate setting from the Cohort page's own "
                "'ISB reconstruction for Vicon/C3D references' checkbox -- "
                "changing one does not change the other."
            )
            isb_reconstruction = st.checkbox(
                "ISB reconstruction (hip/knee/ankle) -- this recording",
                value=cfg.isb_reconstruction and isb_ok,
                disabled=not isb_ok,
                help=isb_hint,
            )

            st.divider()
            frontal_ok = runtime.has("frontal_angles")
            frontal = st.checkbox(
                "Frontal-plane angles",
                value=cfg.frontal and frontal_ok,
                disabled=not frontal_ok,
                help="Needs depth data to be meaningful."
                if frontal_ok else runtime.missing_feature_hint("frontal_angles"),
            )
            perspective_ok = runtime.has("perspective")
            perspective = st.checkbox(
                "M1 perspective correction",
                value=cfg.perspective and perspective_ok,
                disabled=not perspective_ok,
                help="Zero-parameter geometry, computed from this recording's own "
                     "segment lengths. Adds no population assumption, so it is safe "
                     "on any gait."
                if perspective_ok else runtime.missing_feature_hint("perspective"),
            )
            detrend_ok = runtime.has("detrend")
            detrend = st.checkbox(
                "Remove linear drift",
                value=cfg.detrend and detrend_ok,
                disabled=not detrend_ok,
                help="Removes the slow angular drift a fixed camera introduces over a "
                     "long walk, preserving the anatomical mean and per-cycle ROM."
                if detrend_ok else runtime.missing_feature_hint("detrend"),
            )

    return AnglesConfig(
        method=method,
        correction_factor=float(correction),
        calibrate=calibrate,
        calibration_frames=int(calibration_frames),
        calibration_dynamic_fallback=calibration_dynamic_fallback,
        calibration_min_std_deg=float(calibration_min_std_deg),
        calibration_max_offset_deg=float(calibration_max_offset_deg),
        canonicalize_signs=canonicalize_signs,
        c3d_reference_ankle=c3d_reference_ankle,
        isb_reconstruction=isb_reconstruction,
        correct_ankle_sliding=ankle_sliding,
        apply_aspect_ratio=aspect,
        frontal=frontal,
        perspective=perspective,
        detrend=detrend,
    )


def _bias_section(cfg: BiasConfig, angles: AnglesConfig, runtime) -> BiasConfig:
    """The bias corrections, behind their warning.

    These are the only controls in the app that can make a pathological
    recording look healthy, so the warning is shown before the toggles
    rather than hidden in a tooltip, and the hip and knee models are
    disabled until the perspective correction they were fitted on top of
    is enabled.
    """
    with st.expander("2b. Bias corrections - read first", expanded=False):
        st.warning(
            "These are LASSO models fitted on **healthy young adults** against "
            "Vicon. myogait's own documentation states they re-inject a healthy "
            "curve exactly where neuromuscular disease shows itself: swing knee "
            "flexion (DMD, CMT), ankle push-off (drop foot), end-stance hip "
            "extension. Use them to benchmark against a healthy reference. Do not "
            "use them to read a patient."
        )
        st.caption(
            "myogait deprecated this family in 0.8.0, removal planned for 1.0: "
            "its own validation campaign found the *uncorrected* pipeline already "
            "at optical-reference level with a modern pose backbone, and that "
            "these corrections degrade rather than improve accuracy there. Each "
            "call now also emits a DeprecationWarning. `run_pipeline()`, "
            "myogait's own recommended entry point, applies no bias correction."
        )

        available = all(
            runtime.has(key) for key in ("ankle_bias", "hip_bias", "knee_bias")
        )
        if not available:
            st.caption(runtime.missing_feature_hint("ankle_bias"))

        # These models were fitted on the sagittal method's residuals (M1-
        # corrected, for hip/knee). ISB reconstruction is a different
        # angle definition entirely (pelvis-referenced 3-D, not trunk-
        # referenced 2-D) -- applying a correction fitted on one to the
        # other has no scientific basis, so all three are blocked outright
        # while it is on, not just hip/knee the way the perspective
        # requirement below is.
        isb_active = angles.isb_reconstruction
        if isb_active:
            st.caption(
                "ISB reconstruction is on: these corrections were fitted on "
                "the sagittal method's residuals, not ISB's pelvis-referenced "
                "angles, so all three are disabled while it is active."
            )

        ankle = st.checkbox(
            "Ankle bias correction",
            value=cfg.ankle and available and not isb_active,
            disabled=not available or isb_active,
            help="Fitted on the raw signal; does not require the perspective step.",
        )

        needs = not angles.perspective
        if needs and not isb_active:
            st.caption(
                "Hip and knee need the M1 perspective correction enabled first - "
                "their coefficients were fitted on M1-corrected residuals, so "
                "applying them to raw angles double-counts the projection."
            )
        hip = st.checkbox(
            "Hip bias correction",
            value=cfg.hip and available and not needs and not isb_active,
            disabled=not available or needs or isb_active,
        )
        knee = st.checkbox(
            "Knee bias correction",
            value=cfg.knee and available and not needs and not isb_active,
            disabled=not available or needs or isb_active,
        )

        if knee:
            st.error(
                "The knee correction acts on the 60-75% swing peak - the phase "
                "where reduced knee flexion is the hallmark sign in DMD and CMT."
            )

    return BiasConfig(ankle=ankle, hip=hip, knee=knee)


def _events_section(cfg: EventsConfig, runtime) -> EventsConfig:
    components.sidebar_section_marker("03", BRANDING.accent_mark)
    with st.expander("3. Gait events", expanded=True):
        methods = list(runtime.event_methods) or ["zeni"]
        use_consensus = st.checkbox(
            "Consensus across methods",
            value=cfg.is_consensus,
            help="Runs several detectors and keeps the events a majority agree on.",
        )

        method = cfg.method
        consensus_methods: tuple[str, ...] = ()
        tolerance = cfg.consensus_tolerance

        if use_consensus:
            default = [m for m in (cfg.consensus_methods or ("zeni", "oconnor", "crossing"))
                       if m in methods]
            selected = st.multiselect(
                "Methods to vote", methods, default=default or methods[:3]
            )
            consensus_methods = tuple(selected)
            tolerance = st.slider(
                "Agreement tolerance (frames)", 1, 15, int(cfg.consensus_tolerance)
            )
            if len(consensus_methods) < 2:
                st.caption("Select at least two methods, or turn consensus off.")
        else:
            method_entry = find_one(cfg.method) or find_one("gk_") or find_one("detect_events")
            method = st.selectbox(
                "Detection method", methods,
                index=methods.index(cfg.method) if cfg.method in methods else 0,
                help=method_entry.summary if method_entry else None,
            )
            if method.startswith("gk_") and not runtime.gaitkit_ok:
                st.caption(
                    "This detector comes from gaitkit, which is older than myogait "
                    "requires here - results may be unreliable."
                )

        adaptive = st.checkbox(
            "Adaptive parameters", value=cfg.adaptive,
            help="Estimates walking speed and overrides the two values below.",
        )
        min_cycle = st.slider(
            "Min cycle duration (s)", 0.2, 2.0, float(cfg.min_cycle_duration), 0.05,
            disabled=adaptive,
        )
        cutoff = st.slider(
            "Event filter cutoff (Hz)", 1.0, 15.0, float(cfg.cutoff_freq), 0.5,
            disabled=adaptive,
        )
        femur = st.slider(
            "Reference femur length (mm)", 150, 600, int(cfg.femur_length_mm), 10,
            help="Used by the gk_* detectors to convert normalised positions to "
                 "real-world units. Auto-filled when the Subject panel's measured "
                 "femur length changes - move this slider to override for this "
                 "run only.",
        )
        trim = st.checkbox(
            "Trim standstill", value=cfg.trim_standstill,
            help="Drops events detected while the subject is not yet walking.",
        )

    return EventsConfig(
        method=method,
        min_cycle_duration=float(min_cycle),
        cutoff_freq=float(cutoff),
        adaptive=adaptive,
        femur_length_mm=float(femur),
        trim_standstill=trim,
        consensus_methods=consensus_methods if len(consensus_methods) > 1 else (),
        consensus_tolerance=int(tolerance),
    )


def _cycles_section(cfg: CyclesConfig, runtime) -> CyclesConfig:
    components.sidebar_section_marker("04", BRANDING.ink_light)
    with st.expander("4. Cycle segmentation", expanded=False):
        n_points = st.select_slider(
            "Points per normalised cycle", [51, 101, 201], value=int(cfg.n_points),
            help=find_one("segment_cycles").summary,
        )
        bounds = st.slider(
            "Accepted cycle duration (s)", 0.2, 4.0,
            (float(cfg.min_duration), float(cfg.max_duration)), 0.05,
            help="Cycles outside this window are discarded as detection errors.",
        )

        st.divider()
        gates_ok = runtime.cycle_quality_gates_supported
        st.caption(
            "Quality gates, applied per cycle before it is kept."
            + ("" if gates_ok else f" Needs myogait 0.8.1+ (installed: "
                                    f"{runtime.myogait_version or 'unknown'}).")
        )
        columns = st.columns(2)
        use_confidence = columns[0].checkbox(
            "Reject low-confidence cycles", value=cfg.min_confidence is not None,
            disabled=not gates_ok,
        )
        min_confidence = (
            st.slider("Min mean confidence", 0.0, 1.0, float(cfg.min_confidence or 0.3), 0.05)
            if use_confidence and gates_ok else None
        )
        use_coherence = columns[1].checkbox(
            "Reject low-coherence cycles", value=cfg.min_coherence is not None,
            disabled=not gates_ok,
            help="Needs 'Score frame coherence' enabled in Signal conditioning "
                 "above, or every cycle's mean coherence is undefined and none "
                 "are rejected.",
        )
        min_coherence = (
            st.slider("Min mean coherence", 0.0, 1.0, float(cfg.min_coherence or 0.3), 0.05)
            if use_coherence and gates_ok else None
        )

    return CyclesConfig(
        n_points=int(n_points),
        min_duration=float(bounds[0]),
        max_duration=float(bounds[1]),
        min_confidence=min_confidence,
        min_coherence=min_coherence,
    )
