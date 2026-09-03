"""Analysis -- one guided screen for every scope the loaded data supports.

A clinician thinks in questions, not in page names: one run, one patient over
time, one group, two groups compared, or how the markerless measure agrees
with a C3D reference. This page offers exactly those scopes, tells at a
glance which ones the loaded data can answer (and what is missing for the
others), and keeps the export surface one click away. The scope views
themselves are the existing pages, rendered underneath.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import streamlit as st

from ..pooling import RunResult, analyse_data
from . import page_export, page_longitudinal, page_pipeline, page_pool, state
from .components import page_header

#: Scope labels, in display order.
_RUN = "Trial Explorer"
_PATIENT = "Patient over time"
_GROUP = "One group"
_TWO_GROUPS = "Two groups"
_ACCURACY = "Accuracy vs C3D"
_EXPORT = "Export"
_SCOPES = (_RUN, _PATIENT, _GROUP, _TWO_GROUPS, _ACCURACY, _EXPORT)

#: Older labels stored in a previous session -> their new home.
_LEGACY_SCOPES = {"Single run": _RUN, "Study & conditions": _GROUP}


@dataclass
class _Inventory:
    """What is loaded right now, across the three stores."""

    source_name: str | None = None
    runs: list = field(default_factory=list)
    n_sessions: int = 0

    @property
    def ok_runs(self) -> list:
        return [r for r in self.runs if r.ok]

    @property
    def n_patients(self) -> int:
        return len({r.patient for r in self.ok_runs})

    @property
    def groupings(self) -> set[str]:
        """Distinct group labels, falling back to conditions when untagged."""
        groups = {r.group for r in self.ok_runs if r.group and r.group not in ("", "unknown")}
        if len(groups) >= 2:
            return groups
        return {r.condition for r in self.ok_runs}

    @property
    def n_reference(self) -> int:
        return sum(1 for r in self.ok_runs if r.is_reference)

    @property
    def has_paired_patient(self) -> bool:
        by_patient: dict[str, set] = {}
        for r in self.ok_runs:
            if r.patient != "?":
                by_patient.setdefault(r.patient, set()).add(r.is_reference)
        return any(kinds == {True, False} for kinds in by_patient.values())


def _inventory() -> _Inventory:
    source = state.get_source()
    return _Inventory(
        source_name=source.name if source is not None else None,
        runs=list(st.session_state.get("pool_runs") or []),
        n_sessions=len(state.get_longitudinal_sessions()),
    )


def _default_scope(inv: _Inventory) -> str:
    """The scope matching the data actually loaded (first visit only)."""
    if inv.ok_runs:
        return _TWO_GROUPS if len(inv.groupings) >= 2 else _GROUP
    if inv.n_sessions:
        return _PATIENT
    if inv.source_name:
        return _RUN
    return _GROUP


def _availability(inv: _Inventory) -> dict[str, str]:
    """Scope -> hint when its data is missing (empty string = ready)."""
    hints: dict[str, str] = {s: "" for s in _SCOPES}
    if not inv.source_name:
        hints[_RUN] = "Load a recording on New assessment first."
    if not inv.n_sessions and not inv.source_name:
        hints[_PATIENT] = "Upload several visits of one patient."
    if not inv.ok_runs:
        hints[_GROUP] = "Build a cohort below (upload several pivot JSONs)."
    if len(inv.groupings) < 2:
        hints[_TWO_GROUPS] = "Needs recordings tagged with at least two groups/conditions."
    if not inv.has_paired_patient:
        hints[_ACCURACY] = "Needs a C3D reference sharing a patient with a video recording."
    return hints


def _strip(inv: _Inventory) -> None:
    """One line saying what is loaded -- the fix for 'my file is invisible'."""
    parts = []
    parts.append(f"Loaded: **{inv.source_name}**" if inv.source_name else "Loaded: none")
    if inv.runs:
        parts.append(
            f"Cohort: **{len(inv.ok_runs)} run(s)**, {inv.n_patients} patient(s), "
            f"{len(inv.groupings)} group(s), {inv.n_reference} C3D ref(s)"
        )
    else:
        parts.append("Cohort: empty")
    if inv.n_sessions:
        parts.append(f"Longitudinal: {inv.n_sessions} session(s)")
    st.caption(" • ".join(parts))

    # Bridge: the loaded single source can join the cohort in one click.
    source = state.get_source()
    if source is not None and source.name not in {r.name for r in inv.runs}:
        if st.button(
            "Add loaded source to cohort", key="bridge_source_to_pool",
            help="Analyses the loaded recording with the auto-detected recipe "
                 "and adds it to the cohort batch, so it counts in the group "
                 "views below.",
        ):
            with st.spinner("Analysing the loaded recording..."):
                run: RunResult = analyse_data(
                    source.name, source.data, source_key=source.key,
                )
            st.session_state.setdefault("pool_runs", [])
            st.session_state["pool_runs"] = list(st.session_state["pool_runs"]) + [run]
            st.rerun()


def render() -> None:
    page_header(
        "Analysis",
        "Pick the question: one run, one patient over time, one group, two "
        "groups compared, or accuracy against a C3D reference -- and export "
        "from here. Greyed hints say what data each scope still needs.",
    )

    inv = _inventory()
    _strip(inv)

    # Remap or drop a scope stored by an older app version before the pills
    # widget is created (it raises on out-of-options values).
    stored = st.session_state.get("analysis_scope")
    if stored in _LEGACY_SCOPES:
        st.session_state["analysis_scope"] = _LEGACY_SCOPES[stored]
    elif stored is not None and stored not in _SCOPES:
        st.session_state.pop("analysis_scope", None)

    scope = st.pills(
        "Scope", list(_SCOPES), selection_mode="single",
        default=_default_scope(inv), key="analysis_scope",
        label_visibility="collapsed",
    ) or _default_scope(inv)

    hints = _availability(inv)
    if hints.get(scope):
        st.info(hints[scope])

    st.divider()
    # The Analysis folio is enough; the view below must not add its own.
    st.session_state["_embedded_header"] = True
    if scope == _RUN:
        page_pipeline.render()
    elif scope == _PATIENT:
        page_longitudinal.render()
    elif scope == _TWO_GROUPS:
        page_pool.render(show_header=False, mode="compare")
    elif scope == _ACCURACY:
        page_pool.render(show_header=False, mode="accuracy")
    elif scope == _EXPORT:
        page_export.render()
    else:
        page_pool.render(show_header=False, mode="single")
