"""Shared interface pieces.

The reproducibility panel is the one worth reading closely: it appears on
every page and is generated from the same config object the pipeline just
ran, so what it shows is what happened, not a description of it.
"""

from __future__ import annotations

import html

import streamlit as st

from ..branding import BRANDING
from ..charts.theme import PLOTLY_CONFIG
from ..codegen import cli_command, python_snippet, yaml_config
from ..pipeline import PipelineConfig, PipelineResult
from ..runtime import Runtime, get_runtime
from ..settings import SETTINGS
from ..storage import purge_expired, workspace_usage
from . import state

#: Session-state key for the per-page figure counter that drives the
#: "fig. N" tag in chart(). Reset by page_header() so numbering restarts
#: at 1 on every page rather than climbing across the whole session.
_K_FIGURE_COUNTER = "_mg_fig_counter"


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


#: Figure-key substrings (matched from the end of the ``key`` argument,
#: which every call site already builds from the plotted metric's name)
#: to a human caption for the "fig. N" frame. Purely decorative -- falls
#: back to a humanised version of the key itself for anything unlisted,
#: so a new chart() call site never needs to touch this table to render
#: correctly, just less legibly.
_FIGURE_CAPTIONS = {
    "timeline": "Joint angle timeline",
    "cycles": "Cycle overlay",
    "rom": "Range of motion summary",
    "stance": "Stance / swing split",
    "cadence": "Instantaneous cadence",
    "com": "Center of mass",
    "sway": "Postural sway",
    "derivatives": "Angular velocity / acceleration",
    "spectrogram": "Time-frequency analysis",
    "pca": "PCA waveform components",
    "quality": "Signal quality",
    "diff": "Difference from reference",
    "heat": "Agreement heatmap",
    "metric": "Metric comparison",
    "raster": "Event raster",
    "accuracy": "Video vs Vicon mean curves",
}


def _figure_caption(key: str | None) -> str:
    if not key:
        return "Figure"
    tokens = key.lower().split("_")
    for token in reversed(tokens):
        if token in _FIGURE_CAPTIONS:
            return _FIGURE_CAPTIONS[token]
    words = [t for t in tokens if t not in ("fig", "pool")]
    return " ".join(words).title() or "Figure"


def chart(fig, key: str | None = None) -> None:
    """Render a Plotly figure with the app's shared config.

    Wrapped in the identity's "fig. N" frame: a bordered container, a
    small numbered tag, and a caption bar -- purely presentational, the
    figure itself (data, colours, layout) is untouched. Numbering is
    per-page (page_header() resets it), since the number of charts a
    session actually renders depends on the loaded data and the controls
    in use, unlike a fixed mockup's own static figure count.
    """
    st.session_state[_K_FIGURE_COUNTER] = st.session_state.get(_K_FIGURE_COUNTER, 0) + 1
    n = st.session_state[_K_FIGURE_COUNTER]
    tag_color = BRANDING.primary_red if n % 2 else BRANDING.primary_blue
    container_key = f"mg_fig_{key}" if key else f"mg_fig_n{n}"

    with st.container(border=True, key=container_key):
        st.markdown(
            f'<div class="mg-fig-tag" style="background:{tag_color};'
            f'color:{BRANDING.primary_ink_for(False)}">fig. {n}</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG, key=key)
        st.markdown(
            f'<div class="mg-fig-caption">{html.escape(_figure_caption(key))}</div>',
            unsafe_allow_html=True,
        )


# ── Header and runtime ───────────────────────────────────────────────

#: (page number, eyebrow label) per page title, matching the Claude
#: Design mockup's header treatment. A title with no entry here (a page
#: added later, or page_pool.render() called with a title not yet wired
#: into app.py's nav) still renders correctly via the "--" fallback.
_PAGE_META: dict[str, tuple[str, str]] = {
    # Top-level screens carry the folio the nav reads by.
    "New assessment": ("01", "Capture"),
    "Analysis": ("02", "Read the study"),
    "Advanced": ("03", "Research tools"),
    "Index": ("04", "Reference & guides"),
    # Nested views (shown inside a tab or a scope) keep their own eyebrow.
    "Pipeline explorer": ("02", "Parametric explorer"),
    "Comparator": ("03", "Colour encodes method"),
    "Longitudinal": ("04", "Track over time"),
    "Export": ("05", "Data & figures out"),
    "Accelerometry biomarkers": ("06", "Virtual sensor, no IMU worn"),
    "Experimental": ("07", "AIM benchmark"),
    "One group": ("03", "Study by condition"),
    "Two groups": ("03", "Two named groups compared"),
}


#: Set by a screen that hosts other pages in its tabs/scopes (Advanced,
#: Analysis) so those nested pages skip their own folio -- the parent screen
#: already carries the number. Reset each run in app.main.
_K_EMBEDDED = "_embedded_header"


def page_header(title: str, description: str = "") -> None:
    st.session_state[_K_FIGURE_COUNTER] = 0
    if st.session_state.get(_K_EMBEDDED):
        # Nested inside another screen -- the parent showed the folio, so drop
        # the numbered block here and keep only the one-line description.
        if description:
            st.caption(description)
        return
    num, eyebrow = _PAGE_META.get(title, ("--", ""))
    left = BRANDING.side_colors["left"]
    right = BRANDING.side_colors["right"]

    words = title.split(" ")
    lead = html.escape(" ".join(words[:-1]) + " ") if len(words) > 1 else ""
    block_word = html.escape(words[-1])
    desc_html = (
        f'<p class="mg-header-desc">{html.escape(description)}</p>' if description else ""
    )

    st.markdown(
        f"""
<div class="mg-header">
  <div class="mg-header-bar"></div>
  <div class="mg-header-circle"></div>
  <div class="mg-header-top">
    <div class="mg-header-num">{html.escape(num)}</div>
    <div class="mg-header-eyebrow">{html.escape(eyebrow)}</div>
    <div class="mg-header-side"><span style="background:{left}"></span><span style="background:{right}"></span></div>
  </div>
  <h1 class="mg-header-title">{lead}<span class="mg-header-title-block">{block_word}</span></h1>
  {desc_html}
</div>
""",
        unsafe_allow_html=True,
    )


def sidebar_identity() -> None:
    """App name or logo. The single place branding surfaces."""
    if BRANDING.logo_path and BRANDING.logo_path.is_file():
        st.image(str(BRANDING.logo_path), use_container_width=True)
        st.caption(BRANDING.tagline)
        return

    st.markdown(
        f"""
<div class="mg-sidebar-id">
  <div class="mg-sidebar-mark"><span style="background:{BRANDING.accent}"></span><span style="background:{BRANDING.primary_red}"></span></div>
  <div>
    <div class="mg-sidebar-id-name">{html.escape(BRANDING.app_name)}</div>
    <div class="mg-sidebar-id-tag">{html.escape(BRANDING.tagline)}</div>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def sidebar_section_marker(number: str, color: str) -> None:
    """A small coloured numeral chip preceding a numbered sidebar section.

    Purely decorative, placed just above the matching ``st.expander`` --
    an expander's own summary cannot hold rich HTML, so the numeral lives
    just outside it rather than inside the label text.
    """
    st.markdown(
        f'<div class="mg-sec-num" style="color:{color}">{html.escape(number)}</div>',
        unsafe_allow_html=True,
    )


def runtime_badge(runtime: Runtime | None = None) -> None:
    """A compact statement of what this machine can do."""
    runtime = runtime or get_runtime()
    device_label = {
        "cuda": "NVIDIA GPU",
        "xpu": "Intel GPU",
        "cpu": "CPU",
    }.get(runtime.device, runtime.device)

    st.caption(
        f"[myogait](https://github.com/IDMDataHub/myogait) "
        f"`{runtime.myogait_version or 'not installed'}` &middot; "
        f"[gaitkit](https://github.com/IDMDataHub/gaitkit) "
        f"`{runtime.gaitkit_version or 'absent'}` &middot; {device_label} &middot; "
        f"retention {SETTINGS.retention_hours}h"
    )
    if not runtime.accelerated:
        st.caption(
            "No GPU detected: heavy backends will run on CPU and take a long time."
        )


_K_BACKEND_AVAILABILITY = "_cached_backend_availability"


def cached_backend_availability(runtime: Runtime, *, key: str) -> dict[str, bool]:
    """Session-cached ``Runtime.backend_availability()``.

    That probe is deliberately not cached inside ``Runtime`` itself (its own
    docstring: "caching this across reruns would leave the model picker
    stale" if a setup job installs a backend mid-session) -- but the
    consequence is that it re-probes ~18 backends on *every* Streamlit
    rerun, including one triggered by an unrelated widget on the same page.
    Caching it here per session, with an explicit refresh action
    (``backend_availability_refresh_button``) alongside it, keeps the
    "won't miss a newly-installed backend" property while dropping the
    per-keystroke cost. *key* namespaces the cache per call site (a page
    should pass its own slot name) so unrelated pages don't share one stale
    entry.
    """
    state_key = f"{_K_BACKEND_AVAILABILITY}:{key}"
    if state_key not in st.session_state:
        st.session_state[state_key] = runtime.backend_availability()
    return st.session_state[state_key]


def backend_availability_refresh_button(runtime: Runtime, *, key: str) -> None:
    """Pair with ``cached_backend_availability`` to force a re-probe."""
    state_key = f"{_K_BACKEND_AVAILABILITY}:{key}"
    if st.button("Refresh available models", key=f"refresh_backends_{key}"):
        st.session_state[state_key] = runtime.backend_availability()
        st.rerun()


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
    cells = [
        ("Frames", str(source.n_frames), ""),
        ("Duration", f"{source.duration_s:.1f} s", "ink"),
        ("Frame rate", f"{source.fps:.0f} fps", ""),
        ("Model", str(source.model), "accent"),
    ]
    html_parts = ['<div class="mg-metric-grid">']
    for label, value, variant in cells:
        variant_class = f" mg-metric-{variant}" if variant else ""
        html_parts.append(
            f'<div class="mg-metric-cell{variant_class}">'
            f'<div class="mg-metric-label">{html.escape(label)}</div>'
            f'<div class="mg-metric-value">{html.escape(value)}</div>'
            f"</div>"
        )
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)

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


def _job_label(job) -> str:
    study = job.study or {}
    meta = " · ".join(x for x in (study.get("patient_id"), study.get("condition")) if x)
    text = f"{job.video_name} — {job.model}"
    return f"{text}  ({meta})" if meta else text


def source_loader(message: str, hint: str = "", *, slot: str = "") -> None:
    """An empty state that can actually load a recording, not just explain.

    Every analysis view reads one source from session state; with none set
    the view used to dead-end on a message and send the user away. This offers
    the two ways in on the spot -- pick a finished extraction, or jump to New
    assessment to start or upload one -- so nobody has to leave to get unstuck.

    ``slot`` disambiguates the widget keys so two loaders can share a screen
    (e.g. the Advanced page renders several single-source views at once);
    pass a unique string per call site. Defaults to the message for the common
    one-per-screen case.
    """
    from ..jobs import DONE, JobManager  # lazy: keep the import graph shallow

    token = slot or message
    st.info(message)
    if hint:
        st.caption(hint)

    done = [j for j in JobManager(SETTINGS).list_jobs() if j.status == DONE]
    with st.container(border=True):
        if done:
            st.markdown("**Load a finished extraction**")
            choice = st.selectbox(
                "Finished extractions", done, format_func=_job_label,
                key=f"loader_pick_{token}", label_visibility="collapsed",
            )
            columns = st.columns([3, 2])
            if columns[0].button(
                "Load this recording", type="primary", use_container_width=True,
                key=f"loader_load_{token}",
            ):
                path = choice.result_path(SETTINGS)
                if path:
                    _install_pivot(path, f"{choice.video_name} [{choice.model}]")
                else:
                    st.error("The result file is gone - it may have been purged.")
            _to_new_assessment(columns[1], key=f"loader_data_{token}")
        else:
            st.caption("No finished extraction on this machine yet.")
            _to_new_assessment(st, key=f"loader_data_{token}")


def recording_switcher(slot: str) -> None:
    """A compact, always-on control to switch which recording this tab reads.

    Advanced's four tabs (Pipeline explorer, Comparator, Export, Method
    validation) all read the one shared active source (``state.get_source``)
    -- so once a video extraction *and* its C3D are both ready (Recent jobs),
    there was previously no way to explore the other one from inside a tab;
    only ``source_loader``'s empty-state picker offered this, and it
    disappears the moment a source is loaded. This renders unconditionally,
    loaded-or-not, right below each tab's own header.

    Switching here changes the *shared* active source (the same one every
    other Advanced tab and New assessment/Analysis read) -- there is one
    recording being explored at a time, not an independent choice held per
    tab. Good enough to compare two ready recordings without leaving the
    tab; if trying to hold e.g. Pipeline explorer on the video while Export
    stays on the C3D at the same time turns out to matter, that needs each
    tab to cache its own source+runner independently, a bigger change than
    this control -- not attempted here.
    """
    from ..jobs import DONE, JobManager

    done = [j for j in JobManager(SETTINGS).list_jobs() if j.status == DONE]
    if len(done) < 2:
        return  # nothing to switch to yet

    source = state.get_source()
    label = f"Recording: **{source.name}**" if source else "Pick a recording"
    with st.expander(label, expanded=source is None):
        st.caption(
            "Switches the recording every Advanced tab explores -- not just "
            "this one."
        )
        choice = st.selectbox(
            "Ready recordings", done, format_func=_job_label,
            key=f"switch_pick_{slot}", label_visibility="collapsed",
        )
        if st.button("Load this recording", key=f"switch_load_{slot}"):
            path = choice.result_path(SETTINGS)
            if path:
                _install_pivot(path, f"{choice.video_name} [{choice.model}]")
            else:
                st.error("The result file is gone - it may have been purged.")


def _to_new_assessment(container, key: str) -> None:
    """A button that jumps to New assessment (start or upload a recording).

    Cannot set ``st.session_state["nav_page"]`` directly here: that widget
    (the sidebar pills) already ran earlier in this same script, and
    Streamlit refuses to write a widget's key once it has been
    instantiated in the current run. Sets a pending-navigation key instead;
    ``app.main()`` seeds ``nav_page`` from it before the pills widget is
    created in the *next* run, which is the point that write is allowed.
    """
    if container.button(
        "Go to New assessment", use_container_width=True, key=key,
    ):
        st.session_state["_pending_nav_page"] = "New assessment"
        st.rerun()


def _install_pivot(path, name: str) -> None:
    """Read a pivot file and install it as the current source."""
    from ..validation import validate_pivot

    try:
        from myogait import load_json

        data = load_json(str(path))
    except Exception as exc:
        st.error(f"Could not read the pivot file: {type(exc).__name__}: {exc}")
        return

    errors = validate_pivot(data)
    if errors:
        st.error("Invalid myogait pivot: " + " ".join(errors))
        return

    model = str((data.get("extraction") or {}).get("model") or "unknown")
    kind, source_path = state.resolve_pivot_kind_and_path(data, path)
    state.set_source(
        state.Source(
            kind=kind, name=name, data=data,
            key=state.source_key(name, (path.stat().st_size, path.stat().st_mtime)),
            model=model, path=source_path,
        )
    )
    st.rerun()


def clinical_note(kind: str, text: str) -> None:
    """One consistent inline note for clinical caveats.

    Data-limit, where-this-differs and silent-fallback messages should read the
    same wherever they appear, so screens do not each invent their own wording
    and styling. ``kind`` is ``"info"``, ``"warning"`` or ``"danger"``; anything
    else falls back to ``"info"``. Wraps Streamlit's native alerts, which already
    theme correctly in light and dark.
    """
    render = {"info": st.info, "warning": st.warning, "danger": st.error}.get(kind, st.info)
    render(text)


#: The single wording for the two accelerometry-family calculations that share
#: names (RMS, harmonic ratio) but not their site / normalisation / filtering,
#: so the Accelerometry page and the cohort overview must not be read against
#: each other. Both screens call ``accelerometry_non_comparable_note`` -- do not
#: re-phrase it in only one place (DEV-01 / DOC-01).
ACCELEROMETRY_NON_COMPARABLE = (
    "These biomarkers are computed differently from the similarly-named ones in "
    "the cohort tables (Analysis): different site, normalisation and filtering, "
    "not the same numbers. Don't compare a value from this page directly against "
    "a cohort-view value of the same name."
)


def accelerometry_non_comparable_note() -> None:
    """Render the shared accelerometry non-comparability warning (DEV-01)."""
    clinical_note("warning", ACCELEROMETRY_NON_COMPARABLE)
