# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Streamlit workbench over the [myogait](https://github.com/IDMDataHub/myogait) markerless
gait-analysis toolkit. It is a *parameter explorer*: every lever myogait exposes downstream
of pose extraction is a control, the figures redraw against the same recording, and each
page can hand back the exact Python / YAML / CLI that produced what is on screen.

This repo contains **no myogait algorithms** — it drives them. When a computation looks
wrong, the answer is usually in the installed `myogait` package, not here.

## Commands

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
streamlit run app.py
```

Preview config (`.claude/launch.json`) runs it headless on port 8502 — use
`preview_start {name: "app-myogait"}` rather than launching a server from Bash.

Upgrading the toolkit (tracked from git master, not PyPI):

```bash
pip install --upgrade "myogait[mediapipe,yolo,excel,yaml] @ git+https://github.com/IDMDataHub/myogait.git@master" "gaitkit>=1.4.8"
```

**There is no test suite and no linter configured.** `myogait_app/demo.py` exists as the
headless fixture (`make_demo_data()` produces a valid pivot dict) — use it to exercise
`PipelineRunner` or `jobs.py` from a plain Python script without a video or a browser.
`myogait_app/jobs.py` deliberately does not import Streamlit so it stays runnable that way.

There is no `.gitignore`, so `__pycache__/*.pyc` files are tracked and show up dirty in
`git status`. Do not stage them as part of a change.

## Architecture

Flow: **`app.py`** (routing + always-visible sidebar) → **`ui/sidebar.py`** (builds a
`PipelineConfig`) → **`ui/state.py`** (session state, one `PipelineRunner` per source) →
**`pipeline.py`** (staged, memoised execution of the myogait chain) → **`charts/`** +
**`ui/page_*.py`** (render) with **`codegen.py`** echoing the same config back as code.

### `pipeline.py` — the engine

`STAGES = ("normalize", "angles", "events", "cycles", "bias", "analysis")`. Each stage has
its own **frozen dataclass** config, and each stage is memoised on the tuple of *everything
upstream of it*, so two configs sharing a prefix share that work. Moving a cycle-duration
bound reuses cached angles and events; changing the Butterworth cutoff invalidates
everything below.

Consequences that constrain any change here:

- **Stage configs are cache keys, so they must stay hashable.** Collection fields are
  tuples (`filters`, `consensus_methods`), never lists. A list field silently breaks the
  cache with `TypeError: unhashable`.
- Every stage receives a `copy.deepcopy` of its cached input — myogait mutates the pivot
  dict in place, and a shared reference would corrupt the cached upstream stage.
- Exceptions never escape: `_stage()` catches and reports which stage broke via
  `StageOutcome`, so the UI can name the failure. Keep that contract.
- **`bias` runs after `cycles`, not with the other angle corrections**, because the LASSO
  bias models are gait-phase-indexed. `_apply_bias` therefore re-segments and returns a
  `(data, cycles)` *tuple* — the only stage that caches a pair, which `_run_analysis`
  special-cases.
- The `analysis` key uses `subject.calibration_height_m`, not `height_m`.

### Three non-obvious domain decisions

**Femur-driven calibration.** myogait's `step_length`/`walking_speed` derive scale from
`height_m × 0.245` (a population femur ratio). `SubjectConfig.calibration_height_m` inverts
that ratio from a *measured* femur so myogait's own internal formula reproduces the real
segment. That property — not `height_m` — is what the pipeline passes to `analyze_gait`.
`calibration.py` is a separate cross-check that derives independent scales from every other
measured segment and flags disagreement; it does not feed the official numbers.

**Bias corrections default off and are gated.** They are LASSO models fitted on healthy
young adults and re-inject a healthy curve exactly where neuromuscular disease shows
itself. Hip and knee additionally require `angles.perspective` (they were fitted on
M1-corrected residuals). Keep the default, and keep the explanation at the control.
**Deprecated upstream since myogait 0.8.0** (removal planned for 1.0): its own
validation found the uncorrected pipeline already at optical-reference level with a
modern pose backbone, and these corrections degrade rather than improve it there; each
call now emits a `DeprecationWarning`. `BiasConfig` still wires them — a feature only
"planned" for removal is not gone yet — but do not expand this surface; plan its sunset
instead, possibly around the newer phase-binned `apply_landmark_bias_correction` family
in `myogait.corrections` if that proves out as a replacement.

**C3D aspect ratio is version-gated, not always-on.** Below myogait 0.8.0,
`load_c3d` normalised the antero-posterior and vertical axes independently, distorting
angles on any non-square recording; `myogait_app/c3d_utils.py` compensates by re-reading
the file's true axis ranges. 0.8.0 fixed this upstream (isotropic normalisation), so
running the app's own correction on 0.8.0+ would double-correct. `runtime.c3d_isotropic_native`
(version-gated on `C3D_ISOTROPIC_NATIVE_VERSION = (0, 8, 0)`) is what the C3D tab checks
before offering that control at all — do not re-enable it unconditionally.

### `runtime.py` — capability probing, not assumptions

The app targets `myogait >= 0.6.1` / `gaitkit >= 1.4.8` but runs against whatever is
installed, disabling what it cannot do instead of failing at click time. Backends are
probed with `importlib.util.find_spec` (resolve without importing — importing torch to grey
out a checkbox would cost seconds).

**Any optional myogait function you call from the UI must be registered in
`OPTIONAL_FEATURES`** (and in `FEATURE_EXTRA_REQUIREMENTS` if it needs a third-party
package at call time, like `export_c3d` needing `c3d`). Then gate the control with
`runtime.has("key")` and explain the absence with `runtime.missing_feature_hint("key")` —
disabled-with-a-reason, never hidden.

### `jobs.py` / `storage.py` — ephemeral by design

Extraction outlives a Streamlit script run, so it goes to a `ThreadPoolExecutor` and its
state lives **on disk** (`job.json`, written atomically); the UI polls the file rather than
holding a future, because reruns discard in-memory state. The user gets a `MG-XXXX-XXXX`
ticket. Cancellation is cooperative — raised from the progress callback, since myogait has
no other interruption point.

Nothing persists: sessions and job tickets are purged on `MYOGAIT_APP_RETENTION_HOURS`
(default 24). Ticket strings are regex-validated before they touch a path, and uploaded
filenames are reduced to `Path(name).name` — both are path-traversal guards, don't relax
them.

### `codegen.py` — keep it in step

The reproducibility panel appears on every analysis page and is generated from the same
`PipelineConfig` the pipeline just ran. **A new pipeline parameter is not done until
`python_snippet`, `yaml_config` and `cli_command` know about it**, or the panel starts
lying. Where YAML has no equivalent key, the setting is emitted as a comment rather than
dropped.

### Charts and colour

Plotly on screen (`charts/`, one registered template per light/dark, built from
`branding.py`); matplotlib **via myogait's own plotting functions** for exported publication
figures, so the paper figure and the CLI-reproduced figure are the same figure.

One encoding rule holds everywhere: **colour carries one entity per chart** — the side on
analysis pages, the model/method on the comparator (where side becomes a facet). The
palette in `branding.py` is validated (OKLCH lightness band, chroma floor, protan/deutan
separation, contrast, in both modes); do not substitute hex values without re-running that
check. `branding.py` is the only place any colour or label lives.

Dark mode is detected server-side in `components.is_dark()` and passed explicitly to every
chart function.

## Adding a pipeline parameter (the common task)

1. Add the field to the right frozen dataclass in `pipeline.py` (tuple, not list, for
   collections) and wire it into that stage's `_apply_*` function.
2. Add the control to the matching `_*_section` in `ui/sidebar.py` — sections are in
   pipeline order and each returns a rebuilt frozen config.
3. If it calls a myogait function that may be absent, register it in
   `runtime.OPTIONAL_FEATURES` and gate the control with `runtime.has(...)`.
4. Extend `codegen.py` (all three outputs).
5. Consider a `glossary.py` entry — the Reference page and sidebar tooltips are grounded in
   myogait's own docstrings via that module.

## Configuration

All behaviour is environment-driven (`settings.py`, `SETTINGS` is a frozen singleton read
at import): `MYOGAIT_APP_WORKSPACE`, `_RETENTION_HOURS`, `_MAX_UPLOAD_MB`, `_MAX_JOBS`,
`_WATCH_DIR`, `_EXPERIMENTAL`, `_SHOW_CODE`, `_NAME`/`_LOGO`. The upload limit exists in
three places that must stay in sync: `settings.py`, `.streamlit/config.toml`, and nginx
`client_max_body_size` in `deploy/nginx-location.conf` — at the nginx default, every video
upload fails with a 413 before Streamlit sees it.
