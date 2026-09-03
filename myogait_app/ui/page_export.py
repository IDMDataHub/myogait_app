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
from .components import (
    _job_label,
    page_header,
    recording_switcher,
    reproducibility_panel,
    source_loader,
)

#: Session-state key for named job groups staged here, for Advanced's
#: rebuilt Patient over time / Two groups scopes to recall directly
#: (Phase 3 of the audit's action plan -- see _group_staging_section).
#: Nothing reads this back yet; this module only produces it.
_GROUPS_KEY = "_named_job_groups"

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


def render(scope: str = "full") -> None:
    """*scope* controls which tabs actually show.

    ``"full"`` (default, Advanced's own Export tab) is unchanged: every
    tab, video included. ``"light"`` (Analysis's Export scope) keeps only
    Data files, Figures and PDF report (myogait's own native report) --
    Video, Video report and MoCap report are Advanced-only there, plus it
    adds the group-staging tool below. The audit found the un-scoped
    version's full surface duplicated across two nav locations with no
    distinction (UX-06); this is what makes the "slim" side of that split
    real rather than cosmetic.

    Export reads three independent session-state stores, and offers what
    each holds rather than dead-ending on the one that is empty:

    - ``state.get_source()`` -- one recording, for the data / figures /
      report tabs.
    - ``pool_runs`` -- a loaded cohort, for the cohort bundle (``"light"``
      only; ``"full"`` keeps it under Advanced's cohort scope views).
    - finished jobs on disk -- for the group-staging tool (``"light"``)
      and the combined video+C3D pair export (``"full"``).

    A user who has built a cohort but loaded no single recording used to
    hit "Nothing loaded" here with no way forward, even as Analysis's own
    header advertised the cohort right above.
    """
    source = state.get_source()
    config = state.get_config()
    cohort = list(st.session_state.get("pool_runs") or [])

    if source is None:
        page_header("Export")
        if cohort and scope == "light":
            st.caption(
                f"No single recording loaded — the {len(cohort)}-run cohort is, "
                "though. Per-recording data / figures / report need a recording "
                "(pick one below); the cohort bundle is further down."
            )
        source_loader(
            "Nothing loaded — the single-recording exports (data files, "
            "figures, report) need one.",
            "Pick a finished extraction below, or go to New assessment to load "
            "one.",
            slot="export",
        )
        if cohort and scope == "light":
            _cohort_bundle_section(cohort)
        # Works off finished jobs, not the loaded recording.
        if scope == "light":
            _group_staging_section()
        else:
            _combined_pair_export_section(config)
        return

    result = state.get_runner().run(config)

    if scope == "light":
        page_header("Export", "Data files, publication figures, the native report, and the loaded cohort.")
    else:
        page_header("Export", "Data files, publication figures, and rendered video.")
    recording_switcher("export")

    if not result.ok:
        failed = result.failed_stage
        st.error(f"The pipeline is failing at **{failed.name}** - fix that first.")
        st.caption(failed.error)
        if cohort and scope == "light":
            _cohort_bundle_section(cohort)
        return

    if source.is_demo:
        st.info(
            "The loaded dataset is synthetic. Exports will work, but the contents "
            "are a generated signal."
        )

    if scope == "light":
        tab_data, tab_figures, tab_report = st.tabs(["Data files", "Figures", "PDF report"])
        with tab_data:
            _data_tab(result, source)
        with tab_figures:
            _figures_tab(result)
        with tab_report:
            _report_tab(result, config)
    else:
        tab_data, tab_figures, tab_video, tab_report, tab_video_report, tab_mocap_report = st.tabs(
            ["Data files", "Figures", "Video", "PDF report", "Video report", "MoCap report"]
        )
        with tab_data:
            _data_tab(result, source)
        with tab_figures:
            _figures_tab(result)
        with tab_video:
            _video_tab(result, source)
        with tab_report:
            _report_tab(result, config)
        with tab_video_report:
            _video_report_tab(result, source)
        with tab_mocap_report:
            _mocap_report_tab(result, config, source)

    st.divider()
    reproducibility_panel(
        config, source_name=source.name, model=source.model,
        from_json=True,
        c3d_options=source.c3d_options if source.kind == "c3d" else None,
        key="export",
    )

    if scope == "light":
        if cohort:
            _cohort_bundle_section(cohort)
        _group_staging_section()
    else:
        _combined_pair_export_section(config)


def _cohort_bundle_section(runs: list) -> None:
    """The "Export cohort bundle (zip)" that sits at the foot of every
    cohort scope view (``page_pool``), surfaced on Analysis -> Export too.

    A user who builds a cohort and then clicks Export looks for the
    cohort's export here, not only under the scope view it was built in.
    The full ``page_pool._bundle_export`` widget is reused verbatim (all
    joints/sides -- the per-scope joint filter is a reading aid, the
    bundle is "everything" regardless), so the two entry points cannot
    drift. Analysis renders one scope per run, so ``page_pool``'s own
    ``bundle_*`` widget keys never collide with this call.
    """
    from ..pooling import SAGITTAL_JOINTS
    from .page_pool import _bundle_export

    ok = [r for r in runs if getattr(r, "ok", False)]
    if not ok:
        st.divider()
        st.caption("The loaded cohort has no usable run to export yet.")
        return
    _bundle_export(ok, SAGITTAL_JOINTS, ("left", "right"))


def _group_staging_section() -> None:
    """Name and save a set of finished jobs, for Advanced to recall later.

    Phase 3 of the audit's action plan rebuilds Advanced's "Patient over
    time" and "Two groups" scopes to work from a *named* set of recordings
    picked once, rather than re-selected from scratch on every visit. This
    is the producing half only: pick jobs, name the set, save it here in
    session state (not yet persisted to disk -- a session-scoped group is
    the deliberate default until Phase 3 defines what "recall" needs).
    Nothing reads these groups back yet.
    """
    from ..jobs import DONE, JobManager

    st.divider()
    with st.expander("Prepare a named group for Advanced", expanded=False):
        st.caption(
            "Pick finished recordings and give them a name. Once Advanced's "
            "Patient over time and Two groups scopes are rebuilt to use "
            "this (a later phase), they will recall this exact set directly "
            "instead of re-selecting files by hand each visit."
        )
        jobs = [j for j in JobManager(SETTINGS).list_jobs() if j.status == DONE]
        if not jobs:
            st.caption("No finished extraction yet.")
            return

        labels = {j.ticket: _job_label(j) for j in jobs}
        picked = st.multiselect(
            "Recordings", list(labels), format_func=lambda t: labels[t],
            key="group_staging_picks",
        )
        name = st.text_input(
            "Group name", key="group_staging_name",
            placeholder="e.g. Suivi Patient 004",
        )
        if st.button(
            "Save group", key="group_staging_save",
            disabled=not (picked and name.strip()),
        ):
            groups = dict(st.session_state.get(_GROUPS_KEY, {}))
            groups[name.strip()] = list(picked)
            st.session_state[_GROUPS_KEY] = groups
            st.success(f"Saved '{name.strip()}' ({len(picked)} recording(s)).")

        saved = st.session_state.get(_GROUPS_KEY, {})
        if saved:
            st.markdown("**Saved groups**")
            for group_name, tickets in list(saved.items()):
                c1, c2 = st.columns([4, 1])
                c1.caption(f"**{group_name}** — {len(tickets)} recording(s)")
                if c2.button("Remove", key=f"group_staging_remove_{group_name}"):
                    remaining = dict(st.session_state[_GROUPS_KEY])
                    remaining.pop(group_name, None)
                    st.session_state[_GROUPS_KEY] = remaining
                    st.rerun()


def _combined_pair_export_section(config) -> None:
    """One file for a whole cohort of matched video+C3D pairs.

    Added 2026-09-03, alongside (not instead of) the per-recording exports
    above and page_pool.py's own "Export cohort bundle (zip)" (aggregate
    statistics/figures across a condition-grouped cohort -- a different
    thing: this combines each *pair's* own complete pipeline result, the
    other aggregates *across* a cohort). Reuses the same ready-pair
    detection as the Accuracy vs C3D history picker (jobs.paired_ready_
    groups) so "paired" means the same thing everywhere in the app.

    Each selected pair is re-run through the *current sidebar
    configuration* (not each job's own auto-detected recipe) -- Advanced's
    Export always reads config this way already (state.get_config()), so
    this stays consistent with every other export on this page rather
    than introducing a second recipe rule just for this one feature.

    JSON keeps full fidelity -- every side's complete data/cycles/stats,
    exactly what PipelineRunner.run() returned -- the right choice for
    re-import or an external script. Excel is a compact side-by-side
    summary (spatio-temporal metrics, cycle counts), not a full per-frame
    dump: a workbook is the wrong shape for nested per-frame data, which
    the JSON option already carries in full.
    """
    from ..jobs import DONE, JobManager, paired_ready_groups

    st.divider()
    with st.expander("Export a cohort of video+C3D pairs as one file", expanded=False):
        st.caption(
            "Every selected pair's complete pipeline result (current sidebar "
            "configuration), combined into a single file."
        )
        jobs = [j for j in JobManager(SETTINGS).list_jobs() if j.status == DONE]
        groups = paired_ready_groups(jobs)
        if not groups:
            st.caption("No ready video+C3D pair in Recent jobs yet.")
            return

        labels = {key: f"{key[0]} / {key[1]}" for key in groups}
        picked = st.multiselect(
            "Pairs", list(groups), format_func=lambda key: labels[key],
            key="combined_export_pairs",
        )
        fmt = st.radio(
            "Format", ["JSON (full fidelity)", "Excel (summary)"],
            key="combined_export_format", horizontal=True,
        )
        if st.button(
            "Build combined file", type="primary", key="combined_export_go",
            disabled=not picked,
        ):
            with st.spinner(f"Running the pipeline on {len(picked)} pair(s)..."):
                try:
                    pairs_data = [
                        _combine_pair(key, groups[key], config) for key in picked
                    ]
                except Exception as exc:  # noqa: BLE001 -- shown verbatim, not raised
                    st.error(f"Could not process one pair: {type(exc).__name__}: {exc}")
                    return

            if fmt.startswith("JSON"):
                out = state.workspace().outputs / "cohort_pairs.json"
                _run_export(
                    "Combined pairs (JSON)", out,
                    lambda path: _write_combined_json(pairs_data, path),
                    spinner="Writing the combined file...",
                )
            else:
                out = state.workspace().outputs / "cohort_pairs.xlsx"
                _run_export(
                    "Combined pairs (Excel summary)", out,
                    lambda path: _write_combined_excel(pairs_data, path),
                    spinner="Writing the combined file...",
                )


def _combine_pair(key: tuple[str, str], jobs: list, config) -> dict:
    """Run *config* on both sides of one pair, keyed "video"/"c3d"."""
    from ..jobs import C3D_IMPORT_MODEL_LABEL

    record: dict = {"patient_id": key[0], "condition": key[1]}
    for job in jobs:
        kind = "c3d" if job.model == C3D_IMPORT_MODEL_LABEL else "video"
        path = job.result_path(SETTINGS)
        if path is None:
            continue
        record[kind] = _run_pipeline_on_result_file(path, config)
    return record


def _run_pipeline_on_result_file(path: Path, config) -> dict:
    """{"data":..., "cycles":..., "stats":...} for one saved job result,
    run through *config* -- exactly what PipelineRunner.run() returns,
    kept in memory as plain Python objects until _write_combined_json
    actually serialises the whole combined structure at once.
    """
    from myogait import load_json

    from ..pipeline import PipelineRunner

    raw = load_json(str(path))
    runner = PipelineRunner(raw, source_key=str(path))
    result = runner.run(config)
    return {"data": result.data, "cycles": result.cycles, "stats": result.stats}


def _json_default(obj):
    """json.dumps(default=...) fallback for any numpy scalar/array left in
    cycles/stats -- data itself already goes through myogait.schema.
    save_json elsewhere on this page, but this combined export bundles
    cycles/stats too, which that helper does not cover."""
    import numpy as np

    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _write_combined_json(pairs_data: list[dict], path: Path) -> None:
    import json

    path.write_text(
        json.dumps({"pairs": pairs_data}, indent=2, default=_json_default),
        encoding="utf-8",
    )


def _write_combined_excel(pairs_data: list[dict], path: Path) -> None:
    """One row per (pair, kind): patient/condition, cycle count, and every
    spatio-temporal / step-length metric that side's stats carry -- a
    side-by-side summary, not the full per-frame data (see this section's
    own docstring for why)."""
    import pandas as pd

    rows = []
    for pair in pairs_data:
        for kind in ("video", "c3d"):
            side = pair.get(kind)
            if not side:
                continue
            stats = side.get("stats") or {}
            spatio = stats.get("spatiotemporal") or {}
            step = stats.get("step_length") or {}
            n_cycles = len((side.get("cycles") or {}).get("cycles", []))
            rows.append({
                "Patient": pair["patient_id"],
                "Condition": pair["condition"],
                "Kind": kind,
                "Cycles": n_cycles,
                **{f"spatiotemporal.{k}": v for k, v in spatio.items()},
                **{f"step_length.{k}": v for k, v in step.items()},
            })
    pd.DataFrame(rows).to_excel(path, index=False, sheet_name="Cohort pairs summary")


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


# ── Video report ─────────────────────────────────────────────────────


def _video_report_tab(result: PipelineResult, source: state.Source) -> None:
    st.markdown("**Animated markerless report**")
    st.caption(
        "A narrated video -- skeleton overlay, joint kinematics, spatio-temporal "
        "parameters, range of motion, a virtual accelerometer with its "
        "biomarkers, and a normative-band comparison -- built entirely from the "
        "source video and this run's own results. Carries the Institut de "
        "Myologie mark alongside the app's own identity."
    )
    if source.path is None or source.kind != "video":
        st.caption(
            "Needs the source video on the server. It is available right after an "
            "extraction run from this app, not when a pivot JSON is loaded on its own."
        )
        return
    if not result.n_cycles:
        st.warning("The video report needs at least one segmented cycle.")
        return

    from .. import gait_accelerometry as ga

    sites = [s for s in ga.SITES if ga.site_available(result.data, s)]
    if sites:
        accel_site = st.selectbox(
            "Virtual accelerometer site", sites, format_func=lambda s: ga.SITE_LABEL[s],
            key="vidrep_site",
            help="Which landmark(s) the accelerometer and biomarker segments are built "
            "from. Sacrum matches a waist-worn sensor most closely.",
        )
    else:
        accel_site = None
        st.caption(
            "No site has enough landmark coverage for a virtual accelerometer -- "
            "those two segments will be skipped."
        )

    with st.expander("Optional: reference-cohort validation segment"):
        st.caption(
            "Adds an extra segment comparing this recording's own biomarkers "
            "against a video-vs-IMU reference dataset you supply -- nothing is "
            "bundled with the app, and the file is used for this render only. "
            "CSV columns: `subject`, `biomarker`, `video`, `imu` -- one row per "
            "subject and biomarker (e.g. `S1,Cadence,99.7,92.9`). Recognised "
            "biomarker names (case-insensitive) that also mark this recording's "
            "own value: Cadence, Stride frequency, HF/BF V, IH V, HR V, RMS V, "
            "Regularity, Symmetry -- any other name still plots, just without "
            "that marker."
        )
        cohort_file = st.file_uploader("Reference cohort CSV", type=["csv"], key="vidrep_cohort")

    st.warning(
        "Full frame-by-frame animation -- rendering can take several minutes. "
        "The overlay shows the subject's face and body, so keep it inside the "
        f"lab; it is deleted after {SETTINGS.retention_hours} h like everything "
        "else here."
    )
    if st.button("Render video report", use_container_width=True, key="vidrep_go"):
        from ..video_report import render_video_report

        reference_cohort = None
        if cohort_file is not None:
            import csv
            import io

            text = io.TextIOWrapper(cohort_file, encoding="utf-8")
            reference_cohort = list(csv.DictReader(text))

        out = state.workspace().outputs / "video_report.mp4"
        _run_export(
            "Video report", out,
            lambda path: render_video_report(
                result.data, result.cycles, result.stats, str(source.path), str(path),
                accel_site=accel_site or "sacrum", reference_cohort=reference_cohort,
            ),
            spinner="Rendering the video report - this takes several minutes...",
        )


# ── MoCap PDF report ─────────────────────────────────────────────────


def _mocap_report_tab(result: PipelineResult, config, source: state.Source) -> None:
    st.markdown("**MoCap report**")
    st.caption(
        "Four sections: joint kinematics, methodology & ISB compliance (what was "
        "actually computed for this run, not a generic description), spatio-temporal "
        "parameters, and range of motion with the angle at heel-strike and toe-off. "
        "Works the same for a video or a C3D source. Carries the Institut de "
        "Myologie mark alongside the app's own identity."
    )
    if not result.n_cycles:
        st.warning("The MoCap report needs at least one segmented cycle.")
        return

    if st.button("Generate MoCap report", type="primary", use_container_width=True, key="mocaprep_go"):
        from ..mocap_report import render_mocap_report

        out = state.workspace().outputs / "mocap_report.pdf"
        isb_tier = (source.isb_diagnostics or {}).get("tier")
        _run_export(
            "MoCap report", out,
            lambda path: render_mocap_report(
                result.data, result.cycles, result.stats, config, str(path), isb_tier=isb_tier,
            ),
            spinner="Building the MoCap report...",
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
