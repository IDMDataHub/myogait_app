# app myogait

An interactive workbench for the [myogait](https://github.com/IDMDataHub/myogait)
markerless gait analysis toolkit.

It exists to answer one kind of question well: *what does this parameter
actually change?* Every lever myogait exposes downstream of extraction is a
control here, the figures redraw against the same recording, and each screen can
hand back the exact Python, YAML and CLI that produced what is on it. It reads
from a video, a pre-extracted pivot JSON, or a marker-based `.c3d` motion-capture
trial (with automatic marker-convention detection across labs and protocols),
and drives myogait's own functions throughout — this repository contains no
gait-analysis algorithms of its own.

**Research and screening tool, not a diagnostic device.** The pathology
screens, clinical scores and normative comparisons throughout the app are
heuristic and explicitly labelled as such at the point of use; read them
alongside the kinematic curves, never as a standalone diagnosis.

---

## Quick start

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
streamlit run app.py
```

Then open the **Data** page and load a pivot JSON or a video.

## Environment requirements

The app probes the environment at startup and disables what the installed
version cannot do, rather than failing at click time. Two versions matter:

| Package | Minimum | Why |
|---|---|---|
| `myogait` | **0.6.1** | Below it, `apply_linear_detrend` does not exist, and Sapiens 2, the clinical scores and the VICON block are missing or behave differently. |
| `gaitkit` | **1.4.8** | The `gk_*` event detectors the comparator puts in competition come from here. 1.3.x does not provide them. |

That floor is a *minimum*, not a recommendation: **0.8.0 fixed a critical
`load_c3d` bug** (each axis was normalised by its own range instead of
isotropically, distorting every angle computed from a non-square recording)
and a hip-sign inversion, benchmarked against marker-based optical motion
capture. Everything below this app degrades gracefully on an older install,
but a C3D-heavy workflow specifically wants 0.8.0 or newer.

Below **0.8.0**, `load_c3d` normalises the antero-posterior and vertical axes
independently, distorting angles on any non-square recording; the C3D tab's
"Correct the aspect ratio" control (`myogait_app/c3d_utils.py`) compensates
for it. From 0.8.0 on the fix is native (isotropic normalisation) and the app
detects this (`runtime.c3d_isotropic_native`) to stop offering that control,
so it never double-corrects. From **0.7.0**, `load_c3d`/`detect_c3d_convention`
can autodetect the marker-naming convention a C3D file uses across five
registered conventions (Plug-in Gait, ISB, Helen Hayes, BioCV, and this app's
own addition for the Nature Scientific Data "Multimodal Gait Dataset") — the
C3D tab tries this first and shows which one it picked, falling back to its
own alias-and-keyword scan only when that cannot resolve enough landmarks.

```bash
pip install --upgrade \
  "myogait[mediapipe,yolo,excel,yaml] @ git+https://github.com/IDMDataHub/myogait.git@master" \
  "gaitkit>=1.4.8" ezc3d "c3d>=0.5"
```

Do **not** request the `myogait[c3d]` extra directly: its `pyproject.toml` pins
`ezc3d>=2.0`, which PyPI has never published for any platform (1.7.2 is the
newest available), so requesting it fails the whole install. C3D import only
needs `ezc3d` (any resolvable version); C3D export needs the separate `c3d`
package — both are installed unbundled above instead.

Optional backends install as extras — `myogait[vitpose]`, `myogait[rtmw]`,
`myogait[sapiens2]`, plus `intel-extension-for-pytorch` for Intel Arc
acceleration. Anything absent is shown greyed out with the reason.

## What is in it

| Page | Does |
|---|---|
| **Data** | Load a pivot JSON or a video. Video extraction runs as a background job and returns a recoverable ticket. |
| **Pipeline explorer** | Every downstream parameter as a control, with kinematics, cycles, spatio-temporal metrics and signal quality updating live. |
| **Comparator** | Sweep one parameter across values, or compare separate extractions of the same walk, with divergence curves, an RMS matrix and an event-timing raster. |
| **Export** | CSV, Excel, OpenSim `.mot`/`.trc`, C3D, Pose2Sim, the PDF report, an anonymised stick figure, and publication figures rendered by myogait's own matplotlib functions. |
| **Experimental** | VICON trial alignment and the AIM input-degradation grid. Scoped as experimental by the package itself. |

## Design decisions worth knowing

**Stage caching.** The pipeline is memoised per stage on everything upstream of
it. Moving a cycle duration bound recomputes in ~60 ms instead of ~490 ms,
because the filtering, angles and events above it are reused. Changing the
Butterworth cutoff correctly invalidates the whole chain below it.

**Bias corrections are off by default, and say why.** myogait's
`apply_{hip,knee,ankle}_bias_correction` are LASSO models fitted on healthy
young adults. The package documents that they re-inject a healthy curve exactly
where neuromuscular disease shows itself — swing knee flexion in DMD and CMT,
ankle push-off in drop foot, end-stance hip extension in hip weakness. The app
states this at the control, and gates the hip and knee models behind the M1
perspective correction their coefficients were fitted on top of. They are also
phase-indexed, so they run *after* segmentation and the app re-segments
afterwards — otherwise you would read corrected curves against uncorrected cycle
statistics.

**Colour carries one entity per chart.** On the analysis pages that entity is the
side; on the comparator it is the model or method, and the side becomes a facet.
The palette is the validated reference set — it passes the lightness band, chroma
floor, protan/deutan separation, normal-vision floor and contrast checks in both
light and dark mode. Do not substitute hex values without re-running that check.

**Correctness fixes default on, feature toggles default off.** A flexion-positive
sign convention independent of walking direction, and (for a C3D source) an
ankle recomputed from the 3-D marker positions rather than the 2-D sagittal
projection that collapses it, are both on by default — myogait 0.8.0
correctness fixes with no legitimate reason to disable them. The bias
corrections below are the opposite case, and stay off by default for the
reason described next.

**Nothing is kept.** A browser session gets a scratch directory; the only thing
that outlives it is a job ticket, and both are purged on a fixed clock
(`MYOGAIT_APP_RETENTION_HOURS`, default 24). Purging runs at startup and on the
Data page, and the retention rule is stated in the interface rather than applied
silently.

## Configuration

All settings are environment variables, so the same code runs on a laptop and on
the lab server.

| Variable | Default | Purpose |
|---|---|---|
| `MYOGAIT_APP_WORKSPACE` | system temp | Where uploads, jobs and outputs live. |
| `MYOGAIT_APP_RETENTION_HOURS` | `24` | Purge window. |
| `MYOGAIT_APP_MAX_UPLOAD_MB` | `2048` | Must match `.streamlit/config.toml` and nginx. |
| `MYOGAIT_APP_MAX_JOBS` | `1` | Concurrent extractions. Raising it needs no code change. |
| `MYOGAIT_APP_WATCH_DIR` | unset | Server-side drop folder, so a 2 GB file can arrive over SMB/scp instead of the browser uploader. |
| `MYOGAIT_APP_EXPERIMENTAL` | `true` | Show the VICON/AIM page. |
| `MYOGAIT_APP_SHOW_CODE` | `true` | Show the reproducibility panel. |
| `MYOGAIT_APP_NAME` / `MYOGAIT_APP_LOGO` | neutral | Branding. See below. |

## Deployment

`deploy/` holds an nginx location block and a systemd unit for running this
behind a reverse proxy. The one thing that needs raising from the defaults:
2 GB uploads need `client_max_body_size 2048m` and raised timeouts — left at the
nginx default, every video upload fails with a 413 before Streamlit sees it.

```bash
sudo cp deploy/app-myogait.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now app-myogait
```

## Branding

The identity is deliberately neutral. Everything a rebrand touches lives in
`myogait_app/branding.py` — app name, tagline, logo, and the palette. Set
`MYOGAIT_APP_NAME` and `MYOGAIT_APP_LOGO` for the quick version, or edit the
dataclass for a full one. No colour or label is hardcoded anywhere else.

## Layout

```
app.py                     entry point and page routing
myogait_app/
  settings.py              environment-driven configuration
  branding.py              identity and the validated palette
  runtime.py               probes myogait/gaitkit version, device, backends, features
  storage.py               ephemeral workspaces, job tickets, purge
  jobs.py                  background extraction pool (Streamlit-free, testable)
  pipeline.py              staged engine with per-stage memoisation
  codegen.py               Python / YAML / CLI generation
  marker_presets.py        C3D marker-convention detection and fallback
  c3d_utils.py             pre-0.8.0 C3D aspect-ratio compatibility shim
  calibration.py           multi-segment pixel/mm calibration cross-check
  glossary.py              myogait function reference for tooltips and the Reference page
  demo.py                  synthetic dataset (dev/test fixture, not wired into the UI)
  charts/                  Plotly theme and figures
  ui/                      Streamlit pages
deploy/                    nginx + systemd
```

## License

[MIT](LICENSE). myogait itself is developed separately at
[IDMDataHub/myogait](https://github.com/IDMDataHub/myogait), also MIT.
