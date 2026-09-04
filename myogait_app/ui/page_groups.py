"""Advanced -> Groups -> Two groups: two named groups, compared.

The plan's B3 (audit action plan, chantier B): import two groups
*independently* -- each from a prepared group, job history, or uploaded
pivots -- name them, and read every parameter they share side by side.
For each shared parameter: descriptive statistics per group and one
adaptive difference test (Welch's t or Mann-Whitney by a normality check,
with a matching effect size). Many parameters tested at once is flagged,
not silently corrected -- the reader picks the correction. A visual
control underneath overlays any one recording on its group's mean band,
with a checkbox to drop it from the analysis while keeping it in the
imported group.

Distinct from **One group** (``page_pool`` mode ``"single"``), which reads
the single cohort loaded there; nothing on this screen touches that
cohort.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from ..charts import kinematics as K
from ..pooling import load_runs, pool_cycles
from ..reliability import compare_two_groups, significant_count
from .components import chart, is_dark, page_header
from .group_sources import group_source_picker

_STATE = "groups_two"
_EXCLUDED = "groups_excluded"
_DEFAULT_NAMES = ("Group 1", "Group 2")


def render() -> None:
    page_header(
        "Two groups",
        "Two independently imported groups, compared parameter by parameter "
        "with an adaptive difference test.",
    )

    name_a, paths_a, name_b, paths_b = _import_zones()

    ready = bool(paths_a and paths_b)
    if st.button(
        f"Compare {len(paths_a)} vs {len(paths_b)} recording(s)" if ready else "Compare",
        type="primary", use_container_width=True, disabled=not ready, key="groups_go",
    ):
        stamp = (tuple(str(p) for p in paths_a), tuple(str(p) for p in paths_b))
        with st.spinner("Running both groups through the pipeline..."):
            st.session_state[_STATE] = {
                "stamp": stamp,
                "names": (name_a, name_b),
                "a": load_runs(list(paths_a)),
                "b": load_runs(list(paths_b)),
            }

    stored = st.session_state.get(_STATE)
    if not stored:
        st.info("Pick a source for each group above, then press Compare.")
        return

    name_a, name_b = stored.get("names", _DEFAULT_NAMES)
    _report_failures(list(stored["a"]) + list(stored["b"]))

    all_a = [r for r in stored["a"] if r.ok]
    all_b = [r for r in stored["b"] if r.ok]
    if not all_a or not all_b:
        st.warning("At least one group produced no usable recording.")
        return

    excluded = set(st.session_state.get(_EXCLUDED) or [])
    runs_a = [r for r in all_a if _rid(r) not in excluded]
    runs_b = [r for r in all_b if _rid(r) not in excluded]
    if not runs_a or not runs_b:
        st.warning(
            "Every recording in one group is currently excluded -- clear an "
            "exclusion below to compare."
        )
        return

    n_excluded = sum(1 for r in all_a + all_b if _rid(r) in excluded)
    st.caption(
        f"**{name_a}** — {len(runs_a)} recording(s), "
        f"{len({r.patient for r in runs_a})} patient(s). "
        f"**{name_b}** — {len(runs_b)} recording(s), "
        f"{len({r.patient for r in runs_b})} patient(s)."
        + (f" {n_excluded} recording(s) excluded from the statistics."
           if n_excluded else "")
    )

    rows = compare_two_groups(runs_a, runs_b)
    _comparison_table(rows, name_a, name_b)
    st.divider()
    _individual_control(all_a, all_b, name_a, name_b, excluded)


# ── Import ───────────────────────────────────────────────────────────


def _import_zones() -> tuple[str, list, str, list]:
    col_a, col_b = st.columns(2)
    with col_a:
        name_a = st.text_input("Name", _DEFAULT_NAMES[0], key="groups_name_a").strip() \
            or _DEFAULT_NAMES[0]
        st.caption("Source")
        paths_a = group_source_picker("groups_a")
    with col_b:
        name_b = st.text_input("Name", _DEFAULT_NAMES[1], key="groups_name_b").strip() \
            or _DEFAULT_NAMES[1]
        st.caption("Source")
        paths_b = group_source_picker("groups_b")
    if name_a == name_b:
        name_b = f"{name_b} (2)"
    return name_a, paths_a, name_b, paths_b


def _report_failures(runs: list) -> None:
    failures = [r for r in runs if not r.ok]
    if not failures:
        return
    with st.expander(f"{len(failures)} recording(s) could not be analysed", expanded=False):
        for run in failures:
            st.caption(f"**{run.name}** — {run.error}")


# ── Comparison ───────────────────────────────────────────────────────


def _comparison_table(rows: list[dict], name_a: str, name_b: str) -> None:
    if not rows:
        st.info("The two groups share no parameter with data on both sides.")
        return

    hits, tested = significant_count(rows)
    if tested > 1:
        st.warning(
            f"{tested} parameters compared at once, {hits} with p < 0.05. "
            "P-values are **not** corrected for multiple comparisons — with "
            f"{tested} tests, roughly {0.05 * tested:.1f} would clear 0.05 by "
            "chance alone. Apply a correction (Bonferroni: significant below "
            f"{0.05 / tested:.4f}; or Holm / Benjamini-Hochberg) before reading "
            "any single p as confirmatory."
        )

    table = []
    for row in rows:
        table.append({
            "Parameter": _pretty(row["parameter"]),
            f"{name_a} (n={row['n_a']})": _mean_sd(row["mean_a"], row["sd_a"]),
            f"{name_b} (n={row['n_b']})": _mean_sd(row["mean_b"], row["sd_b"]),
            "Δ (A−B)": _round(row["delta"]),
            "Test": row["test"] or "—",
            "p": _round(row["p"], 4),
            f"Effect ({row['effect_name']})" if row["effect_name"] else "Effect":
                _round(row["effect"], 3),
        })
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)
    st.caption(
        "Test picked per parameter: **Welch t** when Shapiro-Wilk does not "
        "reject normality in both groups (n ≥ 3), **Mann-Whitney U** otherwise. "
        "Effect size follows the test — Hedges g (standardised mean difference, "
        "bias-corrected) or rank-biserial r. Each recording contributes one "
        "value; repeated recordings of a patient are not accounted for, so read "
        "p descriptively when a group has several recordings per patient."
    )


# ── Visual control ───────────────────────────────────────────────────


def _individual_control(
    all_a: list, all_b: list, name_a: str, name_b: str, excluded: set,
) -> None:
    st.markdown("**Visual control — one recording against its group**")
    st.caption(
        "Overlay a single recording's mean cycle on its group's mean ± SD "
        "band. Exclude it to drop it from the statistics above while keeping "
        "it in the imported group."
    )

    group_choice = st.radio(
        "Group", [name_a, name_b], horizontal=True, key="groups_vc_group",
    )
    runs = all_a if group_choice == name_a else all_b
    if not runs:
        st.caption("This group has no usable recording.")
        return

    by_rid = {_rid(r): r for r in runs}
    names = {rid: f"{run.patient} / {run.run}" for rid, run in by_rid.items()}
    labels = {rid: names[rid] + (" — excluded" if rid in excluded else "")
              for rid in by_rid}
    picked_rid = st.selectbox(
        "Recording", list(by_rid), format_func=lambda rid: labels[rid],
        key="groups_vc_run",
    )
    picked = by_rid[picked_rid]

    joints = _shared_joints(runs)
    joint = st.selectbox(
        "Joint", joints, format_func=lambda j: K.JOINT_LABELS.get(j, j.title()),
        key="groups_vc_joint",
    ) if joints else None

    checkbox_key = f"groups_vc_exclude_{picked_rid}"
    st.checkbox(
        f"Exclude **{names[picked_rid]}** from the statistics",
        value=picked_rid in excluded, key=checkbox_key,
        on_change=_apply_exclusion, args=(picked_rid, checkbox_key),
    )

    if joint is None:
        st.caption("No joint has a usable cycle in this group.")
        return

    kept = [r for r in runs if _rid(r) not in excluded] or runs
    chart(
        K.group_vs_individual_overlay(
            pool_cycles(kept), pool_cycles([picked]), joint=joint,
            group_label=group_choice, individual_label=names[picked_rid],
            dark=is_dark(),
        ),
        key=f"groups_vc_{joint}",
    )


def _shared_joints(runs: list) -> list[str]:
    """The sagittal joints at least one recording in the group actually
    produced a cycle for. ISB DOF (abd/add, rotation) trends are the phased
    B1/B2 extension, not attempted for the visual control yet."""
    summaries = [(r.cycles or {}).get("summary") or {} for r in runs]
    return [
        joint for joint in K.SAGITTAL_JOINTS
        if any((summary.get(side) or {}).get(f"{joint}_mean")
               for summary in summaries for side in ("left", "right"))
    ]


# ── Formatting ───────────────────────────────────────────────────────


def _rid(run) -> str:
    """Stable per-recording id for exclusion -- the source path/key, not the
    bare filename (several job-history recordings are all ``result.json``)."""
    return run.source_key or run.name


def _apply_exclusion(rid: str, checkbox_key: str) -> None:
    """Checkbox ``on_change``: fold this recording in/out of ``_EXCLUDED``.

    A callback (not an inline reconcile) so the single source of truth is
    ``_EXCLUDED`` -- an inline ``value=``/session-state compare fights
    Streamlit ignoring ``value=`` once a keyed checkbox exists, which
    silently un-excluded on the next rerun.
    """
    excluded = set(st.session_state.get(_EXCLUDED) or [])
    if st.session_state.get(checkbox_key):
        excluded.add(rid)
    else:
        excluded.discard(rid)
    st.session_state[_EXCLUDED] = sorted(excluded)


def _pretty(parameter: str) -> str:
    return parameter.replace("_", " ").replace(" rom", " ROM").strip().capitalize()


def _mean_sd(mean, sd) -> str:
    if mean is None:
        return "—"
    return f"{mean:.2f}" if sd is None else f"{mean:.2f} ± {sd:.2f}"


def _round(value, ndigits: int = 2):
    return round(float(value), ndigits) if isinstance(value, (int, float)) and np.isfinite(value) else None
