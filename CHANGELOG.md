# Changelog

All notable changes to this project, grouped by date. Newest first. Every
entry below is attributed to its actual author; where that is not stated, it
is Romain Feigean.

## Unreleased — 2026-09-04 (Romain Feigean)

**B1/B2 extension — accelerometry + ISB DOF pooled into trends, not just
single-trial views.** The plan's phased scope (open point 1): v1 shipped
sagittal joint ROM + spatiotemporal only; this adds the rest wherever a
recording actually carries it, without touching what does not.

- **`reliability.scalars_from(cycles, stats, joints)`** — the granular core
  `_run_scalars` now delegates to, callable straight from a session dict
  (not only a `RunResult`). Adds `ISB_DOF_CYCLE_KEYS` (the abd/add + rotation
  ROM `pipeline._enrich_cycles_with_isb_dof` writes) to every scalar
  extraction — `biomarker_table`, `parameter_descriptives`, `compare_
  two_groups` and `group_comparison_biomarkers` all pick them up for free
  when a marker (C3D) source carried them; self-gating, so a video-only
  cohort is unaffected.
- **Advanced → Patient over time — "All parameters over time"** (new
  section): every scalar biomarker across the loaded sessions, one at a
  time, plotted against session order — not only myogait's own fixed
  cadence / symmetry / GPS-2D set. A joint-ROM parameter's trend shows an
  MDC95 band (pooled from each session's own within-session cycle spread)
  around the first session, so a later point outside it reads as a real
  change rather than noise; the two-session pairwise MDC table gains the
  same ISB DOF rows.
- **Advanced → Groups → One group — pooled cycle curves** now also plot the
  ISB abd/add + rotation DOF when a run in the condition carried them,
  alongside the sagittal flex/ext joints (previously `SAGITTAL_JOINTS`-only
  regardless of what was loaded).

**Advanced → Groups rebuilt to the refonte plan (B2/B3).** The 0.9.0 entry
below described a four-tab Analysis with the group screens moved to Advanced;
the code kept them as Analysis scopes. That relocation is now real, and the
two group screens are rebuilt rather than relabelled.

- **Two groups** (new `page_groups.py`, plan B3) — two groups imported
  *independently*, each named and fed from a prepared group, job history, or
  uploaded pivots (not one loaded cohort split by condition). Per shared
  parameter: n / mean / SD per group, the difference, and one adaptive test —
  Welch's t when a Shapiro-Wilk check keeps normality in both groups,
  Mann-Whitney U otherwise — with a matching effect size (Hedges g or
  rank-biserial r). Many parameters at once raises an explicit
  multiple-comparison warning with the Bonferroni threshold; no correction is
  imposed. A visual control overlays any one recording on its group's mean ± SD
  band, with a checkbox that drops it from the statistics while keeping it in
  the imported group.
- **One group** (plan B2) — the per-condition descriptive table widens from
  spatiotemporal + sagittal ROM to every scalar biomarker a recording yields
  (`pooling.parameter_descriptives`), and the cohort can now be imported from a
  prepared group or straight from job history, not only by file upload.
- **Advanced → Groups** is two real sub-tabs (One group / Two groups) instead
  of an inner radio — possible now that Two groups has its own widget keys, so
  `page_pool` is still rendered only once per run.
- **`reliability.group_difference` / `compare_two_groups` / `significant_count`**
  — the adaptive-test core, Streamlit-free and unit-tested. `RunResult` gains
  `source_key`, a stable per-recording identity (the bare filename collides —
  every job-history recording is stored as `result.json`).

**Phase 4 — cleanup & docs (audit C4 / C5 / C10 / C13).**

- **C4** — `page_data.render()` is gone (the old five-tab "Data" page; nothing
  routed to it since New assessment took over). `_PAGE_META["Cohort"]` removed,
  `"One group"` / `"Two groups"` added. `page_analysis._LEGACY_SCOPES` removed —
  a departed scope label is just dropped now, landing on the same data-aware
  default it used to be remapped to.
- **C10 / C13** — minimal cross-references between the separate import zones
  (New assessment ↔ Advanced → Groups / Patient over time) and between the two
  Export locations (Analysis' clinical subset ↔ Advanced's full surface).
- **C5** — README, TUTORIAL and CLAUDE.md updated to the four-screen IA
  (New assessment / Analysis / Advanced / Index) instead of the old flat page
  list; the two stale claims the audit flagged are corrected (`myogait` is on
  PyPI now; `test_cohort_smoke.py` passes `default_timeout=60`). Stale
  "Analysis → Study & conditions" / "the Cohort page" strings in code comments
  and user-facing captions repointed.

## 0.9.0 — 2026-09-03 (Frédéric Fer)

**Analysis / Advanced restructure + audit remediation (Phases 1-3).** Acts on
the 2 September audit: Analysis becomes the analysis entry point (four tabs);
Advanced becomes the fullest screen (cohorts, group stats, search).

- **Analysis** — `Single run` renamed to **Trial Explorer** (the full Pipeline
  explorer, now living only here; the Advanced duplicate is removed, UX-01).
  **Accuracy vs C3D** now filters to real video+C3D pairs and can pick completed
  pairs from job history instead of manual re-entry (UX-02, UX-04). **Export**
  slimmed to Data files / Figures / native PDF report, plus a *Prepare groups
  for Advanced* section that saves named job selections (UX-06).
- **Advanced** — **Patient over time** driven from job history with MDC-based
  change flagging across the available parameters (B1). **One group**
  descriptive statistics per parameter (B2). **Two groups** with a retainable
  individual-exclusion control and comparison stats (B3). Comparator clarifies
  that a sweep re-runs the pipeline (DOC-05); Method validation frozen (note).
- **Reliability / clinical safety** — the silent ISB→sagittal fallback is now
  surfaced in the UI, not just logged (DEV-04); the two accelerometry-style
  calculations carry a non-comparability warning (DEV-01/DOC-01); the two ISB
  toggles are relabelled and cross-referenced (UX-03).
- **UI density** — the Trial Explorer sidebar gains an *Expert settings* switch
  that keeps the advanced pipeline sections collapsed by default without hiding
  any control (UX-07).
- **Robustness / tests / docs** — per-session pose-backend detection cache
  (DEV-05); upload-limit sync guard (DEV-07); dedicated export/page_data tests
  (DEV-02/03); glossary + ISB/bias/navigation guides (DOC-03/04); metadata
  carried across the two New-assessment forms (UX-04). Ships the previously
  unreleased Video / MoCap Export reports (below).

## Unreleased — 2026-09-01 (Romain Feigean)

- **Two new Export reports, both carrying the Institut de Myologie mark
  alongside the app's own identity.**
  - **`video_report.py`** -- a narrated, five-segment animated MP4 (skeleton
    overlay, joint kinematics, spatio-temporal parameters, range of motion,
    normative-band comparison), modelled on an external pedagogical script's
    storyboard but rebuilt on this app's own validated palette/type
    (`branding.py`, bundled JetBrains Mono, OFL-licensed) instead of a
    second parallel identity, and on this app's own computed results
    instead of an IMU/virtual-accelerometer pipeline nothing here produces.
    Full frame-by-frame animation fidelity, by request -- ~56 s of output,
    several minutes to render, the Export tab says so up front.
  - **`mocap_report.py`** -- a 4-section PDF (kinematics; methodology + ISB
    compliance, generated from the actual `PipelineConfig` that ran, not a
    fixed template; spatio-temporal parameters with a "how it's computed"
    column; range of motion plus the angle at heel-strike and toe-off),
    source-kind-agnostic (video or C3D).
  - Both wired into `Advanced -> Export` as new tabs ("Video report",
    "MoCap report").
- **Four real bugs found and fixed while testing the above, each with a
  regression test that reproduces the exact failure before the fix:**
  - `storage.write_json_atomic`'s temp-file rename could raise
    `PermissionError`/WinError 5 on Windows when a poller had the
    destination momentarily open for reading -- a previously *known and
    accepted* race (a test skip's own comment said so) rather than an
    unknown one. Now retries (up to 40x/50ms) instead of crashing; the
    stale Windows test skip is removed and the test itself fixed to
    tolerate `read_json`'s own documented "may return None during a race"
    contract instead of asserting a stronger guarantee than the system
    actually makes.
  - A video's `Source.kind` was always `"json"` after being loaded back
    (tick a finished job -> Analyse, or the recording switcher) -- neither
    of the two places that ever build a loaded `Source` set `kind="video"`,
    so `source.kind == "video"` (what the skeleton-overlay export and the
    new video report both gate on) was unreachable through the normal
    workflow. `state.resolve_pivot_kind_and_path` now upgrades to
    `kind="video"` when the pivot's own recorded `meta.video_path` still
    resolves on this machine.
  - `components._to_new_assessment`'s "Go to New assessment" button set
    `st.session_state["nav_page"]` directly -- illegal once that widget
    (the sidebar's page pills) has already run earlier in the same script,
    raising `StreamlitAPIException`. Now sets a pending-navigation key that
    `app.main()` seeds `nav_page` from before the pills widget exists in
    the *next* run, the one point such a write is allowed.
  - `hrnet`'s live availability trusted `myogait.models.available_models()`
    reporting it importable from `torch` alone -- but the installed
    myogait's own `HRNETPoseExtractor.setup()` unconditionally needs MMPose
    (confirmed by reading the source, not assumed), which needs `mmcv`, an
    OpenMMLab compiled extension with no prebuilt wheel for every Python/
    torch combination -- sending a user into a job that failed mid-run with
    a raw `ImportError` instead of the control simply being unavailable
    up front. `BackendInfo.is_available` no longer trusts myogait's signal
    for this one backend; the install hint explains why installing MMPose
    is not practically possible either (`chumpy`, unmaintained, breaks
    under any modern pip's PEP 517 build isolation) rather than suggesting
    a doomed command.
- **Literal virtual-accelerometer pipeline, ported from an external research
  script with two exclusions -- three more `video_report.py` segments, a new
  `gait_accelerometry.py` module, and a new Advanced tab.** The user supplied
  the script (`gait_biomarkers.py`, "Pipeline Equimetrix enrichi", 2024, an M2
  project) and its validation-cohort CSVs after the first pass above shipped
  without them; explicit go-ahead was sought and given for what could be
  ported, per file (see below).
  - **`gait_accelerometry.py`** (new, Streamlit-free, unit-tested): a virtual
    accelerometer from a pivot's own landmark trajectories -- site position ->
    torso-length normalisation -> Savitzky-Golay second derivative ->
    resampled to 100 Hz, at a choice of sacrum/lumbar/sternum/head -- plus the
    literature-cited biomarker family (temporal parameters; Moe-Nilssen
    regularity/symmetry; Harmonic Ratio; spectral analysis; Sample/
    Approximate Entropy; RMS variability; statistical moments), with
    published reference ranges and a clinical interpretation. Two things
    from the source script were deliberately left out of the port: its
    `_locolike`/"RDM" regularity indices, marked proprietary in the script's
    own comments (publishing them was never confirmed); and its private
    8-subject video-vs-IMU validation cohort -- no data or numeric result
    derived from that cohort ships in this module or this repository.
  - **`video_report.py`** grows from 5 to 7 segments by default (virtual
    accelerometer, biomarkers) and to 8 when the caller supplies a
    reference-cohort CSV for that one render only (`render_video_report`'s
    new `reference_cohort` parameter -- never bundled with the app, parsed
    and discarded after the render). `page_export.py`'s Video report tab
    gained a matching optional file uploader (documented `subject,biomarker,
    video,imu` schema) and an accelerometer-site picker. The segment
    timeline is now built by `_timeline(has_cohort)` rather than a fixed
    module-level tuple, so `draw_stepper` and the summary segment work at
    whichever absolute position a segment lands.
  - **New Advanced tab, "Accelerometry biomarkers"**: the same computation
    as a standing per-category table (value, published reference range,
    interpretation), reachable for any loaded video source without
    rendering the video report.
  - **Known, disclosed overlap, not reconciled.** `reliability.
    accelerometric_scalars` (0.8.0, Frédéric Fer) already computes a
    smaller, simpler version of the same idea -- RMS, an index of
    harmonicity, an LF/HF power ratio, from the pelvis centre by plain
    double-differentiation, no torso normalisation, no resampling -- for
    the cohort ICC/group-comparison tables. Left untouched: its numbers
    already feed shipped, tested statistics, and swapping its computation
    for this module's is a real behaviour change needing its own
    validation pass, the same caution this project's ISB-reconstruction
    reconciliation needed. **Decision (Romain Feigean): `gait_
    accelerometry.py` stays in `main` as-is.** An earlier plan to have
    Frédéric Fer arbitrate whether to unify the two (with a stated leaning
    toward keeping his simpler implementation) was withdrawn before it
    reached him. The two compute different numbers for a similar-sounding
    quantity; unifying them remains open and undecided, not blocking.
  - Not attempted: literal reproduction of the original pedagogical video's
    exact subject. Its raw source video and Sapiens-2 JSON extraction were
    never supplied, so this capability was built and tested against the
    app's own demo/synthetic data and is fully generic (any video source),
    not validated against that one specific recording.
- 269 tests passing (25 new), ruff clean, 73% coverage (floor 60%).

## [0.8.0] — 2026-08-31

Guided Analysis, clinician-grade cohort statistics and a full export
(Frédéric Fer), plus video-vs-C3D accuracy pairing (Romain Feigean).
Requires `myogait >= 0.8.7`.

### Guided Analysis, cohort statistics and export (Frédéric Fer)

- **Guided Analysis page.** One scope selector matching the question asked:
  Single run / Patient over time / One group / Two groups / Accuracy vs C3D /
  Export. An inventory strip states what is loaded so a file is never invisible;
  each scope hints what data it needs; a one-click bridge adds the loaded source
  to the cohort; the page opens on the scope matching the loaded data.
- **Cohort batch config + re-analysis.** Recipe choice (auto-detect per
  recording -- re-enabled -- or the shared sidebar configuration) plus a
  "Re-analyse N recordings" button: change the analysis of many JSONs at once.
  A joints/sides selection is honoured by every cohort view.
- **Reliability statistics (`reliability` module).** ICC(2,1) validity,
  ICC(3,1) test-retest (+ ICC(2,k)) and Bland-Altman, locked against the
  published Shrout & Fleiss example; per-run biomarker table; group comparison
  (n, mean±SD, Hedges g, Welch p); accelerometry-family biomarkers from the
  pelvis trajectory (RMS acceleration, index of harmonicity, LF/HF ratio --
  image-normalised units, stated as such) plus the harmonic ratio.
- **Cohort figures + export bundle.** Bland-Altman plots and between-group
  boxplots on screen; an "Export cohort bundle (zip)" packaging every table
  (per-patient per-cycle, overview, agreement, MDC, biomarkers, ICC
  validity/test-retest, Bland-Altman) as CSV + one Excel workbook, plus
  print-grade figures at a chosen DPI, with provenance.

### Video-vs-C3D accuracy pairing (Romain Feigean)

- **Video-vs-C3D accuracy pairing: the documented workflow did not actually
  work, and the numbers were silently ambiguous when it did.** Verified
  end-to-end against real Bath BioCV data (P03) before and after each fix.
  - **The C3D tab had no way to tag a Patient ID/Condition at all**
    (`_study_form` only ever ran in the video-extraction tab), so a C3D
    import could never automatically pair with its video, contradicting
    `page_new.py`'s own onboarding text. `_c3d_tab` now calls `_study_form`
    too (a new `key_prefix` param keeps its widget keys distinct from the
    video tab's, since both render unconditionally in the same
    `st.tabs(...)`), and `_load_c3d` writes the result into `data["study"]`.
  - **A C3D load never got a job ticket**, so it could never appear in
    Recent jobs next to a video extraction for the tick-select →
    `_selection_actions` → `pooling.load_runs` shortcut — pairing needed a
    manual export-then-reupload through the Cohort page's own uploader.
    New `JobManager.register_immediate(data, name, kind_label, study=)`
    writes a `DONE` job straight away (no worker); `_load_c3d` calls it
    with `kind_label="c3d-import"`. `_ticket_tab`'s "Finished — tick to
    analyse" list now groups by `(patient_id, condition)` and captions each
    tagged group's readiness ("ready to compare", "video only", "C3D
    only"). `_selection_actions`'s cohort path now passes an explicit
    `PipelineConfig()` (was `config=None`/autoconfig) so this shortcut
    matches the Cohort page's own "Analyse" button exactly.
  - **The "unspecified" condition bucket could silently pair unrelated
    patients.** `pooling.UNSPECIFIED` holds every untagged recording from
    every patient; `page_pool._accuracy_section` used to run
    `condition_agreement` on it like a real condition. It now refuses for
    that one label, with an explanation, instead of showing a number that
    might be comparing two different people.
  - **ISB reconstruction (default on) silently mixed two angle definitions
    in the accuracy comparison.** It recomputes a Vicon/C3D reference's
    hip/knee/ankle from ISB anatomical frames but is a no-op for markerless
    video (no 3-D markers) — the Cohort page hardcoded `PipelineConfig()`
    regardless, so hip/knee bias conflated tracking error with the
    ISB-vs-sagittal definitional offset documented below. A new checkbox
    ("ISB reconstruction for Vicon/C3D references", on by default) now
    threads through `load_runs`'s config, and `page_pool._isb_caveat` warns
    under the accuracy table whenever hip/knee is present and it is on —
    verified on P03: hip bias flips from −6.1° (on) to +4.9° (off), same
    pair, same code.
  - **The accuracy charts could not tell video and Vicon apart.**
    `pooling.condition_agreement`/`overall_agreement` now also return
    `video_pooled`/`vicon_pooled` (each kind pooled separately — merging
    first would blend the two into one indistinguishable mean), feeding a
    new `charts.kinematics.video_vs_reference_overlay`: a second, dedicated
    colour per kind (video vs Vicon/C3D), a deliberate exception to this
    module's usual "colour carries the side" rule — side survives as
    solid-vs-dashed line style.
  - **Advanced's tabs could not switch which ready recording they explored**
    without a trip back to New assessment. New `components.
    recording_switcher(slot)` renders a compact picker (no-ops under two
    finished recordings) in Pipeline explorer, Comparator's Sweep tab,
    Export, and Method validation's Vicon tab — switches the one shared
    active source, not an independent choice per tab.
- **"Reference" page renamed to "Index"** (`app.py`'s `PAGES`, `components.
  _PAGE_META`, `page_reference.py`'s header, `sidebar.py`'s tooltip,
  README.md/TUTORIAL.md) now that it holds more than a function glossary: a
  new "Guides" section documents the video-vs-C3D pairing workflow above,
  step by step, including the ISB-toggle caveat and the unspecified-group
  refusal.
- 163 tests passing (11 new: job registration, `_job_label`, 2 chart
  colour-encoding tests, 2 cohort-pairing UI tests, the Index guide, plus
  pooling extensions), ruff clean, 68.1% coverage (floor 60%).

## [0.7.0] — 2026-08-28 (Frédéric Fer)

Editable pivots and a two-condition comparison.

- **Edit pivot metadata in-app, with pre-fill and round-trip.** Loading a pivot
  now pre-fills the Subject controls and a new Study / condition editor from the
  file's stored `data["subject"]` / `data["study"]`; editing them and exporting
  downloads a JSON that keeps the changes. Subject anthropometry (incl. the
  measured segment lengths) and study identifiers round-trip both ways with
  `myogait` (uses `set_subject`/`set_study` from myogait 0.8.7, with a
  plain-dict fallback against older installs). Study lives in session state, not
  the pipeline config, so editing it never invalidates the analysis cache.
- **Compare two conditions against the MDC** (Cohort tab, shown with ≥2
  conditions). Per joint: mean per-cycle ROM in each condition, the difference,
  the 95% Minimal Detectable Change (repeatability from within-condition,
  within-subject cycle spread), and a verdict — real change vs within noise.
  Wires the previously unused `mdc.py`. Joint-ROM parameters only, stated in the
  UI. Verified end-to-end on real Bath BioCV trials.

## [0.6.0] — 2026-08-28

First tagged release since 0.5.0. It ships two clinical-standard corrections
**on by default**, each behind a visible sidebar switch: ISB-convention 3-D
hip/knee/ankle reconstruction for full-marker C3D sources (a no-op on video),
and calibrated restoration of the markerless ankle push-off. Both trace to
`myogait` 0.8.6. The detailed, author-attributed log follows.

- **Ankle push-off restoration on by default (Frédéric Fer).** The 2-D pose
  estimator low-passes the ankle waveform and flattens the fast push-off,
  under-reading ankle ROM by ~11° vs Vicon; `restore_ankle_dynamics` inverts
  that filter (calibrated once against Vicon, applied cadence-adaptively in Hz)
  and adds the systematic per-phase deficit back to every cycle, leaving
  inter-cycle variability untouched. Flipped on by default and given its first
  sidebar toggle (it had none). Robustness probes: restored ROM stays 30–33°
  across 60–150 steps/min (out-of-band harmonics clamp, they do not
  extrapolate); a simulated slow walk under-corrects at every cadence and never
  overshoots; a cycle whose push-off is suppressed is not reinvented (frequency
  domain, template-free). Not yet validated on pathological gait. Codegen emits
  the restore step so an exported script reproduces it.

## Unreleased — 2026-08-26 to 2026-08-28 (Romain Feigean)

- **`feat/isb-marker-cascade` merged into `main`** (fast-forward, commit
  `8e4600a` — CI green on all 6 matrix cells, 154 passed/1 unrelated skip,
  ruff clean; branch deleted after merge). Re-verified today against
  `myogait` master (0.8.6) itself: its own CI-equivalent commands
  (`ruff check myogait/ tests/ --select E,W,F --ignore E501`,
  `pytest tests/ --cov=myogait --cov-fail-under=75`) pass locally —
  1377 passed, 78.4% coverage.
  - **Two verification notes** (`Claude/test_fred/verification_by_claude/`,
    not tracked in this repo, same convention as Fred's own
    `ankle_dynamics_report.pdf`) re-run both of the parallel-work features
    against real Bath BioCV data available locally, rather than the
    synthetic fixtures either side's own unit tests use. ISB tier 1 on
    P03 (18/18 landmarks resolved): hip/knee offset and r reproduce the
    10–17° / r>=0.99 pattern documented below almost exactly. Ankle-dynamics
    restoration on P03/P04/P06/P08 (4 of Fred's 9 subjects; P03 is the only
    one with a local Vicon reference, and only 1 cycle/side — too few
    trials to confirm or refute his pooled 9-subject numbers): the
    correction deepened push-off in 5 of 6 video-only sides tested, with
    one real counter-example (P04 left, ROM −3.5°) flagged rather than
    hidden. Full method, caveats and figures in the notes themselves.
- **ISB-convention 3-D angle reconstruction (`feat/isb-marker-cascade`, on top
  of myogait's `feat/isb-3d-angles-tier1`).** Hip/knee/ankle can now be
  computed from proper ISB pelvis/thigh/shank/foot anatomical frames instead
  of this app's default trunk-referenced 2-D sagittal projection — a
  different angle *definition*, not just a precision gap (an internal audit
  against BATH and a Myokinesis clinical recording found r >= 0.99 between
  the two methods but a 10–17° constant offset on hip/knee, traced to the
  reference-segment difference). **On by default as of the reconciliation
  below** — a new "ISB reconstruction (hip/knee/ankle)" checkbox in the
  sidebar's Angles section still controls it. Degrades silently and safely
  to the existing sagittal result wherever the
  source can't support it (no `myogait.isb` yet, or the C3D's marker
  convention doesn't resolve enough of the paired medial/lateral landmarks
  ISB needs) — never fails the pipeline over this.
  - **Three calibration tiers, chosen automatically from whichever files are
    attached in the C3D tab** — not a separate control. Tier 1 (no file)
    needs only the trial C3D itself. Tier 2 adds a static trial (Harrington
    et al. 2007 hip-joint-centre regression). Tier 3 adds a `.vsk` + `.prot`
    on top for a full CGM/Plug-in-Gait-equivalent technical-cluster
    calibration — measured, real accuracy improvement over tier 2 confirmed
    on real Myokinesis data (hip HJC RMSE 2.76/1.72° → 0.47/0.61°). The
    "New assessment" C3D tab gained an "ISB calibration files (optional)"
    expander for the static/`.vsk`/`.prot` uploads, all optional; providing
    none keeps today's exact behaviour.
  - **Marker-convention resolution is auto-detected**, the same way this
    app already does for the base 6-landmark C3D mapping: a new
    `resolve_isb_mapping` cascade (alias tables for Myokinesis/BATH/Nature
    conventions first, a lateral/medial-aware keyword scan as fallback)
    finds the richer 18-landmark paired set ISB needs, so this works on any
    C3D convention, not just one clinic's naming — the flexibility this
    feature was explicitly required to keep.
  - **Bias corrections (LASSO healthy-gait models) are hard-blocked while
    ISB is active**, all three joints — they were fitted on the sagittal
    method's residuals and have no scientific basis applied to ISB's
    pelvis-referenced angles.
  - **The 2 extra degrees of freedom ISB also reconstructs — abduction/
    adduction and internal/external rotation — are cycle-normalised and
    charted** in the Pipeline explorer's Cycles tab (joint picker offers
    them only when the loaded run actually has them; a normative reference
    band is available for hip and knee abd/add, not yet for ankle or any
    rotation DOF — none exists anywhere in myogait yet). The CSV bundle
    export already carries them for free; the Excel workbook does not yet
    (hardcoded upstream in myogait's own `export.py`, not this app).
  - Reproducibility panel notes when ISB reconstruction was on (as a
    comment, not a literal reproducible call — which tier ran depends on
    files attached at load time, which `codegen`'s current signature
    doesn't carry).
  - New `myogait_app.marker_presets.resolve_isb_mapping`/
    `merged_c3d_mapping`, `pipeline.AnglesConfig.isb_reconstruction`,
    `ui.page_data._build_isb_context`, `ui.state.Source.isb_context`. 22 new
    tests across `test_marker_presets.py`, `test_isb_pipeline.py` and the
    new `test_page_pipeline_isb.py`; full suite green (122 passed, 1
    pre-existing skip), `ruff check` clean, CI green on every push
    (`ubuntu-latest`/`windows-latest` × Python 3.10–3.12).
  - Depends on `myogait.isb`/`myogait.vicon_calibration`
    (`reconstruct_isb_angles`/`_tier2`/`_tier3`, `calibrate_technical_frames`,
    Harrington HJC regression — 23 tests of its own), **merged into
    myogait's own `master` as of 0.8.6**. See CLAUDE.md's "ISB
    reconstruction" section for the full architecture writeup.
  - **Reconciled with a parallel, independent implementation of the same
    feature** that landed on `main` while this branch was in flight (same
    contributor as the earlier Nocturne visual identity, again in parallel
    without coordination): hip/knee-only, tier-1-equivalent, on by default,
    characterised across the Bath BioCV cohort (356 trial x joint x side —
    a clean, subject-specific level shift, waveform r=0.975 preserved,
    hip offset -6 to -22 deg). Kept this branch's architecture as the base
    (3 tiers, all of hip/knee/ankle, the hard bias-correction block) and
    folded in what was additive: its lazy, re-read-the-source-file marker
    injection now survives as a fallback for a pivot that never went
    through this branch's load-time marker cascade, its marker-alias table
    is unioned into this branch's own (computed, not hand-duplicated, after
    finding the two tables had already silently diverged — the parallel
    version's table alone resolved only 14/18 landmarks on a real
    Myokinesis C3D, missing its `LFMH1`/`LFMH5` codes), and its config
    fields/sidebar checkbox/codegen block/test file were removed as a
    strict subset of this branch's own. `codegen.python_snippet` picked up
    a genuine improvement from it: a literal, runnable tier-1 reproduction
    instead of a comment-only note. Full suite green (154 passed, 1
    pre-existing skip) against real myogait 0.8.6, `ruff check` clean.
- **Reconciled with "Nocturne": back to the paper-light Bauhaus identity.**
  0.3.0 below landed a second, independently art-directed visual identity
  (dark ground, blurple, Inter) on the same files as an in-progress
  refinement of the original light Bauhaus/international-typographic
  identity from Claude Design — two redesigns of the same surface, done in
  parallel without coordination. Product decision: keep the paper-light
  world, reasserted over Nocturne's tokens/CSS/font in `branding.py`,
  `.streamlit/config.toml`, `charts/theme.py` and `theme_css.py`, while
  keeping every non-visual part of 0.3.0 as-is — the Jobs list, the footer's
  partner-mark credits and package links (reskinned, not reverted), and the
  `st.pills` navigation (restyled as pressed ink boxes rather than reverted
  to a radio). See `DESIGN.md`'s "Reconciled with Nocturne" section for the
  full accounting of what changed back and what stayed.
- **Header, metric-strip and figure-frame fidelity pass.** `page_header()`,
  `source_summary()` and `chart()` in `myogait_app/ui/components.py` now
  match the Claude Design mockup's structural elements (the rotated colour
  bar and numbered folio on every page header, the alternating-colour
  metric grid, the bordered "fig. N" frame around every Plotly chart) —
  CSS injection alone cannot add new decorative markup, so this needed
  real (but page-file-untouched) layout code. See `DESIGN.md`'s "Structural
  fidelity pass" section.

## 0.3.0 — 2026-08-26 (Frédéric Fer)

- **"Nocturne" visual identity.** A dark Bauhaus/constructivist ground with a
  single blurple accent and Inter throughout: an underlined, capitalised
  wordmark with a geometric mark; page navigation as real pressed-button
  pills; outlined buttons; rules that fade to transparent at both ends;
  tracked-uppercase micro-labels; cards and metrics as hairline surfaces; and
  the walker illustration dimmed to a faint fixed texture behind the app.
  New `theme_css` module; `.streamlit/config.toml` and `branding` mirror the
  tokens (charts and chrome share Inter and the dark ground).
- **Jobs, not tickets.** The "Recover a job" tab is now a **Jobs** list that
  shows every extraction directly (Analyse / Stop inline) — no ticket to type.
- **Credits & links.** A discreet footer with the AIM and Téléthon marks
  (tinted to the ground), clickable GitHub links for myogait / gaitkit / this
  app, and a contact address; the version badge links the packages too.

## 0.2.1 — 2026-08-25 (Frédéric Fer)

- **Persistent extraction status.** A running extraction now shows in a banner
  at the top of every page (live progress + Stop), so it can be launched, left
  to run while working elsewhere, and picked back up — a finished one loads
  with a single Analyse button from anywhere. Start is disabled while an
  extraction runs (one at a time), and orphaned jobs from a server restart are
  reconciled at startup instead of blocking a new run with an eternal bar.

## 0.2.0 — 2026-08-25 (Frédéric Fer)

- **Cohort tab (analysis by condition).** Load many exported pivots at once
  and read a study by condition: pooled mean±SD kinematic curves with an
  age-matched normative band, ROM, stance/swing, cadence, duration, and —
  when a subject height is provided — step length in metres. GPS-2D / GDI-2D
  screening scores and a per-parameter validity note accompany the curves.
  When a condition also holds a marker (C3D) reference, an accuracy section
  reports RMSE / centred RMSE / waveform-r / ROM / peak-timing error per
  joint against it. New Streamlit-free modules `pooling`, `agreement`,
  `clinical`, `mdc`.
- **Study identifiers** written into each output JSON (patient, run, group,
  condition, optional height/age) so a pooled analysis can group and label
  every recording.

## 2026-08-25

- **Backend accessibility + GPU setup.** The Data page's model picker used
  to show only pose backends whose package was already importable. Now every
  backend myogait implements (mediapipe, yolo, openpose, vitpose ×3, rtmw,
  hrnet, mmpose, alphapose, detectron2, sapiens ×3, sapiens2 ×4) is always
  listed, with an install-status suffix and, for an uninstalled one, the
  exact pip command — sourced from `myogait.models.available_models()`
  directly rather than a hand-maintained copy, which had already drifted
  (`hrnet` was wrongly gated on `mmpose`; myogait needs only `torch`).
  Sapiens 2's multi-gigabyte weights now fetch automatically inside the
  extraction job itself the first time a size is picked, with no separate
  setup button. Two real bugs found by clicking through the app and fixed:
  the readiness check only looked at the *pose* model file, missing that
  the Sapiens segmentation checkbox loads a second, independently-cached
  file; and the weight-fetch/trace step ran outside the device-override
  block, so forcing CPU didn't apply to it — a real problem on Intel XPU,
  where tracing hit a missing kernel with no way to route around it. The
  "Sapiens depth" checkbox is now disabled for every `sapiens2-*` model:
  myogait still requests a HuggingFace repo Meta never published for v2
  (verified directly against HuggingFace); Sapiens v1's depth repos are
  real and unaffected. New `scripts/setup_gpu.py`: one command, run once
  after installing requirements, that detects the machine (NVIDIA via
  `nvidia-smi`, Intel via a pinned `torch==2.6.0+xpu` — not "latest":
  2.13.0's XPU wheel ships nested license paths deep enough to overflow
  Windows' 260-character `MAX_PATH`; 2.6.0 does not, confirmed on real
  Intel Arc hardware without needing any registry change) and installs the
  matching build. `requirements.txt` now requests every backend extra that
  installs cleanly via plain pip instead of just mediapipe/yolo. README
  gained a GPU acceleration section and a Model licenses section (Sapiens
  v1 is CC-BY-NC-4.0 non-commercial; Sapiens 2 excludes biometric
  processing and unlicensed medical/health practice).

- **Bauhaus / international-typographic-style redesign.** Replaces the
  chronophotography identity below, not a refinement of it — implemented
  from a concrete mockup built in Claude Design against this app's own real
  sidebar/page structure. Light-only by deliberate choice (Bauhaus print is
  inherently light-ground); `.streamlit/config.toml` drops the
  `[theme.dark]` section entirely. Palette: warm paper ground (`#e8e8e2`),
  near-black ink, one yellow accent (`#e0a80f`). The accent needed two
  tokens, not one, caught by `scripts/validate_palette.py` rather than
  assumed: measured at 1.75:1 against the paper ground (needs 3:1 even for
  non-text marks), the bright yellow is too light-valued to work as a
  standalone mark the way the mockup's other three primaries (red/blue/
  black) do — `accent_mark` (`#7f4c00`, same hue, darkened) is the fix for
  every line/rule/small numeral use. Side colour (left/right limb, on
  analysis charts) is re-specified to blue/ink, the one part of the
  categorical/side palette the mockup explicitly redraws; this surfaced a
  real bug in `charts/theme.py`'s `side_color()`, which used to re-derive
  left/right from categorical slots that only *happened* to match the old
  side colours and would have silently gone stale against the new ones —
  it now reads `Branding.side_colors` directly. Typography moves to
  Helvetica Neue for UI/headings. Also removed roughly 2,400 files (real
  per-subject gait trial data, internal strategy notes, a licensed
  third-party dataset) that had been uploaded wholesale into the source
  Claude Design project, discovered while reading the mockup and removed
  at the project owner's request.

- **Calibration: mirror myogait 0.8.2's isotropic step-length scaling**
  (Frédéric Fer). myogait 0.8.2 de-normalises `step_length`/`walking_speed`
  distances to source pixels before scaling, fixing an aspect-ratio
  under-estimation of step and stride length on non-square frames (roughly
  1.78× on 16:9 video). The app's official numbers pick this up
  automatically through `analyze_gait`, but the segment-based calibration
  cross-check (`myogait_app/calibration.py`) re-implements the geometry
  independently to compare calibration sources, so it silently kept the
  old anisotropic result. Adds `Runtime.step_length_isotropic_native`
  (gated at myogait 0.8.2) and applies the same de-normalisation there so
  the two panels stay comparable on any install; unchanged on older
  myogait or when frame dimensions are unavailable.

- Fixed the README's upgrade command, which was missing `loess,wavelet`
  and would have left a reader without the smoothing-filter options those
  extras enable.

## 2026-08-24

The main development session: the working tree's accumulated uncommitted
feature set was captured as a foundation commit, then extended and prepared
for a public GitHub release.

- **Foundation commit** capturing the app's actual working feature set that
  had accumulated on top of the initial skeleton: C3D import with
  multi-convention marker auto-detection, the independent multi-segment
  calibration cross-check, the myogait function-reference glossary, and the
  Pipeline explorer / Longitudinal / Reference pages with their charts.
- Added the **`nature_multimodal` C3D marker convention**: neither
  myogait's own registered conventions nor this app's fuzzy fallback could
  resolve a Nature Scientific Data "Multimodal Gait Dataset" file (0/6
  landmarks) because its ISB/CAST labels don't contain the substrings
  either detector looks for. Registered both in this app's own alias pool
  and directly into myogait's own convention registry, so native
  autodetection recognises it too.
- **Adopted myogait 0.7–0.8.1's calibration and signal-correctness
  parameters**: flexion-positive sign canonicalization (on by default —
  without it, two passes walked in opposite directions can disagree in
  sign), a calibration-offset guard, per-cycle confidence/coherence quality
  gates, and native femur/foot-length calibration instead of inverting a
  population height ratio. Added `pipeline._accepts()` (signature
  introspection) to gate new *keyword arguments* on existing functions,
  distinct from the existing whole-function-presence gating. Exposed all
  of it in the sidebar and in the generated Python/YAML/CLI reproducibility
  panel.
- **Stopped bypassing myogait's own C3D convention autodetection.** The
  C3D tab always built an explicit marker mapping first, which meant
  myogait's own (more complete) `detect_c3d_convention` never ran, and
  "Package default" silently triggered that same autodetection instead of
  the literal default its label promised. `marker_presets.resolve_c3d_
  mapping()` now tries myogait's own detector first, falling back to this
  app's fuzzy scan only when fewer than 4/6 required landmarks resolve, and
  surfaces which path fired. Also added 3-D ankle reference correction for
  C3D sources (the 2-D sagittal projection is faithful for hip/knee but
  collapses the ankle) and fixed a real occlusion-masking gap in the
  aspect-ratio recovery for pre-0.8.0 myogait installs.
- **Fixed a real chart bug**: `trunk` and `pelvis_obliquity` are stored
  once per frame in myogait's angle data, not once per side, but the
  kinematics chart always looked them up with a per-side key and silently
  drew an empty trace. Fixed the lookup and made `pelvis_obliquity`
  selectable in the Kinematics tab.
- **Prepared the repository for a public GitHub release**: added
  `.gitignore` and untracked committed `__pycache__` files and stray
  downloaded model weights that predated it; added the MIT license,
  matching myogait's own; rewrote the README for a public audience (what
  the app actually reads, a research/screening-tool disclaimer up front,
  environment-requirement rationale, a license section); credited
  Assistmyo · NeuPEL · Institut de Myologie in the license and a new
  README Author section; untracked `CLAUDE.md` (internal AI-assistant
  guidance) to keep it local-only.
- Added `PRODUCT.md` (product context for a visual-identity redesign) and
  then the **chronophotography (Étienne-Jules Marey) redesign** itself: a
  walking figure decomposed into luminous marker positions against a
  controlled ground, chosen by explicit user pick over a dice-assigned
  candidate. New `scripts/validate_palette.py` (WCAG contrast + simulated
  protanopia/deuteranopia in OKLab) validates every colour token — a
  script the code had promised in a comment for some time without actually
  existing. Fixed several colour call sites that read a single value
  without branching on light/dark, which cannot hit correct contrast
  against both grounds.
- Added `TUTORIAL.md`, a five-minute getting-started guide, with every UI
  claim checked against the actual source rather than written from memory.
- **Sidebar layout pass**: split the "Joint kinematics" section (grown to
  13 controls with no internal grouping) into Calibration / Corrections
  tabs. A "modified from default" marker for section labels was attempted
  and reverted after `AppTest` showed it lagging by exactly one
  interaction — a structural Streamlit ordering constraint (an expander's
  label is fixed before its body runs), not a bug fixable within that
  pass's scope; documented in `DESIGN.md` so it is not re-attempted blind.

## 2026-08-19

- **Project start.**

---

*Full technical detail — the exact bugs found, why a fix takes the shape
it does, and how each change was verified — lives in the individual git
commit messages (`git log`), which this file summarises rather than
replaces.*
