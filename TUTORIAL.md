# Getting started

A five-minute walkthrough: upload a video, run an extraction, read the first
kinematic curves, then find your way to everything else the app can measure.
Assumes the app is already running (see the README's **Quick start**) and
open in your browser.

## 1. Upload a video and run an extraction

Open the **Data** page (the sidebar page list) and its **Video → extraction**
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
4. Click **Start extraction**. You get back a ticket like `MG-XXXX-XXXX` —
   keep it. Extraction runs in the background: you can navigate away, close
   the tab, and come back later and recover it from the **Recover a job**
   tab using that ticket.
5. Progress shows under **This session's extractions**. When it reaches
   **Load**, click it — the extraction is now the loaded source, and every
   other page works from it.

Prefer to skip extraction on a first try? The **Pivot JSON** tab loads a
`.myogait.json` file already produced by a CLI run, instantly. Motion-capture
labs can load a `.c3d` trial directly from the **C3D** tab instead of a
video — see the README for how marker-convention detection handles that.

## 2. Read the first kinematic signals

Switch to the **Pipeline explorer** page. The sidebar now fills with the
full pipeline configuration — every parameter myogait exposes downstream of
extraction, each with an explanation at the control. Defaults are sensible;
nothing here needs touching yet.

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

Everything below lives on the same **Pipeline explorer** page, one tab over
from Kinematics, or one page over in the sidebar.

| Where | What you get |
|---|---|
| **Cycles** tab | Time-normalised gait-cycle curves (0–100%), mean ± SD per side, range-of-motion bars, stance/swing split, a per-cycle table. |
| **Spatio-temporal** tab | Cadence, stride time, step length and walking speed, symmetry, variability, and heuristic pathology screening (Trendelenburg, spastic gait, steppage, crouch — screening signals, never a diagnosis). Step length/speed read in real metres once a height or a measured femur length is entered in the sidebar's **Subject** panel; without one, they stay in normalised units. |
| **Advanced analysis** tab | Single support time, toe clearance, stride variability, arm swing, cadence drift, centre-of-mass path, postural sway, angular velocity/acceleration, time-frequency analysis, PCA on cycle-to-cycle variation — twelve myogait functions with no other home in the app, each computed on demand. |
| **Comparator** page | Sweep one parameter across several values on the same recording, or load a second extraction and compare the two directly — divergence curves, an RMS matrix, an event-timing raster. |
| **Longitudinal** page | Track the same subject or protocol across multiple loaded sessions over time. |
| **Export** page | CSV, Excel, OpenSim `.mot`/`.trc`, C3D, a PDF report, an anonymised stick-figure video, and publication figures rendered by myogait's own plotting functions. |
| **Reference** page | A glossary of every myogait function this app calls, grounded in the package's own docstrings — the fastest way to look up what a control actually does. |

## 4. Reproduce what you just did

Every analysis page ends with a **Reproduce this** expander: the exact
Python, YAML, or CLI form of whatever is currently on screen, generated from
the same configuration the pipeline just ran — never a description of it,
the actual call. Copy it into a script, a batch config, or a lab notebook to
rerun the same analysis outside the app.
