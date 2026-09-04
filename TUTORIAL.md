# Getting started

A five-minute walkthrough: upload a video, run an extraction, read the first
kinematic curves, then find your way to everything else the app can measure.
Assumes the app is already running (see the README's **Quick start**) and
open in your browser.

## 1. Upload a video and run an extraction

Open **New assessment** (the sidebar page list) and its **Video → extraction**
tab.

1. **Pose model** — pick a backend. For a first try, `MediaPipe` is the
   right choice: it runs on CPU and finishes in roughly real time. Heavier
   backends (ViTPose, Sapiens…) are more accurate but need a GPU to be
   practical. The dropdown only lists backends actually installed on this
   machine — install more via the `pip` extras in the README to unlock
   them.
2. Leave **Limit frames** at `0` (all frames) unless you are sanity-checking
   a model on a long recording first.
3. Under **Video source**, choose **Upload** and pick your file
   (`.mp4`/`.mov`/`.avi`/`.mkv`/`.m4v`). For a large file that struggles
   through the browser, the "Already on the server" option covers files
   dropped into the server's watch folder instead.
4. Fill the **patient / condition** identifiers, then click **Start
   extraction**. Every job also gets a ticket like `MG-XXXX-XXXX`, but you
   do not need to keep it: extraction runs in the background, and the
   **Recent jobs** tab lists every job (newest first) with **Analyse** /
   **Stop** inline — navigate away, close the tab, come back, it is still
   there.
5. Progress shows under the Start button and in **Recent jobs**. When the job
   is finished, click **Analyse** — the extraction is now the loaded source,
   and every other screen works from it.

Prefer to skip extraction on a first try? The **Pivot JSON** tab loads a
`.myogait.json` file already produced by a CLI run, instantly. Motion-capture
labs can load a `.c3d` trial directly from the **C3D** tab instead of a
video — see the README for how marker-convention detection handles that.

## 2. Read the first kinematic signals

Go to **Analysis** and pick the **Trial Explorer** scope. The sidebar now
fills with the full pipeline configuration — every parameter myogait exposes
downstream of extraction, each with an explanation at the control. Defaults
are sensible; nothing here needs touching yet. (An *Expert settings* switch
keeps the deeper sections collapsed until you want them.)

The **Kinematics** tab (open by default) is the first thing worth reading:
raw joint angles plotted against time, left and right in their own colour,
with heel-strikes (solid vertical lines) and toe-offs (dotted) marked. By
default it shows hip, knee and ankle; the **Joints** selector above the
chart adds trunk lean and pelvis obliquity too.

What to look for on a first pass:

- **A repeating rhythm.** Gait is cyclic — each joint's curve should show
  clearly repeated shapes between heel-strikes, not noise.
- **Plausible ranges.** Knee flexion swinging roughly 0–60°, ankle a
  narrower band, is normal; a curve pinned near 0° or swinging wildly
  usually means a tracking problem, not a gait finding.
- **The heel-strike/toe-off count row** below the chart. Zero or wildly
  uneven left/right counts mean event detection needs a different method or
  cutoff (sidebar, **3. Gait events**) before anything downstream is
  trustworthy.

If a curve looks wrong, the **Signal quality** tab (last on this page) shows
per-frame detection confidence and biomechanical coherence — it usually
explains *why* a kinematic curve looks off, rather than leaving you to guess.

## 3. Explore what else can be measured

The tabs below Kinematics are all on **Analysis → Trial Explorer**; the rows
after them are separate screens.

| Where | What you get |
|---|---|
| **Cycles** tab | Time-normalised gait-cycle curves (0–100%), mean ± SD per side, range-of-motion bars, stance/swing split, a per-cycle table. |
| **Spatio-temporal** tab | Cadence, stride time, step length and walking speed, symmetry, variability, and heuristic pathology screening (Trendelenburg, spastic gait, steppage, crouch — screening signals, never a diagnosis). Step length/speed read in real metres once a height or a measured femur length is entered in the sidebar's **Subject** panel; without one, they stay in normalised units. |
| **Advanced analysis** tab | Single support time, toe clearance, stride variability, arm swing, cadence drift, centre-of-mass path, postural sway, angular velocity/acceleration, time-frequency analysis, PCA on cycle-to-cycle variation — twelve myogait functions with no other home in the app, each computed on demand. |
| **Analysis → Markerbased vs Monocular** | One video+C3D pair, every parameter, the markerless and marker-based results drawn together — where and how the two methods differ, as curves. |
| **Analysis → Accuracy vs C3D** | Markerless-vs-Vicon agreement (bias, RMSE, r, CMC, ICC), paired automatically by patient, once a video and its C3D share a patient and condition. |
| **Advanced → Comparator** | Sweep one parameter across several values on the same recording, or load a second extraction and compare the two directly — divergence curves, an RMS matrix, an event-timing raster. |
| **Advanced → Patient over time** | Track one subject across several sessions, with a minimal-detectable-change threshold on each parameter. |
| **Advanced → Groups** | One group's descriptive statistics, or two independently imported groups compared parameter by parameter with an adaptive difference test. |
| **Advanced → Export** / **Analysis → Export** | CSV, Excel, OpenSim `.mot`/`.trc`, C3D, a PDF report, an anonymised stick-figure video, and publication figures rendered by myogait's own plotting functions. Analysis carries the clinical subset; Advanced adds the rendered video and the narrated video / MoCap reports. |
| **Index** | A glossary of every myogait function this app calls, grounded in the package's own docstrings — the fastest way to look up what a control actually does — plus short step-by-step guides for multi-step workflows (e.g. pairing a video extraction with its Vicon C3D for an accuracy comparison). |

## 4. Reproduce what you just did

Every analysis page ends with a **Reproduce this** expander: the exact
Python, YAML, or CLI form of whatever is currently on screen, generated from
the same configuration the pipeline just ran — never a description of it,
the actual call. Copy it into a script, a batch config, or a lab notebook to
rerun the same analysis outside the app.
