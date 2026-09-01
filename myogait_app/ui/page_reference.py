"""A small index of what myogait's processing functions actually do, plus
short how-to guides for the app's own multi-step workflows.

The function glossary is grouped in pipeline order, grounded in the
package's own docstrings (``myogait_app.glossary``), with a status tag
distinguishing what is already usable in this app from what a later phase
will add. The guides above it are this app's own conventions -- things no
myogait docstring can explain because they live in how this UI wires
several pages together. Available with nothing loaded -- it is
documentation, not an analysis screen.
"""

from __future__ import annotations

import streamlit as st

from ..glossary import GROUPS, find
from .components import page_header

_STATUS_BADGE = {
    "phase4": " &middot; :orange[planned - Phase 4]",
    "phase5": " &middot; :orange[planned - Phase 5]",
    "backlog": " &middot; :gray[backlog - not wired]",
}

#: (title, body) pairs, each a self-contained how-to for one multi-step
#: workflow this app supports but no single page fully documents on its
#: own. New entries go at the end; nothing here depends on render order.
_GUIDES: list[tuple[str, str]] = [
    (
        "Compare a video extraction against its Vicon C3D",
        """
A video's markerless kinematics can be checked against a Vicon C3D of the
same walk, once both are tagged with the same **Patient ID** and
**Condition** — the app then pairs and scores them automatically.

1. **Extract or load the video, tagged.** *New assessment → "Video →
   extraction"*: pick the file, fill in **Patient ID** and **Condition**
   in the Study identifiers form (e.g. `P03` / `walk`), then **Start
   extraction**. Wait for the job to reach *done* (progress bar under the
   button, or the *Recent jobs* tab).
2. **Load the matching C3D, tagged the same way.** *New assessment →
   "C3D"*: upload the file, let marker-mapping auto-detection run, then
   fill in the **same** Patient ID and Condition in the Study identifiers
   form here — it must match step 1 exactly; a stray space or a different
   casing keeps the two apart.
3. **Check readiness.** *New assessment → "Recent jobs"*: recordings are
   grouped by Patient ID / Condition. A group with both kinds present
   reads **"ready to compare — video + C3D both present"**; one with only
   one kind says what is missing.
4. **Send the pair to Analysis.** Tick both rows in that group and press
   **Open as cohort** (or **Compare conditions** if the tick-selection
   spans more than one condition).
5. **Read the accuracy.** *Analysis → "Study & conditions"*: the pair now
   appears automatically — a per-joint accuracy table (bias, RMSE,
   waveform *r*, CMC) and mean-curve charts (blue = video, orange =
   Vicon/C3D; solid = left, dashed = right).

**ISB reconstruction changes what "bias" means.** The checkbox at the top
of the Cohort page ("ISB reconstruction for Vicon/C3D references", on by
default) recomputes hip/knee/ankle for the Vicon side from proper ISB
anatomical frames — a different angle *definition* than the sagittal
method the video side always uses, not just added precision. With it on,
hip/knee bias in the table above also reflects that definitional offset
(roughly 10–17° hip, 8–9° knee), not only markerless tracking error. Turn
it off and re-analyse to isolate pure tracking accuracy.

**Untagged recordings are never paired for accuracy, on purpose.**
Anything loaded without a Patient ID/Condition lands in an "unspecified"
group; pairing across it would risk comparing two different patients, so
the accuracy table for that group explains why it is withheld instead of
silently showing numbers.

**Once both are loaded, Advanced's tabs can switch between them too.**
Pipeline explorer, Comparator's Sweep tab, Export, and Method validation's
Vicon tab each show a compact **"Recording: …"** picker once two or more
finished recordings exist, so exploring the C3D instead of the video (or
back) does not require a trip to New assessment — though it switches the
one recording every Advanced tab reads, not an independent choice per tab.

**Current limitation.** A pre-extracted video pivot loaded through the
"Pivot JSON" tab (rather than run as a fresh extraction) has no Study
identifiers form yet and is not listed in Recent jobs — only a live video
extraction or a C3D import register for pairing today.
""",
    ),
]


def render() -> None:
    page_header(
        "Index",
        "What each myogait processing function does, plus short how-to guides "
        "for multi-step workflows. Written from the package's own docstrings "
        "and this app's own conventions.",
    )

    _guides_section()
    st.divider()

    query = st.text_input(
        "Search", placeholder="e.g. butterworth, GVS, femur, c3d, perspective"
    )

    if query.strip():
        matches = find(query)
        st.caption(f"{len(matches)} match(es).")
        if not matches:
            return
        last_group = None
        for group, entry in matches:
            if group != last_group:
                st.markdown(f"**{group}**")
                last_group = group
            _entry_row(entry)
        return

    for title, entries in GROUPS:
        with st.expander(title, expanded=False):
            for entry in entries:
                _entry_row(entry)


def _guides_section() -> None:
    st.markdown("**Guides**")
    for title, body in _GUIDES:
        with st.expander(title, expanded=False):
            st.markdown(body)


def _entry_row(entry) -> None:
    badge = _STATUS_BADGE.get(entry.status, "")
    st.markdown(f"`{entry.name}`{badge}")
    caption = entry.summary
    if entry.citation:
        caption += f"  _{entry.citation}_"
    st.caption(caption)
