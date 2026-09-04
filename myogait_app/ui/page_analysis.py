"""Analysis -- the clinical read: one trial, the cohort at a glance,
accuracy against a C3D reference, and the export surface.

A clinician thinks in questions, not in page names. This screen answers the
four that belong on the clinical path; the deeper cohort work -- one
patient over time, one group's statistics, two groups compared -- moved to
**Advanced**, which is now the fullest analysis screen (audit action plan,
chantier B). The scope views themselves are the existing pages, rendered
underneath.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import streamlit as st

from ..pooling import RunResult, analyse_data
from . import page_export, page_pipeline, page_pool, state
from .components import page_header

#: Scope labels, in display order.
_RUN = "Trial Explorer"
_MARKERBASED = "Markerbased vs Monocular"
_ACCURACY = "Accuracy vs C3D"
_EXPORT = "Export"
_SCOPES = (_RUN, _MARKERBASED, _ACCURACY, _EXPORT)

#: Older labels stored in a previous session -> their new home. "One
#: group" / "Two groups" / "Patient over time" / "Study & conditions"
#: are no longer Analysis scopes (they are Advanced tabs now); a stored
#: value naming one of them simply falls through to the data-aware
#: default below.
_LEGACY_SCOPES = {"Single run": _RUN}


@dataclass
class _Inventory:
    """What is loaded right now, across the source and cohort stores."""

    source_name: str | None = None
    runs: list = field(default_factory=list)

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
    )


def _default_scope(inv: _Inventory) -> str:
    """The scope matching the data actually loaded (first visit only)."""
    if inv.ok_runs:
        return _MARKERBASED
    if inv.source_name:
        return _RUN
    return _RUN


def _availability(inv: _Inventory) -> dict[str, str]:
    """Scope -> hint when its data is missing (empty string = ready)."""
    hints: dict[str, str] = {s: "" for s in _SCOPES}
    if not inv.source_name:
        hints[_RUN] = "Load a recording on New assessment first."
    if not inv.ok_runs:
        hints[_MARKERBASED] = "Build a cohort below (upload several pivot JSONs)."
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
    st.caption(" • ".join(parts))

    # Bridge: the loaded single source can join the cohort in one click.
    source = state.get_source()
    if source is not None and source.name not in {r.name for r in inv.runs}:
        if st.button(
            "Add loaded source to cohort", key="bridge_source_to_pool",
            help="Analyses the loaded recording with the auto-detected recipe "
                 "and adds it to the cohort batch, so it counts in the "
                 "Markerbased vs Monocular and Accuracy views.",
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
        "Pick the question: one trial, the cohort at a glance, accuracy "
        "against a C3D reference, or export -- one patient over time and "
        "group statistics are on Advanced now. Greyed hints say what data "
        "each scope still needs.",
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
    elif scope == _MARKERBASED:
        page_pool.render(show_header=False, mode="markerbased")
    elif scope == _ACCURACY:
        page_pool.render(show_header=False, mode="accuracy")
    else:
        page_export.render(mode="analysis")
