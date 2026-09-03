"""Tracking one subject across multiple recordings over time.

Distinct from the Comparator: that page holds one recording fixed and
varies either the pipeline configuration or the pose backend. This page
holds the pipeline configuration fixed (the sidebar's current one) and
varies the *recording* -- several sessions of the same subject, spread
over time, run through an identical pipeline so any trend in the plotted
metric is attributable to the subject rather than to a processing
difference between sessions.
"""

from __future__ import annotations

import io
from datetime import date as date_cls
from pathlib import Path

import streamlit as st

from ..pipeline import PipelineRunner
from ..jobs import DONE, JobManager
from ..settings import SETTINGS
from ..runtime import get_runtime
from . import state
from .components import empty_state, page_header

METRIC_LABELS = {
    "cadence": "Cadence (steps/min)",
    "symmetry": "Symmetry index (overall, %)",
    "gps_2d_overall": "GPS-2D overall",
    "gps_2d_left": "GPS-2D left",
    "gps_2d_right": "GPS-2D right",
}


def render() -> None:
    page_header(
        "Longitudinal",
        "Track one metric across several recordings of the same subject over "
        "time, all run through the sidebar's current pipeline configuration.",
    )

    jobs = [job for job in JobManager(SETTINGS).list_jobs() if job.status == DONE and (job.study or {}).get("patient_id")]
    groups = st.session_state.get("prepared_groups") or {}
    if not jobs:
        empty_state(
            "No sessions loaded.",
            "Complete recordings on New assessment first; they will appear here by Patient ID.",
        )
        return

    patient_ids = sorted({str(job.study["patient_id"]) for job in jobs})
    source = st.radio("Session source", ["Patient history", "Prepared group"], horizontal=True)
    if source == "Patient history":
        patient = st.selectbox("Patient ID", patient_ids, key="long_patient")
        candidates = [job for job in jobs if str(job.study.get("patient_id")) == patient]
    else:
        if not groups:
            st.info("No prepared group yet. Create one in Analysis → Export.")
            return
        group_name = st.selectbox("Prepared group", sorted(groups), key="long_prepared_group")
        tickets = set(groups[group_name])
        candidates = [job for job in jobs if job.ticket in tickets]
    selected = st.multiselect(
        "Sessions", candidates, default=candidates, key="long_history_sessions",
        format_func=lambda job: f"{job.video_name} — {(job.study or {}).get('condition', 'no condition')}",
    )
    if not selected:
        return

    dated_jobs = []
    for i, job in enumerate(selected):
        columns = st.columns([3, 1])
        columns[0].text(job.video_name)
        session_date = columns[1].date_input(
            "Date", value=date_cls.today(), key=f"long_date_{job.ticket}",
            label_visibility="collapsed",
        )
        dated_jobs.append((job, session_date))

    if st.button("Run all sessions", type="primary", use_container_width=True):
        _run_sessions(dated_jobs)

    sessions = state.get_longitudinal_sessions()
    if not sessions:
        return

    failed = [s for s in sessions if s.get("error")]
    if failed:
        st.warning(
            f"{len(failed)} session(s) failed and are excluded from the plot: "
            + ", ".join(f"{s['label']} ({s['error']})" for s in failed)
        )
    ok_sessions = [s for s in sessions if not s.get("error")]
    if not ok_sessions:
        return

    st.divider()
    _trend_section(ok_sessions)
    st.divider()
    _pairwise_section(ok_sessions)
    st.divider()
    _report_section(ok_sessions)


# ── Running each session through the shared pipeline ────────────────


def _run_sessions(dated_files) -> None:
    runtime = get_runtime()
    config = state.get_config()
    sessions = []

    with st.spinner(f"Running {len(dated_files)} session(s)..."):
        for job, session_date in dated_files:
            label = job.video_name
            try:
                path = job.result_path(SETTINGS)
                if path is None:
                    raise FileNotFoundError("The completed job result has been purged.")
                from myogait import load_json

                data = load_json(str(path))
                runner = PipelineRunner(data, source_key=f"long-{label}-{session_date}")
                result = runner.run(config)
                if not result.ok:
                    failed_stage = result.failed_stage
                    sessions.append({
                        "label": label, "date": str(session_date),
                        "error": f"{failed_stage.name}: {failed_stage.error}" if failed_stage else "pipeline failed",
                    })
                    continue

                stats = dict(result.stats or {})
                if runtime.has("scores"):
                    from myogait import gait_profile_score_2d

                    stats.update(gait_profile_score_2d(result.cycles))

                sessions.append({
                    "label": label, "date": str(session_date),
                    "data": result.data, "cycles": result.cycles, "stats": stats,
                })
            except Exception as exc:  # noqa: BLE001 - reported, not raised
                sessions.append({
                    "label": label, "date": str(session_date),
                    "error": f"{type(exc).__name__}: {exc}",
                })

    state.set_longitudinal_sessions(sessions)
    st.rerun()


# ── Trend plot ───────────────────────────────────────────────────────


def _trend_section(sessions: list[dict]) -> None:
    runtime = get_runtime()
    if not runtime.has("longitudinal"):
        st.caption(runtime.missing_feature_hint("longitudinal"))
        return

    from myogait import plot_longitudinal

    options = ["cadence", "symmetry"]
    if runtime.has("scores"):
        options += ["gps_2d_overall", "gps_2d_left", "gps_2d_right"]
    metric = st.selectbox(
        "Metric", options, format_func=lambda m: METRIC_LABELS.get(m, m), key="long_metric",
    )

    figure = plot_longitudinal(sessions, metric=metric)
    st.pyplot(figure, use_container_width=True)

    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=200, bbox_inches="tight")
    buffer.seek(0)
    st.download_button(
        "Download trend PNG", buffer.getvalue(), file_name=f"longitudinal_{metric}.png",
        mime="image/png", use_container_width=True,
    )

    import matplotlib.pyplot as plt

    plt.close(figure)


# ── Pairwise comparison ──────────────────────────────────────────────


def _pairwise_section(sessions: list[dict]) -> None:
    st.markdown("**Compare two sessions directly**")
    if len(sessions) < 2:
        st.caption("Needs at least two successfully-run sessions.")
        return

    from myogait import plot_session_comparison

    labels = [f"{s['label']} ({s['date']})" for s in sessions]
    columns = st.columns(2)
    idx_a = columns[0].selectbox("Session A", range(len(sessions)), format_func=lambda i: labels[i], key="long_pair_a")
    idx_b = columns[1].selectbox(
        "Session B", range(len(sessions)),
        index=min(1, len(sessions) - 1), format_func=lambda i: labels[i], key="long_pair_b",
    )
    if idx_a == idx_b:
        st.caption("Pick two different sessions.")
        return

    figure = plot_session_comparison(sessions[idx_a], sessions[idx_b])
    st.pyplot(figure, use_container_width=True)

    from ..mdc import exceeds_mdc, mdc95, pooled_sw

    rows = []
    for joint in ("hip", "knee", "ankle"):
        values_a = _cycle_rom(sessions[idx_a], joint)
        values_b = _cycle_rom(sessions[idx_b], joint)
        if not values_a or not values_b:
            continue
        delta = sum(values_a) / len(values_a) - sum(values_b) / len(values_b)
        threshold = mdc95(pooled_sw([values_a, values_b]), n=min(len(values_a), len(values_b)))
        rows.append({"Parameter": f"{joint.title()} ROM (deg)", "Difference": round(delta, 1),
                     "MDC95": None if threshold is None else round(threshold, 1),
                     "Beyond MDC": "yes" if exceeds_mdc(delta, threshold) else "no / unavailable"})
    if rows:
        st.caption("Change beyond MDC95 is unlikely to be explained by cycle-to-cycle measurement noise.")
        st.dataframe(rows, use_container_width=True, hide_index=True)

    import matplotlib.pyplot as plt

    plt.close(figure)


def _cycle_rom(session: dict, joint: str) -> list[float]:
    """Finite per-cycle ROM values used for the longitudinal MDC estimate."""
    values = []
    for cycle in (session.get("cycles") or {}).get("cycles", []):
        wave = (cycle.get("angles_normalized") or {}).get(joint) or []
        finite = [float(value) for value in wave if isinstance(value, (int, float))]
        if len(finite) >= 2:
            values.append(max(finite) - min(finite))
    return values


# ── PDF report ───────────────────────────────────────────────────────


def _report_section(sessions: list[dict]) -> None:
    runtime = get_runtime()
    if not runtime.has("report"):
        st.caption(runtime.missing_feature_hint("report"))
        return

    st.markdown("**Multi-session PDF report**")
    language = st.selectbox("Language", ["en", "fr"], key="long_rep_lang")

    if not st.button("Generate PDF", use_container_width=True, key="long_rep_go"):
        return

    from myogait import generate_longitudinal_report

    out = state.workspace().outputs / "longitudinal_report.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with st.spinner("Building the report..."):
            generate_longitudinal_report(sessions, str(out), language=language)
    except Exception as exc:
        st.error(f"Report failed: {type(exc).__name__}: {exc}")
        return

    payload = Path(out).read_bytes()
    st.success(f"Ready - {len(payload) / 1024:.0f} KB")
    st.download_button(
        "Download longitudinal_report.pdf", payload, file_name="longitudinal_report.pdf",
        mime="application/pdf", use_container_width=True,
    )
