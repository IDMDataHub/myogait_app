"""A grounded, plain-language index of myogait's processing functions.

Every entry is written from the package's own docstrings (module version
0.6.1, mirroring the ``master`` branch this app tracks), so the Reference
page and the sidebar tooltips describe what myogait actually documents
itself as doing, not what this app assumes it does. Citations are kept
only where myogait's own docstring cites one.

Entries cover both what is reachable from this app's UI today and a
handful of functions that were considered but are not currently planned,
so this file does not need rewriting each time a new tab lands -- only
the ``status`` on the affected entries changes. Statuses: ``"wired"``
(usable in the app today), ``"phase4"`` / ``"phase5"`` (were planned,
never left unresolved past their own phase), and ``"backlog"`` (a real
myogait function, deliberately not wired -- see its summary for why).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    name: str  # myogait symbol, or a method key inside a dispatcher
    module: str  # myogait.<module> it lives in
    summary: str  # what it does, in the package's own terms
    status: str = "wired"  # "wired" | "backlog" | "phase4" | "phase5"
    citation: str = ""


STATUS_LABELS = {
    "wired": "In the app today",
    "backlog": "Backlog - not currently planned",
    "phase4": "Planned - Phase 4",
    "phase5": "Planned - Phase 5",
}

#: (group title, entries) in pipeline order, then the surrounding
#: analysis / scoring / export / figures groups.
GROUPS: list[tuple[str, list[Entry]]] = [
    (
        "1. Signal conditioning - myogait.normalize",
        [
            Entry("normalize", "normalize", "Dispatches to the chosen filter(s) in order, then optionally centers/aligns the skeleton and corrects bilateral segment-length asymmetry. The one function every stage after extraction runs through first."),
            Entry("filter_butterworth", "normalize", "Zero-phase low-pass filter (via filtfilt) - the default. Lower cutoff smooths more but can remove real gait content; myogait suggests checking against auto_cutoff_frequency()."),
            Entry("filter_savgol", "normalize", "Savitzky-Golay polynomial smoothing - preserves peak shape better than a moving average at the cost of more parameters to tune."),
            Entry("filter_moving_mean", "normalize", "Simple centered moving average over a window of frames. The bluntest of the filters, mainly useful as a baseline."),
            Entry("filter_median", "normalize", "1-D median filter applied independently per coordinate - the standard first pass recommended by DeepLabCut for spike/outlier removal before smoothing."),
            Entry("filter_spline", "normalize", "Smoothing spline fit to each coordinate trajectory."),
            Entry("filter_kalman", "normalize", "Kalman filter for trajectory smoothing; falls back to a moving mean if pykalman is not installed."),
            Entry("filter_loess", "normalize", "LOESS/LOWESS locally weighted scatterplot smoothing. Needs statsmodels."),
            Entry("filter_wavelet", "normalize", "Wavelet denoising of the kinematic signals. Needs PyWavelets."),
            Entry("confidence_filter", "normalize", "Sets landmark coordinates to NaN wherever the backend's own visibility/confidence score falls below a threshold, before any smoothing runs - a quality gate, not a smoother."),
            Entry("detect_outliers", "normalize", "Z-score spike detection per coordinate column; values beyond the threshold are replaced by linear interpolation."),
            Entry("fill_gaps", "normalize", "Interpolates short runs of missing landmark data (up to a max gap length) so a brief occlusion does not break downstream stages."),
            Entry("frame_coherence_score", "normalize", "Per-frame biomechanical plausibility score in [0, 1], combining segment-length stability, landmark velocity, and angular continuity - flags frames a filter alone would not catch."),
            Entry("data_quality_score", "normalize", "One composite 0-100 score for the whole recording: detection rate, mean confidence, coherence, and gap frequency."),
            Entry("center_on_torso / align_skeleton", "normalize", "The Center / Align toggles: recenters coordinates on the shoulder-hip centroid and normalizes scale, removing camera framing as a confound."),
            Entry("correct_bilateral", "normalize", "The Correct bilateral swaps toggle: rescales the right-side segments to match the left-side reference length, for when a backend occasionally swaps a left/right label."),
            Entry("residual_analysis / auto_cutoff_frequency", "normalize", "Suggests a Butterworth cutoff automatically from the signal's own residual-vs-cutoff curve, rather than guessing one."),
            Entry("cross_correlation_lag / align_signals", "normalize", "Finds and applies the time shift that best aligns two signals - used internally for bilateral and multi-source synchronisation."),
        ],
    ),
    (
        "2. Joint kinematics - myogait.angles",
        [
            Entry("compute_angles", "angles", "Computes hip/knee/ankle sagittal angles per frame from the normalized landmarks, with optional neutral-pose calibration and a 2D projection ROM correction factor (myogait suggests 0.8 for MediaPipe, 1.0 for 3D-capable backends). Ankle is the default calibrated joint. When the calibration window itself shows no meaningful motion (a patient standing still, possibly in a pathological or asymmetric pose), calibration_dynamic_fallback replaces it with the median of all valid frames instead of silently shifting the whole cycle by that static-pose offset - worth ruling out before reading a persistent ankle error as a hardware or measurement ceiling rather than a calibration artefact."),
            Entry("apply_aspect_ratio (compute_angles option)", "angles", "Rescales normalized [0,1] coordinates into pixel space using meta.width/height before computing angles - required whenever the image/canvas is not square, otherwise X and Y carry different metric units and angles are biased."),
            Entry("detect_ankle_swap / correct_ankle_swaps", "angles", "Cross-checks the ankle angle two ways (using the ANKLE landmark vs. using HEEL as a pivot); when they disagree beyond a threshold, the ANKLE label is treated as swapped and patched - the Ankle sliding fix toggle."),
            Entry("compute_frontal_angles", "angles", "Hip abduction and knee valgus/varus in the frontal plane, from depth-enhanced landmarks (Sapiens depth backends only)."),
            Entry("compute_extended_angles", "angles", "Adds head posture, shoulder/elbow flexion and sagittal pelvis angles beyond the core hip/knee/ankle set. Not part of any planned phase - would fit alongside compute_frontal_angles in Joint kinematics if prioritised.", status="backlog"),
            Entry("foot_progression_angle", "angles", "Angle between the heel-to-toe vector and the horizontal axis per foot - positive is out-toeing, negative is in-toeing. Not part of any planned phase.", status="backlog"),
        ],
    ),
    (
        "2b. Perspective & bias corrections - myogait.corrections",
        [
            Entry("apply_perspective_correction", "corrections", "Zero-parameter M1 projection correction for hip and knee: estimates cos(camera angle) per frame from how the observed segment length compares to its own session 95th percentile. Pure geometry from this recording, no population assumption."),
            Entry("apply_linear_detrend", "corrections", "Removes the slow angular drift a fixed camera introduces over a long walk, applied after the perspective correction, preserving the anatomical mean and per-cycle ROM."),
            Entry("apply_ankle_bias_correction", "corrections", "Frozen Fourier/LASSO correction fitted on healthy young adults vs. Vicon. Do not use for clinical reading of pathological gait - it re-injects a healthy push-off dip exactly where drop foot shows itself."),
            Entry("apply_hip_bias_correction / apply_knee_bias_correction", "corrections", "Same LASSO-model family as the ankle correction, but must run after apply_perspective_correction since their coefficients were fitted on M1-corrected residuals."),
        ],
    ),
    (
        "3. Gait events - myogait.events",
        [
            Entry("detect_events", "events", "Dispatches to the chosen heel-strike/toe-off detector. All built-in methods are registered in EVENT_METHODS and extensible via register_event_method()."),
            Entry("zeni", "events", "Default method: ankle antero-posterior position relative to the pelvis.", citation="Zeni, Richards & Higginson, Gait Posture 2008"),
            Entry("oconnor", "events", "Heel antero-posterior velocity zero-crossings.", citation="O'Connor et al., Gait Posture 2007"),
            Entry("crossing", "events", "Detects events from where the left and right knee X-coordinates cross, based on contralateral limb progression.", citation="Desailly et al., Gait Posture 2009"),
            Entry("velocity", "events", "Foot vertical-velocity zero-crossings: downward-to-upward is a heel strike, upward-to-downward is a toe off.", citation="Hreljac & Marshall, J Biomech 2000"),
            Entry("gk_* methods", "events (gaitkit)", "Ten individual detectors plus gk_ensemble (multi-method voting) from the optional gaitkit package - what the Comparator puts in competition with the built-in methods."),
            Entry("event_consensus", "events", "Runs several detectors and keeps only the events a majority agree on within a frame tolerance - trades detector-specific noise for a stricter agreement requirement."),
            Entry("femur_length_mm (detect_events option)", "events", "Reference length used to convert normalized positions to real-world millimetres before handing frames to the gk_* detectors, which expect metric input."),
        ],
    ),
    (
        "4. Cycle segmentation - myogait.cycles",
        [
            Entry("segment_cycles", "cycles", "Splits the walk into one cycle per heel-strike-to-next-same-side-heel-strike, time-normalizes each to 0-100%, and computes per-side mean +/- SD curves."),
            Entry("ensemble_average", "cycles", "Aggregates the per-trial mean curves from several segment_cycles() runs into a grand mean plus inter-trial and intra-trial variability. The Longitudinal page compares sessions via plot_longitudinal/plot_session_comparison instead; this stays unused.", status="backlog"),
        ],
    ),
    (
        "5. Spatio-temporal metrics & pathology screens - myogait.analysis",
        [
            Entry("regularity_index", "analysis", "Stride/step regularity via unbiased autocorrelation of the vertical ankle signal.", citation="Moe-Nilssen & Helbostad, J Biomech 2004"),
            Entry("harmonic_ratio", "analysis", "Gait smoothness as the ratio of even to odd FFT harmonics of the antero-posterior signal - higher is smoother and more symmetric.", citation="Smidt et al. 1971; Bellanca et al., J Biomech 2013"),
            Entry("step_length / walking_speed", "analysis", "Ankle-displacement-based step/stride length and speed. Calibrated to metres only when height_m is given, via a fixed 24.5% femur-to-height ratio. When a femur was actually measured, the app passes height_m = femur_mm / 1000 / 0.245 instead of the stated height, so this formula reproduces the real femur rather than the population ratio - the femur measurement takes priority whenever it is set.", citation="Drillis, Contini & Bluestein, Artif Limbs 1964"),
            Entry("segment_lengths", "analysis", "Per-frame Euclidean length of ten body segments (femur, tibia, upper arm, forearm, trunk, each side), with mean/SD/CV and a quality flag above 15% CV. Feeds the app's own segment-based calibration panel."),
            Entry("detect_pathologies", "analysis", "Screens for four patterns from the normalized cycles: Trendelenburg (excess pelvis drop), spastic gait (reduced swing knee flexion), steppage (excess hip flexion compensating foot drop), crouch gait (persistent knee flexion). What analyze_gait runs automatically."),
            Entry("detect_equinus", "analysis", "Flags equinus when peak stance-phase ankle dorsiflexion never reaches neutral (<=0 deg) - typical of spastic diplegic CP or post-stroke gait. Not part of detect_pathologies."),
            Entry("detect_antalgic", "analysis", "Flags antalgic (pain-avoidance) gait from asymmetric stance duration (<55% on one side vs. >65% on the other). Not part of detect_pathologies."),
            Entry("detect_parkinsonian", "analysis", "Flags a parkinsonian pattern when at least two of short stride length, reduced arm swing, and elevated cadence (festination) co-occur. Not part of detect_pathologies."),
            Entry("single_support_time", "analysis", "Duration of single-limb stance per side, normally ≈40% of the cycle - reduced single support on one side can indicate pain avoidance or instability."),
            Entry("toe_clearance", "analysis", "Minimum foot-to-ground distance during mid-swing (normally ≈1-2 cm); low clearance is a trip/fall risk factor."),
            Entry("stride_variability", "analysis", "Coefficient of variation across multiple gait parameters at once - elevated variability tracks with fall risk and some neurodegenerative conditions."),
            Entry("arm_swing_analysis", "analysis", "Shoulder flexion amplitude, left/right asymmetry, and arm-leg coordination - reduced arm swing is an early Parkinson's indicator."),
            Entry("speed_normalized_params", "analysis", "Dimensionless gait parameters via Froude-number normalization, so subjects of different heights become comparable. Needs the Subject height.", citation="Hof, Gait Posture 1996"),
            Entry("instantaneous_cadence", "analysis", "Cadence computed per consecutive heel-strike pair (60 / step time) rather than one averaged number - shows cadence drift within a single trial."),
            Entry("compute_rom_summary", "analysis", "Per-cycle range of motion (max - min) for each joint and side, with mean/SD/CV across cycles - the numeric counterpart to the ROM bar chart already shown."),
            Entry("estimate_center_of_mass", "analysis", "Whole-body centre of mass per frame from segmental analysis using Winter's body-segment-parameter tables.", citation="Winter, Biomechanics and Motor Control of Human Movement, 2009"),
            Entry("postural_sway", "analysis", "Sway metrics (95% confidence ellipse area, mean velocity, ML/AP range) from the ankle-midpoint as a centre-of-pressure proxy."),
            Entry("pca_waveform_analysis", "analysis", "PCA on time-normalized joint-angle waveforms across cycles - the dominant patterns of cycle-to-cycle variation. Its own docstring says it reads cycle['angles'][joint_side], but segment_cycles() only ever produces cycle['angles_normalized'][joint] (unsuffixed); called as documented it always finds zero waveforms. The app rebuilds the side-suffixed view on a copy before calling it."),
            Entry("compute_derivatives", "analysis", "Angular velocity and acceleration of the joint-angle curves via central differences. Mutates its data argument in place, so the app always passes it a copy."),
            Entry("time_frequency_analysis", "analysis", "Time-frequency decomposition (continuous wavelet transform, or short-time Fourier) of an angle signal - where in the cycle a given frequency content concentrates."),
        ],
    ),
    (
        "6. Clinical profile scores - myogait.scores",
        [
            Entry("gait_variable_scores (GVS)", "scores", "Per-joint, per-side RMS difference between the patient's mean cycle curve and a normative curve."),
            Entry("gait_profile_score_2d (GPS-2D)", "scores", "RMS of every GVS value across the sagittal joints - a single overall deviation-from-normal number."),
            Entry("sagittal_deviation_index (SDI)", "scores", "A simplified z-score-based deviation index from sagittal-plane data only. Not the Schwartz & Rozumalski Gait Deviation Index (GDI) - that is a full 3D PCA/SVD index myogait does not attempt to reproduce. gait_deviation_index_2d is a deprecated alias for this same function; the name change exists precisely to stop it being mistaken for GDI. Its return dict still uses gdi_2d_* keys internally - the app relabels them SDI everywhere in the UI."),
            Entry("movement_analysis_profile (MAP)", "scores", "GVS values organized per joint for a bar-chart profile view."),
        ],
    ),
    (
        "7. Normative reference data - myogait.normative",
        [
            Entry("get_normative_curve / get_normative_band", "normative", "Reference mean curve and +/- N-SD band for a joint and demographic stratum - what the Cycles tab's reference-band overlay already draws."),
            Entry("select_stratum", "normative", "Maps a subject's age to a normative stratum (pediatric / adult / elderly)."),
        ],
    ),
    (
        "8. C3D & data sources",
        [
            Entry("load_c3d", "experimental_vicon", "Reads 3-D marker trajectories from a .c3d motion-capture file with ezc3d, projects them into the same 2-D sagittal pivot format a video extraction produces. Normalizes the antero-posterior and vertical axes independently - the app corrects the resulting aspect-ratio distortion by default."),
            Entry("load_json / save_json", "schema", "Reads/writes the pivot JSON that carries a recording through every stage - the format a CLI extraction hands to this app, and vice versa."),
            Entry("extract", "extract", "Runs a pose-estimation backend over a video and builds the initial pivot dict - the expensive stage every other one downstream is cheap by comparison to."),
        ],
    ),
    (
        "9. Export & interchange",
        [
            Entry("export_csv / export_excel / export_json", "export", "Bundled data exports: per-stage CSVs, a single Excel workbook, or a plain JSON dump of angles/cycles/stats."),
            Entry("export_mot / export_trc", "export", "OpenSim-format kinematics (.mot) and marker trajectories (.trc, optionally remapped to a named OpenSim model's marker set)."),
            Entry("export_c3d", "export", "Writes the pivot data back out as a .c3d file, using the c3d package (the export counterpart to load_c3d's ezc3d-based import)."),
            Entry("export_landmarks_excel", "export", "Raw per-frame landmark coordinates to Excel, distinct from export_excel's angle/cycle/stats summary."),
            Entry("export_opensim_scale_setup", "opensim", "XML Scale Tool setup for OpenSim: measurement definitions (femur_length, tibia_length, trunk_height) built from marker pairs, ready to scale a generic model to this subject."),
            Entry("export_ik_setup", "opensim", "XML InverseKinematicsTool setup pointing at a .trc file and a scaled model. The app exports the .trc first and bundles both."),
            Entry("export_moco_setup", "opensim", "MocoTrack XML template for OpenSim Moco, from a .mot kinematics file. The app exports the .mot first and bundles both."),
        ],
    ),
    (
        "10. Figures, video & reports",
        [
            Entry("plot_summary / plot_angles / plot_cycles / plot_events", "plotting", "Core matplotlib figures - the same ones the CLI produces, so an exported figure and a reviewer's own reproduction are pixel-identical in intent."),
            Entry("plot_normative_comparison / plot_quality_dashboard / plot_rom_summary / plot_butterfly / plot_phase_plane / plot_cadence_profile / plot_arm_swing / plot_gvs_profile", "plotting", "Publication figures for, respectively: patient-vs-normative overlay, extraction quality, ROM per joint, mirrored left/right cycles, angle-vs-angular-velocity phase portrait, cadence over time, arm-swing kinematics, and the GVS/MAP profile."),
            Entry("plot_frontal_comparison", "plotting", "Frontal-plane normative comparison (hip adduction, knee valgus) - convenience wrapper over plot_normative_comparison. Missing from myogait's own top-level lazy-export map, unlike every other plot_* function; the app imports it from myogait.plotting directly."),
            Entry("plot_session_comparison", "plotting", "Two walking sessions plotted side by side, joint by joint. On the Longitudinal page, pick any two loaded sessions to compare."),
            Entry("plot_longitudinal", "plotting", "One chosen metric (cadence, symmetry, or GPS-2D once scores are available) plotted across multiple sessions over time - the trend view a progression check needs."),
            Entry("animate_normative_comparison", "plotting", "Animated GIF of the patient curve tracing out against the normative band, frame by frame."),
            Entry("render_skeleton_frame", "video", "Draws the skeleton, and optionally angles/events, on a single video frame - the building block for a quick in-app QC preview instead of a full rendered clip. Not part of any planned phase.", status="backlog"),
            Entry("render_skeleton_video", "video", "Skeleton overlay on the original video, optionally with angle/event/confidence annotations - identifiable, kept inside the lab."),
            Entry("render_stickfigure_animation", "video", "Anonymised stick-figure GIF/MP4 from the landmarks alone, with optional angle labels and a motion trail - the form to prefer once a figure leaves the lab."),
            Entry("generate_report", "report", "Multi-page bilingual (en/fr) PDF: kinematic plots, spatio-temporal tables, normative comparison."),
            Entry("generate_longitudinal_report", "report", "Multi-session PDF comparison across several loaded recordings of the same subject - needs data, cycles and stats per session, a different shape than plot_longitudinal's date+stats."),
        ],
    ),
]


def all_entries() -> list[tuple[str, Entry]]:
    """(group title, entry) for every entry, in GROUPS order."""
    return [(group, entry) for group, entries in GROUPS for entry in entries]


def find(name_fragment: str) -> list[tuple[str, Entry]]:
    """(group title, entry) pairs whose name or summary match *name_fragment*."""
    needle = name_fragment.strip().lower()
    if not needle:
        return all_entries()
    return [
        (group, entry) for group, entry in all_entries()
        if needle in entry.name.lower() or needle in entry.summary.lower()
    ]


def find_one(exact_name_fragment: str) -> Entry | None:
    """First entry whose name contains *exact_name_fragment* -- for a sidebar
    tooltip that wants one specific function's summary, not a search list."""
    needle = exact_name_fragment.strip().lower()
    for _, entry in all_entries():
        if needle in entry.name.lower():
            return entry
    return None
