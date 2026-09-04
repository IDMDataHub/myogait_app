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
   **Open as cohort**, or pick the pair straight from the history selector
   on *Analysis → "Accuracy vs C3D"*.
5. **Read the accuracy.** *Analysis → "Accuracy vs C3D"*: the pair now
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
    (
        "Method validation: status",
        """
**Method validation is frozen while its next scope is discussed with Frédéric
Fer.** The Advanced tab remains available for its existing AIM benchmark and
server-side `.mat` workflow, but it is not the video-versus-C3D accuracy route.
Use **Analysis → Accuracy vs C3D** for paired local video/C3D recordings.
""",
    ),
    (
        "Interpreting ISB reconstruction and its effect on reported bias",
        """
ISB reconstruction is **on by default**, in two places, and it changes
what a "bias" number in this app actually means — not just its precision.

**What it does.** Instead of this app's default sagittal method (angles
projected against the trunk, in 2-D), ISB reconstruction recomputes
hip/knee/ankle from proper ISB pelvis/thigh/shank/foot anatomical frames.
On a C3D/Vicon source this is a genuinely different angle *definition*,
not an upgrade in precision: an internal audit found the two methods
strongly correlated (waveform r ≥ 0.99) but offset by a constant
10–17° on hip/knee, confirmed across the Bath BioCV validation cohort. A
markerless video source has no 3-D markers to reconstruct from, so the
toggle is always a no-op there.

**Why this matters for "accuracy vs C3D".** Any accuracy/bias number that
compares a video's angles against a Vicon/C3D reference is comparing the
video's sagittal-method angles against *whatever the C3D side is
currently computing* — the ISB-reconstructed angle if the toggle is on
for that reference, the sagittal angle if it is off. Turning the C3D
side's toggle on or off therefore moves the reported hip/knee bias by
roughly that same 10–17°, with no change to markerless tracking quality
itself. One measured example: the same trial's hip bias read −6.1° with
ISB on and +4.9° with it off.

**Two separate toggles, not one.** The sidebar's "ISB reconstruction —
this recording" controls the single recording currently open (Pipeline
explorer, Comparator, etc). The Cohort page's own "ISB reconstruction for
Vicon/C3D references — this cohort" controls every recording loaded into
a cohort batch. They are independent settings; changing one does not
change the other, and nothing in the interface flags a mismatch between
the two if they end up set differently for a comparison you are running
across both contexts.

**Practical rule of thumb.** Leave ISB reconstruction on for reading a
Vicon/C3D recording's own kinematics in isolation — it is the more
anatomically correct definition. Turn it off specifically when you want a
video-vs-Vicon accuracy number to reflect pure markerless tracking error,
not also this definitional offset.
""",
    ),
    (
        "When not to enable bias corrections",
        """
Bias corrections (Ankle/Hip/Knee, in the sidebar's "Bias corrections"
section) are the one family of controls in this app that can make a
pathological recording *look healthy* — read this before turning any of
them on.

**What they are.** LASSO regression models fitted on healthy young
adults against a Vicon reference. myogait's own documentation states
they can re-inject a healthy curve exactly where neuromuscular disease
shows itself: swing-phase knee flexion (Duchenne muscular dystrophy,
Charcot-Marie-Tooth), ankle push-off (drop foot), end-stance hip
extension.

**When they are appropriate.** Benchmarking a healthy or near-healthy
reference recording against Vicon — not reading a patient's own gait
pattern.

**When they are not.** Any clinical reading of a recording with a
suspected or known gait pathology. Applying a correction fitted on
healthy adults will pull the reported curve back toward "normal",
masking the exact deviation the assessment exists to detect.

**Deprecated upstream, not yet removed.** myogait deprecated this whole
family in version 0.8.0 (removal planned for 1.0): its own validation
found the *uncorrected* pipeline already at optical-reference level with
a modern pose backbone, and that these corrections degrade rather than
improve accuracy there. `run_pipeline()`, myogait's own recommended entry
point, applies none of them. This app still wires the toggles — a
feature only "planned" for removal is not gone yet — but keeps them off
by default and behind this warning.

**Blocked automatically, not just discouraged, in two cases.** All three
corrections are disabled while ISB reconstruction is active for that
recording (they were fitted on the sagittal method's residuals, not
ISB's pelvis-referenced angles — applying one to the other has no
scientific basis). Hip and knee are additionally disabled until the
M1 perspective correction is enabled (their coefficients were fitted on
perspective-corrected residuals; skipping that step double-counts the
projection).
""",
    ),
]


def render() -> None:
    page_header(
        "Index",
        "What each myogait processing function does (plus this app's own "
        "virtual-accelerometer feature), and short how-to guides for "
        "multi-step workflows. Written from the package's own docstrings "
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
