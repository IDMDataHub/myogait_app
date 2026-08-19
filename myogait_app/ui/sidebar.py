"""The control panel.

Every lever myogait exposes downstream of extraction lives here, grouped
in pipeline order so the sidebar reads top-to-bottom the way the data
flows. Controls whose backing function is missing from the installed
myogait are disabled rather than hidden, with the reason attached -- a
greyed-out control that explains itself teaches the version boundary;
a hidden one just looks like the feature does not exist.
"""

from __future__ import annotations

import streamlit as st

from ..pipeline import (
    AnglesConfig,
    BiasConfig,
    CyclesConfig,
    EventsConfig,
    NormalizeConfig,
    PipelineConfig,
    SubjectConfig,
)
from ..runtime import get_runtime

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


def render(config: PipelineConfig) -> PipelineConfig:
    """Draw the controls and return the configuration they describe."""
    runtime = get_runtime()

    subject = _subject_section(config.subject)
    normalize = _normalize_section(config.normalize)
    angles = _angles_section(config.angles, runtime)
    bias = _bias_section(config.bias, angles, runtime)
    events = _events_section(config.events, runtime)
    cycles = _cycles_section(config.cycles)

    return PipelineConfig(
        normalize=normalize,
        angles=angles,
        events=events,
        cycles=cycles,
        bias=bias,
        subject=subject,
    )


def _subject_section(cfg: SubjectConfig) -> SubjectConfig:
    with st.expander("Subject", expanded=False):
        st.caption(
            "Height is the one that changes results: without it, step length and "
            "walking speed stay in normalised units instead of metres."
        )
        height = st.number_input(
            "Height (m)",
            min_value=0.0,
            max_value=2.5,
            value=float(cfg.height_m or 0.0),
            step=0.01,
            format="%.2f",
            help="0 leaves it unset.",
        )
        columns = st.columns(2)
        age = columns[0].number_input(
            "Age", min_value=0, max_value=120, value=int(cfg.age or 0), step=1
        )
        weight = columns[1].number_input(
            "Weight (kg)", min_value=0.0, max_value=250.0,
            value=float(cfg.weight_kg or 0.0), step=0.5,
        )
        sex = st.selectbox(
            "Sex", ["", "M", "F", "X"],
            index=["", "M", "F", "X"].index(cfg.sex or ""),
        )
        pathology = st.text_input("Pathology", value=cfg.pathology or "")

    return SubjectConfig(
        age=int(age) or None,
        sex=sex or None,
        height_m=float(height) or None,
        weight_kg=float(weight) or None,
        pathology=pathology or None,
    )


def _normalize_section(cfg: NormalizeConfig) -> NormalizeConfig:
    with st.expander("1. Signal conditioning", expanded=True):
        options = _available_filters()
        filters = st.multiselect(
            "Filters (applied in order)",
            options=options,
            default=[f for f in cfg.filters if f in options],
            help="Leave empty to work on the raw landmarks.",
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
            "Drop low-confidence landmarks", value=cfg.confidence_threshold is not None
        )
        confidence = (
            st.slider("Confidence threshold", 0.0, 1.0,
                      float(cfg.confidence_threshold or 0.3), 0.05)
            if use_confidence else None
        )
        use_outliers = st.checkbox(
            "Interpolate outliers", value=cfg.outlier_z is not None
        )
        outlier_z = (
            st.slider("Outlier threshold (SD)", 1.0, 6.0, float(cfg.outlier_z or 3.0), 0.5)
            if use_outliers else None
        )
        gap = st.slider("Max interpolated gap (frames)", 0, 60, int(cfg.gap_max_frames))

        st.divider()
        columns = st.columns(2)
        center = columns[0].checkbox("Center on torso", value=cfg.center)
        align = columns[1].checkbox("Align skeleton", value=cfg.align, disabled=center)
        correct_limbs = st.checkbox("Correct bilateral swaps", value=cfg.correct_limbs)
        coherence = st.checkbox("Score frame coherence", value=cfg.coherence)

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


def _angles_section(cfg: AnglesConfig, runtime) -> AnglesConfig:
    with st.expander("2. Joint kinematics", expanded=True):
        methods = list(runtime.angle_methods)
        method = st.selectbox(
            "Angle method", methods,
            index=methods.index(cfg.method) if cfg.method in methods else 0,
        )
        correction = st.slider(
            "2D ROM correction factor", 0.5, 1.2, float(cfg.correction_factor), 0.05,
            help="myogait suggests 0.8 for MediaPipe and 1.0 for 3D-capable models.",
        )
        calibrate = st.checkbox("Neutral calibration", value=cfg.calibrate)
        calibration_frames = (
            st.slider("Calibration frames", 5, 120, int(cfg.calibration_frames))
            if calibrate else cfg.calibration_frames
        )

        columns = st.columns(2)
        ankle_sliding = columns[0].checkbox(
            "Ankle sliding fix", value=cfg.correct_ankle_sliding
        )
        aspect = columns[1].checkbox("Aspect ratio", value=cfg.apply_aspect_ratio)

        frontal_ok = runtime.has("frontal_angles")
        frontal = st.checkbox(
            "Frontal-plane angles",
            value=cfg.frontal and frontal_ok,
            disabled=not frontal_ok,
            help="Needs depth data to be meaningful."
            if frontal_ok else runtime.missing_feature_hint("frontal_angles"),
        )

        st.divider()
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

        available = all(
            runtime.has(key) for key in ("ankle_bias", "hip_bias", "knee_bias")
        )
        if not available:
            st.caption(runtime.missing_feature_hint("ankle_bias"))

        ankle = st.checkbox(
            "Ankle bias correction",
            value=cfg.ankle and available,
            disabled=not available,
            help="Fitted on the raw signal; does not require the perspective step.",
        )

        needs = not angles.perspective
        if needs:
            st.caption(
                "Hip and knee need the M1 perspective correction enabled first - "
                "their coefficients were fitted on M1-corrected residuals, so "
                "applying them to raw angles double-counts the projection."
            )
        hip = st.checkbox(
            "Hip bias correction",
            value=cfg.hip and available and not needs,
            disabled=not available or needs,
        )
        knee = st.checkbox(
            "Knee bias correction",
            value=cfg.knee and available and not needs,
            disabled=not available or needs,
        )

        if knee:
            st.error(
                "The knee correction acts on the 60-75% swing peak - the phase "
                "where reduced knee flexion is the hallmark sign in DMD and CMT."
            )

    return BiasConfig(ankle=ankle, hip=hip, knee=knee)


def _events_section(cfg: EventsConfig, runtime) -> EventsConfig:
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
            method = st.selectbox(
                "Detection method", methods,
                index=methods.index(cfg.method) if cfg.method in methods else 0,
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
            "Reference femur length (mm)", 250, 550, int(cfg.femur_length_mm), 10,
            help="Used by the gk_* detectors to convert normalised positions to "
                 "real-world units.",
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


def _cycles_section(cfg: CyclesConfig) -> CyclesConfig:
    with st.expander("4. Cycle segmentation", expanded=False):
        n_points = st.select_slider(
            "Points per normalised cycle", [51, 101, 201], value=int(cfg.n_points)
        )
        bounds = st.slider(
            "Accepted cycle duration (s)", 0.2, 4.0,
            (float(cfg.min_duration), float(cfg.max_duration)), 0.05,
            help="Cycles outside this window are discarded as detection errors.",
        )

    return CyclesConfig(
        n_points=int(n_points),
        min_duration=float(bounds[0]),
        max_duration=float(bounds[1]),
    )
