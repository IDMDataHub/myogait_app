# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Clinicians and clinical researchers doing gait analysis — physiotherapists, movement-science researchers, and neuromuscular-disease investigators, primarily at Assistmyo · NeuPEL (Neuromuscular Physiology and Evaluation Laboratory) · Institut de Myologie (Hôpital Pitié-Salpêtrière, Paris), and by extension any lab running the same open-source myogait toolkit. Expert users: the interface exposes technical pipeline parameters (Butterworth cutoff, calibration frames, event-detection methods) directly, in the vocabulary of the field, not simplified for a lay audience.

## Product Purpose

An interactive workbench over the [myogait](https://github.com/IDMDataHub/myogait) markerless gait-analysis toolkit. It exists to answer one question well: *what does this parameter actually change?* Every lever myogait exposes downstream of pose extraction is a live control; changing one redraws the figures against the same recording instead of requiring a fresh script run. It reads a video, a pre-extracted pivot JSON, or a `.c3d` marker-based motion-capture trial, and can hand back the exact Python, YAML, or CLI that reproduces the state currently on screen.

Success is a researcher or clinician understanding, in seconds, the consequence of one methodological choice (a filter cutoff, a calibration window, an event-detection method) on a real recording, then being able to reproduce that exact choice outside the app.

## Positioning

Unlike myogait itself (a Python library/CLI with no interface), this is the interactive layer over it — every parameter a control, every result reproducible as code. Unlike a fixed clinical-report generator, nothing here is a black box: bias corrections, calibration methods, and event detectors are all explained at the point of use, including myogait's own documented caveats about when a correction should *not* be trusted (e.g., LASSO bias corrections re-injecting healthy-population curves over pathological gait). This repository implements no gait-analysis algorithms of its own — it drives myogait's, and stays honest about the boundary between the two.

## Operating Context

Used in a research/clinical-research setting, not at the bedside for real-time diagnosis. Inputs arrive as video recordings, C3D motion-capture trials from different labs/protocols (each with its own marker-naming convention), or pre-extracted pivot JSON. Sessions are typically one recording explored at length across many parameter changes, occasionally two recordings compared (the Comparator page) or several sessions tracked over time (the Longitudinal page). Deployed both on a researcher's own laptop and on a shared lab server (systemd + nginx, see `deploy/`).

## Capabilities and Constraints

- Streamlit application; all interaction is server-rendered reruns, not a custom JS frontend — visual work operates within Streamlit's component model plus injected CSS/theme config, not arbitrary HTML/JS.
- Version-gated against the installed myogait/gaitkit: capabilities probed at runtime (`myogait_app/runtime.py`) and controls are disabled-with-a-reason, never hidden, when the installed version lacks a feature.
- Ephemeral by design: uploads, extractions and job tickets are purged on a fixed retention window (24h default); the app is explicit about this in the interface rather than implying persistence.
- No gait-analysis test suite exists (a deliberate, standing project decision, not a gap to fill as part of this design work).
- `arch/` is a private research sandbox explicitly outside this repository and outside the scope of any design or documentation work.

## Brand Commitments

No fixed institutional identity today: `myogait_app/branding.py` is explicitly documented as "deliberately neutral," configurable via environment variables or by editing its dataclass, so any lab can reskin the app without touching code elsewhere (colour and label live only in that one file). This project's current redesign work is choosing a bolder *default* identity while preserving that reconfigurability — not committing the codebase to Assistmyo/NeuPEL/Institut de Myologie branding. No existing logo or literal brand asset from the Institut de Myologie is being incorporated (none was supplied, and their identity is a separate, proprietary system) — the new default identity takes conceptual inspiration only, not literal assets:
- The Institut de Myologie's 2021 visual identity (via its foundation) centers muscle fibres and movement/vibration lines as its core graphic language, under the tagline "Muscler la vie" — health from the cellular scale to the population scale.
- The institute's own website reads as clinical yet accessible: functional, trustworthy, information-first over decorative.
- This maps naturally onto gait analysis' own native visual vocabulary — joint-angle waveforms, gait-cycle curves, motion trajectories are already "movement made into lines" — so the new identity should lean into that resonance rather than import institutional branding wholesale.

## Evidence on Hand

- `myogait_app/branding.py`: an already-validated accessible colour system (OKLCH lightness band, chroma floor, protan/deutan colour-blind separation, contrast — checked in both light and dark mode). This is a confirmed, durable constraint for any new palette, not just descriptive of the old one — see Accessibility below.
- `README.md` and `CLAUDE.md`: document real, load-bearing design decisions already in place (colour carries exactly one entity per chart — side on analysis pages, model/method on the comparator; stage-level caching so changing a late parameter is near-instant; bias corrections default off with the reasoning shown at the control). These are product truth to preserve through the redesign, not decoration to discard.
- No testimonials, case studies, or press exist or should be fabricated for this internal research tool.

## Product Principles

1. Every parameter is a control, and every control explains itself — a disabled or non-default state always states why, in the field's own vocabulary.
2. Colour is meaningful, not decorative: it always encodes one specific entity per chart, never applied for texture alone.
3. Nothing claims permanence it doesn't have — ephemeral storage, version-gated features, and heuristic (not diagnostic) screening are stated plainly at the point of use.
4. The interface stays honest about the boundary between this app and myogait: it drives the toolkit, it does not reimplement it.
5. Reconfigurability is load-bearing, not incidental — any new default identity must remain swappable via `branding.py` alone.

## Accessibility & Inclusion

Hard constraint, carried forward unchanged from the existing implementation: any new palette must clear the same bar `branding.py` already validates — an OKLCH lightness band, a chroma floor, protanopia/deuteranopia separation, and contrast, checked in both light and dark themes. No formal external standard (e.g. RGAA/WCAG) is imposed beyond this; this bar itself is the requirement.
