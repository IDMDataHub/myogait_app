"""Shared interface pieces.

The reproducibility panel is the one worth reading closely: it appears on
every page and is generated from the same config object the pipeline just
ran, so what it shows is what happened, not a description of it.
"""

from __future__ import annotations

import streamlit as st

from ..branding import BRANDING
from ..charts.theme import PLOTLY_CONFIG
from ..codegen import cli_command, python_snippet, yaml_config
from ..pipeline import PipelineConfig, PipelineResult
from ..runtime import Runtime, get_runtime
from ..settings import SETTINGS
from ..storage import purge_expired, workspace_usage
from . import state


def is_dark() -> bool:
    """Whether Streamlit is rendering in a dark theme.

    Charts need to know, and the theme option is the only signal
    available server-side.
    """
    try:
        base = st.get_option("theme.base")
        if base:
            return str(base).lower() == "dark"
    except Exception:
        pass
    try:
        return str(st.context.theme.type).lower() == "dark"
    except Exception:
        return False


def chart(fig, key: str | None = None) -> None:
    """Render a Plotly figure with the app's shared config."""
    st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, key=key)


# ── Header and runtime ───────────────────────────────────────────────


def page_header(title: str, description: str = "") -> None:
    st.markdown(f"### {title}")
    if description:
        st.caption(description)


def sidebar_identity() -> None:
    """App name or logo. The single place branding surfaces."""
    if BRANDING.logo_path and BRANDING.logo_path.is_file():
        st.image(str(BRANDING.logo_path), use_container_width=True)
    else:
        st.markdown(f"## {BRANDING.app_name}")
    st.caption(BRANDING.tagline)


def runtime_badge(runtime: Runtime | None = None) -> None:
    """A compact statement of what this machine can do."""
    runtime = runtime or get_runtime()
    device_label = {
        "cuda": "NVIDIA GPU",
        "xpu": "Intel GPU",
        "cpu": "CPU",
    }.get(runtime.device, runtime.device)

    st.caption(
        f"myogait `{runtime.myogait_version or 'not installed'}` &middot; "
        f"gaitkit `{runtime.gaitkit_version or 'absent'}` &middot; {device_label}"
    )
    if not runtime.accelerated:
        st.caption(
            "No GPU detected: heavy backends will run on CPU and take a long time."
        )


def runtime_warnings(runtime: Runtime | None = None) -> None:
    """Surface version problems once, at the top of the app.

    These are not cosmetic: an old myogait silently lacks whole families
    of function, and an old gaitkit removes the detectors the comparator
    exists to compare.
    """
    runtime = runtime or get_runtime()
    if not runtime.warnings:
        return
    with st.expander(
        f"{len(runtime.warnings)} environment warning(s)", expanded=not runtime.myogait_ok
    ):
        for warning in runtime.warnings:
            st.warning(warning)
        st.markdown(
            "Fix with:\n"
            "```bash\n"
            "pip install --upgrade "
            '"myogait[mediapipe,yolo,excel,yaml] @ '
            'git+https://github.com/IDMDataHub/myogait.git@master" "gaitkit>=1.4.8"\n'
            "```"
        )


def storage_banner() -> None:
    """State the retention rule plainly rather than deleting silently."""
    usage = workspace_usage(SETTINGS)
    st.caption(
        f"Nothing is kept: uploads and results are deleted after "
        f"{SETTINGS.retention_hours} h. "
        f"Currently {usage['total_mb']} MB across {usage['n_jobs']} job(s)."
    )
    if st.button("Purge expired data now", use_container_width=True):
        report = purge_expired(SETTINGS)
        st.success(
            f"Removed {report['jobs_removed']} job(s) and "
            f"{report['sessions_removed']} session(s), freeing {report['freed_mb']} MB."
        )


# ── Pipeline feedback ────────────────────────────────────────────────


def stage_status(result: PipelineResult) -> None:
    """Per-stage timings, and the failure when there is one.

    Timings are shown because on a workbench they are actionable: they
    tell you which knob is the expensive one before you start sweeping it.
    """
    failed = result.failed_stage
    if failed:
        st.error(f"Stage **{failed.name}** failed - {failed.error}")

    for outcome in result.outcomes:
        if outcome.note:
            st.warning(f"**{outcome.name}**: {outcome.note}")

    parts = []
    for outcome in result.outcomes:
        mark = "cached" if outcome.cached else f"{outcome.seconds * 1000:.0f} ms"
        parts.append(f"{outcome.name} ({mark})")
    if parts:
        st.caption(" &rarr; ".join(parts) + f" &middot; total {result.total_seconds:.2f} s")


def source_summary(source: state.Source) -> None:
    """What is loaded, stated in the terms a reviewer would ask for."""
    columns = st.columns(4)
    columns[0].metric("Frames", source.n_frames)
    columns[1].metric("Duration", f"{source.duration_s:.1f} s")
    columns[2].metric("Frame rate", f"{source.fps:.0f} fps")
    columns[3].metric("Model", source.model)
    if source.is_demo:
        st.info(
            "This is the synthetic dataset - a generated gait-like signal, not a "
            "recording. Use it to learn the controls; do not read clinical meaning "
            "into the numbers."
        )
    if source.is_c3d and source.c3d_options:
        _c3d_source_summary(source.c3d_options)


def _c3d_source_summary(options: dict) -> None:
    """What load_c3d actually matched, and whether the app corrected it.

    A C3D file's marker set rarely covers every myogait landmark (the
    default mapping, for instance, has no elbow or wrist), so this states
    plainly what is and is not present rather than letting a downstream
    NaN be the first sign of it.
    """
    matched = options.get("matched_landmarks") or []
    missing = options.get("missing_landmarks") or []
    st.info(f"C3D source - {len(matched)} of {len(matched) + len(missing)} landmark(s) matched.")
    if missing:
        st.caption("Not covered by this marker mapping: " + ", ".join(missing))
    if options.get("fix_aspect_ratio") and options.get("ranges"):
        ap_range, vert_range = options["ranges"]
        st.caption(
            f"Aspect-ratio correction applied from the file (AP range "
            f"{ap_range:.1f}, vertical range {vert_range:.1f}) - without it, "
            "compute_angles' own aspect-ratio fix would not trigger for this "
            "source."
        )
    elif options.get("fix_aspect_ratio") is False:
        st.caption(
            "Aspect-ratio correction from the file was left off - angles and "
            "segment lengths may be biased if the AP and vertical axes have "
            "different physical ranges in this recording."
        )


# ── Reproducibility ──────────────────────────────────────────────────


def reproducibility_panel(
    config: PipelineConfig,
    source_name: str = "video.mp4",
    model: str = "mediapipe",
    from_json: bool = False,
    c3d_options: dict | None = None,
    key: str = "repro",
) -> None:
    """Show the current state as runnable code.

    Present on every analysis page. A workbench that cannot hand back
    the exact commands it just ran cannot be written up, and a parameter
    study that cannot be replayed outside the app is not a result.
    """
    if not SETTINGS.show_reproducibility:
        return

    with st.expander("Reproduce this - Python, YAML, CLI", expanded=False):
        tab_py, tab_yaml, tab_cli = st.tabs(["Python", "YAML config", "CLI"])

        with tab_py:
            snippet = python_snippet(
                config, source=source_name, model=model, from_json=from_json,
                c3d_options=c3d_options,
            )
            st.code(snippet, language="python")
            st.download_button(
                "Download script",
                snippet,
                file_name="reproduce_myogait.py",
                mime="text/x-python",
                key=f"{key}_py",
                use_container_width=True,
            )

        with tab_yaml:
            config_text = yaml_config(config, model=model)
            st.caption(
                "The subset `myogait.load_config()` reads. Settings with no config "
                "key are listed as comments rather than dropped."
            )
            st.code(config_text, language="yaml")
            st.download_button(
                "Download config",
                config_text,
                file_name="myogait_config.yaml",
                mime="text/yaml",
                key=f"{key}_yaml",
                use_container_width=True,
            )

        with tab_cli:
            st.caption(
                "The closest single command. It covers the common parameters only - "
                "use the Python tab when corrections or consensus are enabled."
            )
            st.code(cli_command(config, source_name, model), language="bash")


def empty_state(message: str, hint: str = "") -> None:
    """Consistent placeholder when a page has nothing to show yet."""
    st.info(message)
    if hint:
        st.caption(hint)
