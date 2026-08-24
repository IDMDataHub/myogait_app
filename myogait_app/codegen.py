"""Turning the current UI state back into code.

A workbench that cannot tell you what it just did is a dead end: the
result is not reproducible, and it cannot be written up. So every screen
can show the exact equivalent of its current state in two forms.

* **Python** -- the authoritative reproduction. It covers everything the
  app can do, including the opt-in corrections that have no CLI flag.
* **YAML** -- the subset ``myogait.load_config()`` understands, for batch
  runs. Where a setting has no config-file equivalent, it is emitted as a
  comment rather than silently dropped, so the file never claims to
  reproduce something it does not.

Both are generated from the same :class:`~myogait_app.pipeline.PipelineConfig`,
so they cannot drift from what the interface actually ran.
"""

from __future__ import annotations

from .pipeline import PipelineConfig

_INDENT = "    "


def _py_repr(value) -> str:
    if isinstance(value, tuple):
        return repr(list(value))
    return repr(value)


def _kwargs_block(pairs: list[tuple[str, object]], indent: str = _INDENT) -> str:
    return "".join(f"{indent}{name}={_py_repr(value)},\n" for name, value in pairs)


def python_snippet(
    config: PipelineConfig,
    source: str = "video.mp4",
    model: str = "mediapipe",
    from_json: bool = False,
    with_depth: bool = False,
    with_seg: bool = False,
    c3d_options: dict | None = None,
) -> str:
    """Return a runnable script reproducing the current state.

    Parameters
    ----------
    source
        Video path, JSON path, or C3D path, depending on *from_json* and
        *c3d_options*.
    from_json
        Start from already-extracted landmarks rather than re-extracting.
        Extraction is the expensive half, so a researcher reproducing a
        parameter study almost always wants this form. Also set when
        *c3d_options* is given, since a C3D file is likewise not
        re-extracted.
    c3d_options
        When given (with *from_json* also set), *source* is loaded with
        ``load_c3d`` instead of ``load_json``, using the marker mapping,
        axes and aspect-ratio fix recorded at load time. Keys:
        ``marker_mapping``, ``ap_axis``, ``vertical_axis``,
        ``fix_aspect_ratio``, and ``ranges`` (the ``(ap_range,
        vertical_range)`` pair used for the fix, when applied).
    """
    norm = config.normalize
    ang = config.angles
    ev = config.events
    cyc = config.cycles
    bias = config.bias
    subj = config.subject

    lines: list[str] = ['"""Reproduces the current workbench state."""', ""]

    imports = ["normalize", "compute_angles", "segment_cycles", "analyze_gait"]
    imports.append("event_consensus" if ev.is_consensus else "detect_events")
    if not from_json:
        imports.insert(0, "extract")
    if not subj.is_empty:
        imports.append("set_subject")
    if norm.confidence_threshold is not None:
        imports.append("confidence_filter")
    if norm.outlier_z is not None:
        imports.append("detect_outliers")
    if norm.coherence:
        imports.append("frame_coherence_score")
    if ang.frontal:
        imports.append("compute_frontal_angles")

    # Corrections are imported from myogait.corrections, not the package
    # root: they were promoted to the top level at different versions, and
    # the module path is what the myogait documentation uses.
    correction_imports = [
        name
        for flag, name in (
            (ang.perspective, "apply_perspective_correction"),
            (ang.detrend, "apply_linear_detrend"),
            (bias.ankle, "apply_ankle_bias_correction"),
            (bias.hip, "apply_hip_bias_correction"),
            (bias.knee, "apply_knee_bias_correction"),
        )
        if flag
    ]

    if from_json and c3d_options:
        lines.append("from myogait import load_c3d, " + ", ".join(imports))
    elif from_json:
        lines.append("from myogait import load_json, " + ", ".join(imports))
    else:
        lines.append("from myogait import " + ", ".join(imports))
    if correction_imports:
        lines.append(
            "from myogait.corrections import " + ", ".join(correction_imports)
        )
    lines.append("")
    if from_json and c3d_options:
        lines.append(f"data = load_c3d({source!r},")
        lines.append(
            _kwargs_block(
                [
                    ("marker_mapping", c3d_options.get("marker_mapping")),
                    ("ap_axis", c3d_options.get("ap_axis", 1)),
                    ("vertical_axis", c3d_options.get("vertical_axis", 2)),
                ]
            ).rstrip("\n")
        )
        lines.append(")")
        ranges = c3d_options.get("ranges")
        if c3d_options.get("fix_aspect_ratio") and ranges:
            lines += [
                "",
                "# load_c3d normalises the AP and vertical axes independently",
                "# but reports a square virtual canvas, so compute_angles'",
                "# aspect-ratio fix never triggers for a C3D source. Restore",
                "# the true range ratio, recovered from the file itself.",
                f"data['meta']['width'] = {ranges[0]!r}",
                f"data['meta']['height'] = {ranges[1]!r}",
            ]
    elif from_json:
        lines.append(f"data = load_json({source!r})")
    else:
        lines.append("# 1. Pose extraction")
        extract_args = [("model", model)]
        if with_depth:
            extract_args.append(("with_depth", True))
        if with_seg:
            extract_args.append(("with_seg", True))
        lines.append(f"data = extract({source!r},")
        lines.append(_kwargs_block(extract_args).rstrip("\n"))
        lines.append(")")

    if not subj.is_empty:
        lines += ["", "# Subject metadata (height unlocks step length and speed in m/s)"]
        subject_args = [
            (name, getattr(subj, name))
            for name in ("age", "sex", "height_m", "weight_kg", "pathology")
            if getattr(subj, name) not in (None, "")
        ]
        lines.append("data = set_subject(data,")
        lines.append(_kwargs_block(subject_args).rstrip("\n"))
        lines.append(")")

    lines += ["", "# 2. Signal conditioning"]
    if norm.confidence_threshold is not None:
        lines.append(
            f"data = confidence_filter(data, threshold={norm.confidence_threshold})"
        )
    if norm.outlier_z is not None:
        lines.append(f"data = detect_outliers(data, z_thresh={norm.outlier_z})")
    lines.append("data = normalize(data,")
    lines.append(
        _kwargs_block(
            [
                ("filters", norm.filters),
                ("butterworth_cutoff", norm.butterworth_cutoff),
                ("butterworth_order", norm.butterworth_order),
                ("center", norm.center),
                ("align", norm.align),
                ("correct_limbs", norm.correct_limbs),
                ("gap_max_frames", norm.gap_max_frames),
            ]
        ).rstrip("\n")
    )
    lines.append(")")
    if norm.coherence:
        lines.append("data = frame_coherence_score(data)")

    lines += ["", "# 3. Joint kinematics"]
    lines.append("data = compute_angles(data,")
    lines.append(
        _kwargs_block(
            [
                ("method", ang.method),
                ("correction_factor", ang.correction_factor),
                ("calibrate", ang.calibrate),
                ("calibration_frames", ang.calibration_frames),
                ("calibration_dynamic_fallback", ang.calibration_dynamic_fallback),
                ("calibration_min_std_deg", ang.calibration_min_std_deg),
                ("correct_ankle_sliding", ang.correct_ankle_sliding),
                ("apply_aspect_ratio", ang.apply_aspect_ratio),
            ]
        ).rstrip("\n")
    )
    lines.append(")")
    if ang.frontal:
        lines.append("data = compute_frontal_angles(data)")

    if ang.perspective:
        lines.append("")
        lines.append("# M1 projection correction: pure geometry, session-local,")
        lines.append("# no population prior. Safe on any gait.")
        lines.append("data = apply_perspective_correction(data)")
    if ang.detrend:
        lines.append("data = apply_linear_detrend(data)")

    lines += ["", "# 4. Gait events"]
    if ev.is_consensus:
        lines.append("data = event_consensus(data,")
        lines.append(
            _kwargs_block(
                [
                    ("methods", ev.consensus_methods),
                    ("tolerance", ev.consensus_tolerance),
                    ("min_cycle_duration", ev.min_cycle_duration),
                    ("cutoff_freq", ev.cutoff_freq),
                    ("femur_length_mm", ev.femur_length_mm),
                ]
            ).rstrip("\n")
        )
        lines.append(")")
    else:
        lines.append("data = detect_events(data,")
        lines.append(
            _kwargs_block(
                [
                    ("method", ev.method),
                    ("min_cycle_duration", ev.min_cycle_duration),
                    ("cutoff_freq", ev.cutoff_freq),
                    ("adaptive", ev.adaptive),
                    ("femur_length_mm", ev.femur_length_mm),
                    ("trim_standstill", ev.trim_standstill),
                ]
            ).rstrip("\n")
        )
        lines.append(")")

    lines += ["", "# 5. Cycles and analysis"]
    segment_call = [
        "segment_cycles(data,",
        _kwargs_block(
            [
                ("n_points", cyc.n_points),
                ("min_duration", cyc.min_duration),
                ("max_duration", cyc.max_duration),
            ]
        ).rstrip("\n"),
        ")",
    ]
    lines.append("cycles = " + segment_call[0])
    lines += segment_call[1:]

    if bias.any_enabled:
        enabled = [
            name
            for flag, name in (
                (bias.ankle, "apply_ankle_bias_correction"),
                (bias.hip, "apply_hip_bias_correction"),
                (bias.knee, "apply_knee_bias_correction"),
            )
            if flag
        ]
        lines += [
            "",
            "# Bias corrections. These are LASSO models fitted on healthy",
            "# young adults against Vicon. myogait's own documentation warns",
            "# that they re-inject a healthy curve at the phases where",
            "# neuromuscular disease shows: swing knee flexion (DMD, CMT),",
            "# ankle push-off (drop foot), end-stance hip extension.",
            "# Use for benchmarking against a healthy reference, not for",
            "# clinical reading of a patient.",
            "# They are indexed by cycle phase, hence the cycles argument.",
        ]
        for name in enabled:
            model_arg = f", model={bias.model!r}" if bias.model != "v1" else ""
            lines.append(f"data = {name}(data, cycles{model_arg})")
        lines += [
            "",
            "# The corrections rewrote the angle frames, so the segmentation",
            "# above now describes the previous curves. Recompute it.",
            "cycles = " + segment_call[0],
        ]
        lines += segment_call[1:]

    calibration_height = subj.calibration_height_m
    if subj.femur_length_mm:
        lines += [
            "",
            "# myogait derives its pixel/metre scale as height_m x 0.245 (a",
            "# population femur-to-height ratio). Passing this value back",
            "# makes that same formula reproduce the *measured* femur",
            f"# ({subj.femur_length_mm:g} mm) instead of the population estimate.",
        ]
    height = f"height_m={calibration_height!r}"
    lines.append(f"stats = analyze_gait(data, cycles, {height})")
    lines += [
        "",
        'print(f"Cycles: {len(cycles[\'cycles\'])}")',
        "print(stats[\"spatiotemporal\"])",
        "",
    ]
    return "\n".join(lines)


def yaml_config(
    config: PipelineConfig,
    model: str = "mediapipe",
    with_depth: bool = False,
    with_seg: bool = False,
) -> str:
    """Return a ``myogait``-compatible YAML pipeline config.

    Settings the config schema has no key for are emitted as comments, so
    the file is honest about what it does and does not carry.
    """
    norm = config.normalize
    ang = config.angles
    ev = config.events
    cyc = config.cycles
    bias = config.bias
    subj = config.subject

    def scalar(value) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    lines = [
        "# myogait pipeline configuration",
        "# Generated by app myogait from the current workbench state.",
        "# Run with:  myogait batch VIDEO --config this_file.yaml",
        "",
        "extract:",
        f"  model: {model}",
        "  max_frames: null",
        "  flip_if_right: true",
        "  correct_inversions: true",
    ]
    if with_depth or with_seg:
        lines.append(
            f"  # Auxiliary heads (CLI flags): "
            f"{'--with-depth ' if with_depth else ''}"
            f"{'--with-seg' if with_seg else ''}".rstrip()
        )

    lines += [
        "",
        "normalize:",
        "  filters: [" + ", ".join(norm.filters) + "]",
        f"  butterworth_cutoff: {norm.butterworth_cutoff}",
        f"  butterworth_order: {norm.butterworth_order}",
        f"  center: {scalar(norm.center)}",
        f"  align: {scalar(norm.align)}",
        f"  correct_limbs: {scalar(norm.correct_limbs)}",
    ]
    extra_norm = []
    if norm.confidence_threshold is not None:
        extra_norm.append(f"confidence_filter(threshold={norm.confidence_threshold})")
    if norm.outlier_z is not None:
        extra_norm.append(f"detect_outliers(z_thresh={norm.outlier_z})")
    if norm.gap_max_frames != 10:
        extra_norm.append(f"normalize(gap_max_frames={norm.gap_max_frames})")
    if extra_norm:
        lines.append("  # No config key -- apply in Python: " + "; ".join(extra_norm))

    lines += [
        "",
        "angles:",
        f"  method: {ang.method}",
        f"  correction_factor: {ang.correction_factor}",
        f"  calibrate: {scalar(ang.calibrate)}",
        f"  calibration_frames: {ang.calibration_frames}",
        "  # No config key -- pass directly to compute_angles():",
        f"  #   calibration_dynamic_fallback={scalar(ang.calibration_dynamic_fallback)}",
        f"  #   calibration_min_std_deg={ang.calibration_min_std_deg}",
    ]
    post_angles = [
        (ang.frontal, "compute_frontal_angles(data)"),
        (ang.perspective, "apply_perspective_correction(data)"),
        (ang.detrend, "apply_linear_detrend(data)   # CLI: myogait analyze --detrend"),
    ]
    active = [label for flag, label in post_angles if flag]
    if active:
        lines.append("  # No config key -- apply after compute_angles():")
        for label in active:
            lines.append(f"  #   {label}")

    post_cycles = [
        (bias.ankle, "apply_ankle_bias_correction(data, cycles)"),
        (bias.hip, "apply_hip_bias_correction(data, cycles)"),
        (bias.knee, "apply_knee_bias_correction(data, cycles)"),
    ]
    active_bias = [label for flag, label in post_cycles if flag]
    if active_bias:
        lines.append("  # Bias corrections -- no config key, and phase-indexed,")
        lines.append("  # so they run after segment_cycles(), which must then be")
        lines.append("  # recomputed. Fitted on healthy adults: they mask the")
        lines.append("  # kinematic signs of neuromuscular disease. Benchmarking")
        lines.append("  # against a healthy reference only, never clinical reading.")
        for label in active_bias:
            lines.append(f"  #   {label}")

    lines += [
        "",
        "events:",
        f"  method: {ev.method}",
        f"  min_cycle_duration: {ev.min_cycle_duration}",
        f"  cutoff_freq: {ev.cutoff_freq}",
    ]
    if ev.is_consensus:
        lines.append(
            "  # Consensus mode has no config key -- in Python: "
            f"event_consensus(data, methods={list(ev.consensus_methods)}, "
            f"tolerance={ev.consensus_tolerance})"
        )
    if ev.adaptive:
        lines.append("  # detect_events(adaptive=True) overrides the two values above")

    lines += [
        "",
        "cycles:",
        f"  n_points: {cyc.n_points}",
        f"  min_duration: {cyc.min_duration}",
        f"  max_duration: {cyc.max_duration}",
        "",
        "subject:",
        f"  age: {scalar(subj.age)}",
        f"  sex: {scalar(subj.sex) if subj.sex else 'null'}",
        f"  height_m: {scalar(subj.height_m)}",
        f"  weight_kg: {scalar(subj.weight_kg)}",
        f"  pathology: {scalar(subj.pathology) if subj.pathology else 'null'}",
        "",
    ]
    return "\n".join(lines)


def cli_command(
    config: PipelineConfig, source: str = "video.mp4", model: str = "mediapipe"
) -> str:
    """Return the closest single CLI invocation to the current state."""
    parts = [
        "myogait run",
        source,
        f"-m {model}",
        f"--cutoff {config.normalize.butterworth_cutoff}",
        f"--correction {config.angles.correction_factor}",
        f"--events-method {config.events.method}",
    ]
    if not config.normalize.filters:
        parts.append("--no-filter")
    if not config.angles.calibrate:
        parts.append("--no-calibration")
    return " \\\n  ".join(parts)
