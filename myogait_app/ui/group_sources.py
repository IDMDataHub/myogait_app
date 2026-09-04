"""Pick a set of recordings for a group view.

Shared by Advanced's **One group** (B2) and **Two groups** (B3): both need
to gather a group of recordings the same three ways -- a group prepared on
the Export screen, an ad-hoc pick from job history, or uploaded pivot
JSONs -- and both then hand the resulting paths to
``pooling.load_runs``. Keeping the picker here means the two screens stay
in step (audit action plan, chantier B).
"""

from __future__ import annotations

import streamlit as st

from ..settings import SETTINGS
from ..storage import store_uploaded_file
from . import state

_PREPARED = "Prepared group"
_HISTORY = "Job history"
_UPLOAD = "Upload pivots"


def group_source_picker(key: str, *, label: str = "Source") -> list:
    """Return the pivot paths for one group -- empty until the user picks.

    *key* namespaces every widget so two pickers (Two groups) never collide.
    """
    from ..jobs import DONE, JobManager

    jobs = [job for job in JobManager(SETTINGS).list_jobs() if job.status == DONE]
    prepared = st.session_state.get("prepared_groups") or {}

    options = [_HISTORY, _UPLOAD]
    if prepared:
        options.insert(0, _PREPARED)
    source = st.radio(
        label, options, horizontal=True, key=f"{key}_source",
        label_visibility="collapsed",
    )

    if source == _PREPARED:
        name = st.selectbox(
            "Prepared group", sorted(prepared), key=f"{key}_prepared",
        )
        tickets = set(prepared.get(name) or [])
        return _paths(job for job in jobs if job.ticket in tickets)

    if source == _UPLOAD:
        uploads = st.file_uploader(
            "Pivot JSONs", type=["json"], accept_multiple_files=True,
            key=f"{key}_upload",
        )
        if not uploads:
            return []
        workspace = state.workspace()
        return [store_uploaded_file(workspace, up, up.name) for up in uploads]

    # Job history.
    if not jobs:
        st.caption("No finished recording on this machine yet.")
        return []
    by_ticket = {job.ticket: job for job in jobs}
    picked = st.multiselect(
        "Recordings", list(by_ticket),
        format_func=lambda ticket: _job_label(by_ticket[ticket]),
        key=f"{key}_history",
    )
    return _paths(by_ticket[ticket] for ticket in picked)


def _job_label(job) -> str:
    study = job.study or {}
    tags = " / ".join(
        str(study[key]) for key in ("patient_id", "condition") if study.get(key)
    )
    return f"{job.video_name} ({job.model})" + (f" -- {tags}" if tags else "")


def _paths(jobs) -> list:
    out = []
    for job in jobs:
        path = job.result_path(SETTINGS)
        if path is not None:
            out.append(path)
    return out
