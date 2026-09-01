"""Exports and publication figures.

Screen figures are Plotly, for exploring. Exported figures are the
matplotlib ones myogait itself draws, so what ends up in a paper is the
package's own output and not a lookalike this app happens to render --
the figure in the article and the figure a reviewer reproduces from the
CLI are then the same figure.

Everything is produced into the session workspace and offered as a
download; nothing is left on the server past the retention window.
"""

from __future__ import annotations

import io
from pathlib import Path

import streamlit as st

from ..pipeline import PipelineResult, apply_study
from ..provenance import write_provenance
from ..quality import assess_quality
from ..runtime import get_runtime
from ..settings import SETTINGS
from . import state
from .components import page_header, reproducibility_panel, source_loader

#: myogait plotting functions, with what each one needs.
FIGURE_SPECS: dict[str, dict] = {
    "plot_summary": {"args": ("data", "cycles", "stats"), "label": "Summary dashboard"},
    "plot_angles": {"args": ("data",), "label": "Joint angles"},
    "plot_cycles": {"args": ("cycles",), "label": "Normalised cycles"},
    "plot_events": {"args": ("data",), "label": "Event timeline"},
    "plot_normative_comparison": {"args": ("data", "cycles"), "label": "Normative comparison"},
    "plot_quality_dashboard": {"args": ("data",), "label": "Quality dashboard"},
    "plot_rom_summary": {"args": ("cycles",), "label": "ROM summary"},
    "plot_butterfly": {"args": ("cycles",), "label": "Butterfly plot"},
    "plot_phase_plane": {"args": ("data",), "label": "Phase plane"},
    "plot_cadence_profile": {"args": ("data",), "label": "Cadence profile"},
    "plot_arm_swing": {"args": ("data", "cycles"), "label": "Arm swing"},
    # Takes the segmentation itself, not the score dict -- it derives the
    # gait variable scores internally.
    "plot_gvs_profile": {"args": ("cycles",), "label": "GVS / Movement Analysis Profile"},
    # Stratum defaults to "adult", same as plot_gvs_profile above -- not
    # exposed as a control here, to keep this tab's surface small.
    "plot_frontal_comparison": {"args": ("cycles",), "label": "Frontal-plane comparison"},
}


def render() -> None:
    source = state.get_source()
    if source is None:
        page_header("Export")
        source_loader(
            "Nothing loaded.",
            "Pick a finished extraction below, or go to New assessment to load "
            "one.",
            slot="export",
        )
        return

    config = state.get_config()
    result = state.get_runner().run(config)

    page_header("Export", "Data files, publication figures, and rendered video.")

    if not result.ok:
        failed = result.failed_stage
        st.error(f"The pipeline is failing at **{failed.name}** - fix that first.")
        st.caption(failed.error)
        return

    if source.is_demo:
        st.info(
            "The loaded dataset is synthetic. Exports will work, but the contents "
            "are a generated signal."
        )

    tab_data, tab_figures, tab_video, tab_report = st.tabs(
        ["Data files", "Figures", "Video", "PDF report"]
    )

    with tab_data:
        _data_tab(result, source)
    with tab_figures:
        _figures_tab(result)
    with tab_video:
        _video_tab(result, source)
    with tab_report:
        _report_tab(result, config)

    st.divider()
    reproducibility_panel(
        config, source_name=source.name, model=source.model,
        from_json=True,
        c3d_options=source.c3d_options if source.kind == "c3d" else None,
        key="export",
    )


# ── Data files ───────────────────────────────────────────────────────


def _data_tab(result: PipelineResult, source: state.Source) -> None:
    runtime = get_runtime()
    out = state.workspace().outputs
    out.mkdir(parents=True, exist_ok=True)
    stem = Path(source.name).stem or "myogait"

    st.markdown("**Pivot and summary**")
    columns = st.columns(2)

    with columns[0]:
        if st.button("Pivot JSON", use_container_width=True, key="exp_json"):
            _run_export(
                "Pivot JSON", out / f"{stem}.json",
                lambda path: _save_json(_export_pivot(result), path),
            )
        if st.button("Summary JSON", use_container_width=True, key="exp_sumjson"):
            _run_export(
                "Summary JSON", out / f"{stem}_summary.json",
                lambda path: _call("export_summary_json", result.data, result.cycles,
                                   result.stats, str(path)),
            )
    with columns[1]:
        if st.button("Excel workbook", use_container_width=True, key="exp_xlsx"):
            _run_export(
                "Excel", out / f"{stem}.xlsx",
                lambda path: _call("export_excel", result.data, str(path),
                                   result.cycles, result.stats),
            )
        if st.button("CSV bundle", use_container_width=True, key="exp_csv"):
            _run_csv_bundle(result, out, stem)
        if st.button("Landmarks Excel (raw)", use_container_width=True, key="exp_lmxlsx"):
            _run_export(
                "Landmarks Excel", out / f"{stem}_landmarks.xlsx",
                lambda path: _call("export_landmarks_excel", result.data, str(path),
                                   result.cycles),
            )

    st.divider()
    st.markdown("**Biomechanics interchange**")
    columns = st.columns(2)

    with columns[0]:
        if st.button("OpenSim .mot (kinematics)", use_container_width=True, key="exp_mot"):
            _run_export(
                "OpenSim .mot", out / f"{stem}.mot",
                lambda path: _call("export_mot", result.data, str(path)),
            )
        model_name = st.selectbox(
            "OpenSim model for .trc", ["", "gait2392", "gait2354"], key="exp_osim_model"
        )
        if st.button("OpenSim .trc (markers)", use_container_width=True, key="exp_trc"):
            _run_export(
                "OpenSim .trc", out / f"{stem}.trc",
                lambda path: _call("export_trc", result.data, str(path),
                                   opensim_model=model_name or None),
            )
    with columns[1]:
        c3d_ok = runtime.has("c3d")
        if st.button("C3D", use_container_width=True, disabled=not c3d_ok, key="exp_c3d"):
            _run_export(
                "C3D", out / f"{stem}.c3d",
                lambda path: _call("export_c3d", result.data, str(path)),
            )
        if not c3d_ok:
            st.caption("Needs: pip install \"myogait[c3d]\"")

        if st.button("Pose2Sim / OpenPose JSON", use_container_width=True, key="exp_op"):
            target = out / f"{stem}_openpose"
            _run_export(
                "OpenPose JSON", target,
                lambda path: _call("export_openpose_json", result.data, str(path)),
                zip_directory=True,
            )

    st.divider()
    st.markdown("**OpenSim setup files**")
    opensim_ok = runtime.has("opensim")
    if not opensim_ok:
        st.caption(runtime.missing_feature_hint("opensim"))
    columns = st.columns(3)
    with columns[0]:
        if st.button("Scale setup", use_container_width=True, key="exp_osim_scale",
                     disabled=not opensim_ok):
            _run_export(
                "OpenSim Scale setup", out / f"{stem}_scale_setup.xml",
                lambda path: _call("export_opensim_scale_setup", result.data, str(path)),
            )
    with columns[1]:
        if st.button("IK setup (+ .trc)", use_container_width=True, key="exp_osim_ik",
                     disabled=not opensim_ok):
            _run_export(
                "OpenSim IK setup", out / f"{stem}_ik",
                lambda path: _export_ik_bundle(result, path, stem),
                zip_directory=True,
            )
    with columns[2]:
        if st.button("Moco setup (+ .mot)", use_container_width=True, key="exp_osim_moco",
                     disabled=not opensim_ok):
            _run_export(
                "OpenSim Moco setup", out / f"{stem}_moco",
                lambda path: _export_moco_bundle(result, path, stem),
                zip_directory=True,
            )


def _export_ik_bundle(result: PipelineResult, target_dir: Path, stem: str) -> None:
    """IK setup needs a .trc on disk to point at, so this produces both."""
    target_dir.mkdir(parents=True, exist_ok=True)
    trc_path = target_dir / f"{stem}.trc"
    _call("export_trc", result.data, str(trc_path))
    _call("export_ik_setup", str(trc_path), str(target_dir / "ik_setup.xml"))


def _export_moco_bundle(result: PipelineResult, target_dir: Path, stem: str) -> None:
    """Moco setup needs a .mot on disk to point at, so this produces both."""
    target_dir.mkdir(parents=True, exist_ok=True)
    mot_path = target_dir / f"{stem}.mot"
    _call("export_mot", result.data, str(mot_path))
    _call("export_moco_setup", str(mot_path), str(target_dir / "moco_setup.xml"))


def _run_csv_bundle(result: PipelineResult, out: Path, stem: str) -> None:
    """export_csv writes several files, so it is offered as one archive."""
    target = out / f"{stem}_csv"
    _run_export(
        "CSV bundle", target,
        lambda path: _call("export_csv", result.data, str(path),
                           result.cycles, result.stats),
        zip_directory=True,
    )


# ── Figures ──────────────────────────────────────────────────────────


def _figures_tab(result: PipelineResult) -> None:
    st.caption(
        "Rendered by myogait's own matplotlib functions, so the exported figure "
        "matches what the package produces from the CLI."
    )
    columns = st.columns([2, 1, 1])
    choice = columns[0].selectbox(
        "Figure", list(FIGURE_SPECS),
        format_func=lambda name: FIGURE_SPECS[name]["label"], key="fig_choice",
    )
    dpi = columns[1].select_slider("DPI", [100, 150, 200, 300, 600], value=300, key="fig_dpi")
    fmt = columns[2].selectbox("Format", ["png", "pdf", "svg"], key="fig_fmt")

    if not st.button("Render", type="primary", use_container_width=True, key="fig_render"):
        return

    try:
        figure = _build_figure(choice, result)
    except Exception as exc:
        st.error(f"{choice} failed: {type(exc).__name__}: {exc}")
        return

    if figure is None:
        st.warning(f"{choice} returned nothing for this configuration.")
        return

    buffer = io.BytesIO()
    figure.savefig(buffer, format=fmt, dpi=int(dpi), bbox_inches="tight")
    buffer.seek(0)

    if fmt == "png":
        st.image(buffer.getvalue(), use_container_width=True)
    else:
        st.success(f"Rendered {choice} as {fmt.upper()}.")

    st.download_button(
        f"Download {choice}.{fmt}",
        buffer.getvalue(),
        file_name=f"{choice}.{fmt}",
        mime={"png": "image/png", "pdf": "application/pdf", "svg": "image/svg+xml"}[fmt],
        use_container_width=True,
        key="fig_download",
    )

    import matplotlib.pyplot as plt

    plt.close(figure)

    st.divider()
    _normative_animation_section(result)


def _normative_animation_section(result: PipelineResult) -> None:
    runtime = get_runtime()
    st.markdown("**Animated normative comparison**")
    if not runtime.has("normative"):
        st.caption(runtime.missing_feature_hint("normative"))
        return
    st.caption(
        "The patient curve traces out against the normative band, frame by frame - "
        "useful in a talk where the static overlay above is read too quickly."
    )
    columns = st.columns(2)
    stratum = columns[0].selectbox("Stratum", ["adult", "elderly", "pediatric"], key="anim_stratum")
    fps = columns[1].slider("Animation fps", 5, 30, 10, key="anim_fps")

    if not st.button("Render animated GIF", use_container_width=True, key="anim_go"):
        return

    out = state.workspace().outputs / "normative_comparison.gif"
    _run_export(
        "Normative animation", out,
        lambda path: _call(
            "animate_normative_comparison", result.cycles, stratum=stratum,
            output_path=str(path), fps=int(fps),
        ),
        spinner="Rendering the animation - this takes a while.",
    )


def _build_figure(name: str, result: PipelineResult):
    """Call a myogait plotting function with the arguments it declares.

    Looks at the top-level package first, then falls back to
    myogait.plotting directly: plot_frontal_comparison exists in that
    module but is missing from __init__.py's lazy-export map, unlike
    every other plot_* function.
    """
    import myogait
    import myogait.plotting as plotting_module

    spec = FIGURE_SPECS[name]
    function = getattr(myogait, name, None) or getattr(plotting_module, name, None)
    if function is None:
        raise RuntimeError(f"myogait has no {name} in this version.")

    values = []
    for argument in spec["args"]:
        if argument == "data":
            values.append(result.data)
        elif argument == "cycles":
            values.append(result.cycles)
        elif argument == "stats":
            values.append(result.stats)
    return function(*values)


# ── Video ────────────────────────────────────────────────────────────


def _video_tab(result: PipelineResult, source: state.Source) -> None:
    runtime = get_runtime()

    st.markdown("**Anonymised stick figure**")
    st.caption(
        "Renders from the landmarks alone, so the subject is not identifiable. "
        "This is the form to prefer when a figure or a talk leaves the lab."
    )
    if runtime.has("stickfigure"):
        columns = st.columns(3)
        fmt = columns[0].selectbox("Format", ["gif", "mp4"], key="stick_fmt")
        show_angles = columns[1].checkbox("Angle labels", value=False, key="stick_angles")
        trail = columns[2].checkbox("Motion trail", value=False, key="stick_trail")
        if st.button("Render stick figure", use_container_width=True, key="stick_go"):
            out = state.workspace().outputs / f"stickfigure.{fmt}"
            _run_export(
                "Stick figure", out,
                lambda path: _call(
                    "render_stickfigure_animation", result.data, str(path),
                    format=fmt, show_angles=show_angles, show_trail=trail,
                    cycles=result.cycles,
                ),
                spinner="Rendering frame by frame - this takes a while.",
            )
    else:
        st.caption(runtime.missing_feature_hint("stickfigure"))

    st.divider()
    st.markdown("**Skeleton overlay on the original video**")
    if source.path is None or source.kind != "video":
        st.caption(
            "Needs the source video on the server. It is available right after an "
            "extraction run from this app, not when a pivot JSON is loaded on its own."
        )
        return

    st.warning(
        "The overlay shows the subject's face and body. Keep it inside the lab, "
        f"and remember it is deleted after {SETTINGS.retention_hours} h like "
        "everything else here."
    )
    columns = st.columns(3)
    show_angles = columns[0].checkbox("Angles", value=True, key="ovl_angles")
    show_events = columns[1].checkbox("Events", value=True, key="ovl_events")
    show_confidence = columns[2].checkbox("Confidence", value=False, key="ovl_conf")

    if st.button("Render overlay", use_container_width=True, key="ovl_go"):
        out = state.workspace().outputs / "overlay.mp4"
        _run_export(
            "Skeleton overlay", out,
            lambda path: _call(
                "render_skeleton_video", str(source.path), result.data, str(path),
                show_angles=show_angles, show_events=show_events,
                show_confidence=show_confidence,
            ),
            spinner="Rendering the video - this takes a while.",
        )


# ── PDF report ───────────────────────────────────────────────────────


def _report_tab(result: PipelineResult, config) -> None:
    runtime = get_runtime()
    if not runtime.has("report"):
        st.caption(runtime.missing_feature_hint("report"))
        return

    st.caption(
        "myogait's multi-page clinical report: kinematic plots, spatio-temporal "
        "tables and normative comparison."
    )
    language = st.selectbox(
        "Report language", ["en", "fr"], key="rep_lang",
        help="The report generator is bilingual even though this interface is not.",
    )

    if not result.n_cycles:
        st.warning("The report needs at least one segmented cycle.")
        return

    if st.button("Generate PDF", type="primary", use_container_width=True, key="rep_go"):
        out = state.workspace().outputs / "gait_report.pdf"
        _run_export(
            "PDF report", out,
            lambda path: _call(
                "generate_report", result.data, result.cycles, result.stats,
                str(path), language=language,
            ),
            spinner="Building the report...",
        )


# ── Plumbing ─────────────────────────────────────────────────────────


def _call(name: str, *args, **kwargs):
    """Invoke a myogait export function by name."""
    import myogait

    function = getattr(myogait, name, None)
    if function is None:
        raise RuntimeError(f"myogait has no {name} in this version.")
    return function(*args, **kwargs)


def _export_pivot(result: PipelineResult) -> dict:
    """``result.data`` with the edited study identifiers merged in for download.

    The subject/anthropometrics are already in ``result.data`` (applied as a
    pipeline stage from the Subject config); study is metadata that lives in
    session state, so it is merged here at export time. A deep copy keeps the
    live result untouched.
    """
    import copy

    from .sidebar import K_STUDY_EDIT

    data = copy.deepcopy(result.data)
    return apply_study(data, st.session_state.get(K_STUDY_EDIT))


def _save_json(data: dict, path: Path) -> str:
    from myogait.schema import save_json

    return save_json(data, str(path))


def _run_export(
    label: str,
    target: Path,
    produce,
    zip_directory: bool = False,
    spinner: str = "",
) -> None:
    """Run one export, then offer the result as a download.

    Failures are reported with the exception verbatim: an export that
    fails because an optional dependency is missing should say so, not
    disappear behind a generic message.

    Also exposed as :data:`offer_export` for other pages (the cohort
    bundle): the provenance context degrades gracefully when no single
    source is loaded.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with st.spinner(spinner or f"Writing {label}..."):
            produce(target)
    except Exception as exc:
        st.error(f"{label} failed: {type(exc).__name__}: {exc}")
        return

    source = state.get_source()
    result = state.get_runner().run(state.get_config()) if source else PipelineResult()
    provenance_context = {
        "source_data": source.data if source else None,
        "source_key": source.key if source else None,
        "source_kind": source.kind if source else None,
        "model": source.model if source else None,
        "quality": assess_quality(result.data, result.cycles),
    }

    if zip_directory:
        import shutil

        if not target.is_dir():
            st.error(f"{label} reported success but wrote no directory.")
            return
        provenance_path = write_provenance(
            target / "provenance.json", state.get_config(), **provenance_context
        )
        archive = shutil.make_archive(str(target), "zip", root_dir=str(target))
        payload = Path(archive).read_bytes()
        filename = Path(archive).name
        mime = "application/zip"
    else:
        if not target.is_file():
            st.error(f"{label} reported success but wrote no file.")
            return
        provenance_path = write_provenance(
            target.with_suffix(target.suffix + ".provenance.json"),
            state.get_config(),
            **provenance_context,
        )
        payload = target.read_bytes()
        filename = target.name
        mime = "application/octet-stream"

    size_mb = len(payload) / (1024 * 1024)
    st.success(f"{label} ready - {filename} ({size_mb:.1f} MB)")
    st.download_button(
        f"Download {filename}",
        payload,
        file_name=filename,
        mime=mime,
        use_container_width=True,
        key=f"dl_{filename}",
    )
    st.download_button(
        "Download provenance JSON",
        provenance_path.read_bytes(),
        file_name=provenance_path.name,
        mime="application/json",
        use_container_width=True,
        key=f"dl_provenance_{filename}",
    )


#: Public name for other pages (see _run_export's docstring).
offer_export = _run_export
