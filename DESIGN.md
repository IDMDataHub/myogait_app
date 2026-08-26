# Design

<!-- impeccable:design-doc -->

Written directly rather than by the shipped documenter subagent: this is a
Streamlit app with no browser or image-generation tool available in the
session that built it, so there is no screenshot or comp for that agent
to work from. Disclosed per the skill's own finish contract rather than
silently substituted.

## World

Bauhaus, ~1960s international-typographic-style print: sharp geometric
edges, a warm paper ground, Helvetica Neue set in tracked-out uppercase,
one saturated primary reserved for the active/interactive element. This
redesign replaces the chronophotography (Marey) identity documented
below in earlier revisions of this file -- not a refinement of it, a
full swap, per the standard "redesign replaces" rule: the old identity's
tokens are gone, not layered under this one.

Source of truth for this pass was a concrete mockup (`Myogait Pipeline
Explorer.dc.html`, built in Claude Design against this app's own real
sidebar/page structure) rather than a from-scratch direction round --
implementation here means faithfully translating that mockup's tokens
into this codebase's architecture, not inventing a new world.

Color strategy: **Restrained** (paper neutrals plus one accent) --
unchanged in kind from the previous identity, still the correct choice
for Operate mode: the categorical/side/status data-visualization colours
are functional encoding, not brand identity. Side colour *is* re-derived
this pass (see below) because the source mockup explicitly re-specifies
it; the eight-slot categorical palette and status colours are not
touched, same as last time.

## Palette

Validated by `scripts/validate_palette.py` (WCAG contrast + OKLab deltaE
under simulated protanopia/deuteranopia) -- re-run it before changing any
value here. Source of truth: `myogait_app/branding.py`; mirrored into
`.streamlit/config.toml` for Streamlit's own chrome.

| Token | Value | Role |
|---|---|---|
| surface | `#e8e8e2` | Page ground -- warm paper |
| surface (secondary) | `#dedcd4` | Sidebar, widget backgrounds |
| ink | `#16181a` | Primary text |
| ink (muted) | `#5b6461` | Secondary/annotation text |
| border | `#b9b6ac` | Hairline rules, widget borders |
| accent | `#e0a80f` | The one saturated colour -- **fills only** (buttons, chips, swatches with dark text on top) |
| accent (mark) | `#7f4c00` | Same hue, darkened -- accent used as a mark *on* the paper (thin rules, small numerals, chart lines, links) |
| side: left | `#1c4fb0` | Re-specified this pass (was red) -- see below |
| side: right | `#16181a` | Re-specified this pass (was blue) -- plain ink, not a second saturated hue |

**Light-only, by deliberate choice, not an oversight.** The source
mockup only ever demonstrated a light/paper world -- Bauhaus print is
inherently light-ground -- so `.streamlit/config.toml` drops the
`[theme.dark]` section entirely rather than carry forward the previous
identity's dark tokens or invent an undemonstrated dark counterpart.
`branding.py`'s `_dark` fields are kept (equal to their light values)
purely so a call site that still branches on `dark` -- Streamlit's own
OS-preference escape hatch -- renders this identity correctly rather
than a stale mix of the old dark palette with this pass's light
structure, rather than because a second world was art-directed.

**The accent needed two tokens, not one -- measured, not assumed.** The
mockup offers four interchangeable primaries (red, blue, gold, black);
red/blue/black are all dark-valued enough to work identically as a
filled block *and* as a thin mark straight on the paper. The user's
choice, gold (`#e0a80f`), is not: measured at 1.75:1 against the paper
ground (needs 3:1 even for non-text marks) it would have been nearly
invisible as a chart line, a small numeral, or link text. `accent_mark`
(`#7f4c00`, same OKLCH hue, lightness dropped 0.763 -> 0.465) is the fix
-- 5.8:1 on the page, 5.2:1 on the sidebar -- and every call site that
draws the accent as a mark rather than a fill (`kinematics.py`'s stance
line, `.streamlit/config.toml`'s `linkColor`) uses it instead of the
bright fill token. `Branding.accent_ink_for(dark)` is the reverse pairing
-- what text sits *on* an accent fill -- kept as its own method because
the previous identity's accent was dark enough to pair with near-white
text and this one needs dark ink instead; hardcoding white here was the
one-line bug the palette validator caught before this shipped.

**Side colour re-specified, not left alone.** The previous redesign
deliberately left `side_colors` untouched as out of scope. This one
doesn't: the source mockup hardcodes left as its own blue constant,
distinct from the accent, with right as plain ink rather than a second
saturated colour -- a concrete, demonstrated choice, not a gap to fill
in. `charts/theme.py`'s `side_color()` used to re-derive left/right from
categorical slots 8 and 1 -- correct only because the *previous*
side_colors happened to equal those two hexes. This pass's blue/ink pair
isn't in the categorical tuple at all, so that shortcut would have
silently gone stale; `side_color()` now delegates to
`Branding.color_for_side()` directly so the two definitions cannot drift
apart again.

**Left unchanged, by design decision, not oversight:** the eight-slot
categorical palette, the achromatic normative-band colour, and the four
reserved status colours. Not shown or re-specified anywhere in the
source mockup, and independent of the identity swap above -- re-deriving
them was out of scope for this pass, same reasoning as the first
redesign.

## Typography

- **Helvetica Neue** (system font stack -- `Helvetica Neue, Helvetica,
  Arial, sans-serif`, no web-font load) -- UI text and headings. The
  international-typographic-style workhorse this world is built from;
  heavy use of tracked-out uppercase for labels, matching the source
  mockup exactly.
- **JetBrains Mono** (`codeFont`, Google Fonts, unchanged from the
  previous identity) -- code blocks, the reproducibility panel, and any
  data/numeral display, matching the mockup's own monospace figure
  treatment.
- Plotly figures (`myogait_app/charts/theme.py`) share the Helvetica
  Neue family so charts and chrome read as one typeface, not two.

## Shape

`baseRadius = "none"`, `buttonRadius = "none"` -- unchanged in value
from the previous identity (both redesigns land on the same sharp,
geometric corner language, for different reasons: precision-instrument
there, Bauhaus grid-and-primaries here). No other structural change to
Streamlit's own component layout, spacing, or interaction model.

## What this redesign did not touch

- Page structure and interaction flows outside the sidebar and the
  Pipeline explorer page's top summary -- unchanged.
- Every sidebar section's control layout -- unchanged (only the colour/
  type/shape tokens cascade in); the numbered "1./2./3./4." prefixes
  already matched the mockup's own numbering signature closely enough
  that relabeling them "01/02/03/04" was not worth the risk for a
  cosmetic-only gain.
- The categorical/status data-viz palette (see above).
- A literal HTML/CSS reconstruction of the mockup's own hand-built SVG
  charts and "mortar-grid" card layout: the existing Plotly charts and
  `st.metric`/`st.columns` summary strips (`components.py::source_
  summary`, `stage_status`) already carry the same information the
  mockup's Fig. 1-3 and stats strip show, and now inherit this
  identity's tokens automatically through the same architecture the
  first redesign established -- rebuilding them as static HTML to match
  the mockup pixel-for-pixel would trade real, interactive, live-data
  charts for a facsimile, which Operate mode's own principles (native
  widgets, live data over decoration) argue against.
- `myogait_app/ui/components.py::is_dark()`'s detection logic -- still
  correct; nothing here depends on it returning true in practice, since
  no dark world was art-directed this pass.

## Verification performed

1. `scripts/validate_palette.py` -- every fg/bg pair actually used by a
   call site (text, muted text, accent-as-mark, ink-on-accent-fill,
   border, both side colours), light and dark tokens (dark being an
   intentional equal-to-light fallback, not a second world): WCAG
   contrast >=4.5:1 for text (>=3:1 for non-text marks/side colours) and
   OKLab deltaE >=10 under simulated protanopia and deuteranopia. All
   passed after the accent/accent_mark split above -- the first run
   caught the bright accent failing as a standalone mark, which is
   exactly what this script exists to catch before it ships.
2. `streamlit.testing.v1.AppTest` across every page, zero exceptions.
3. A real `streamlit run` launch, confirmed serving.

No visual screenshot review happened at any point (no browser tool
available in this session) -- this is the one real gap against the
skill's normal finish process, disclosed rather than hidden, same as
the previous redesign.

## Refinement pass: colour-block + injected CSS

A follow-up, not a replacement -- the direction stays the same Bauhaus/
1960s print world above, implemented from a second, more complete Claude
Design handoff (`branding_identity.py`, `config.toml`, `theme_css.py`)
covering all six screens instead of Pipeline explorer alone.

**What changed**: the paper/ink/accent hexes were retuned slightly
(`#e8e8e2`/`#16181a`/`#e0a80f` -> `#edeae3`/`#111213`/`#f0b90b`) and two
more primaries were added -- `primary_red` (`#c21b16`) and `primary_blue`
(`#1b4fb0`, matching `side_colors["left"]`, which was re-pointed at it).
Unlike the yellow accent, both new primaries are dark-valued enough to
serve as text/marks *and* as a filled block with paper-coloured text on
top (`Branding.primary_ink_for`) -- red was darkened from the mockup's
original `#d6231f` (4.25:1) to `#c21b16` (5.0:1) specifically so it
clears AA as small text, not just as a large fill.

**New file**: `myogait_app/theme_css.py`. Targets Streamlit's stable
`data-testid`/`data-baseweb` attributes only, never generated class
names, so it survives Streamlit version upgrades. This is what
`.streamlit/config.toml`'s theme block cannot express on its own: the
sidebar's black identity-slab, the numbered-folio treatment on
expanders, tab underlines replaced with a yellow slab indicator,
hairline-divided metric cells, 3px-ruled buttons, hatched progress bars.
`.streamlit/config.toml`'s `[server]`/`[browser]`/`[runner]` sections
are deliberately left untouched by this pass -- the handoff's own
config.toml only specified `[theme]`, and this app's operational
settings (upload size, XSRF, telemetry opt-out, fast reruns) are not a
design decision.

**Encoding rules held**: colour still carries one entity per chart
(side on analysis pages, model/method on the Comparator); joint identity
still rides on dash pattern, not hue, so side stays the only colour axis;
yellow stays reserved for the interaction accent alone -- never page
texture. The categorical/normative/status data-viz palette is untouched
again, same reasoning as both passes before it.

## Structural fidelity pass: header, metric strip, figure frame

Closer to the actual `Myogait App.dc.html` mockup than the refinement
pass above, which only ever reskinned Streamlit's existing widget DOM
via CSS. CSS injection alone cannot add new decorative elements (a
rotated colour bar, a numbered folio, a boxed word inside a heading) --
that needs real layout markup, so this pass touches Python, not just
`theme_css.py`, while staying inside the design-only boundary agreed for
this work: `myogait_app/ui/components.py` (the one place a page's chrome
is built), `myogait_app/ui/sidebar.py` (four one-line marker calls, no
control logic touched), and `theme_css.py`. No pipeline, analysis,
export, marker-mapping, calibration or chart-generation file was edited.

**`page_header()`** now looks up a `(number, eyebrow)` pair from the page
title (a fixed table, e.g. Pipeline explorer -> `02` / "Parametric
explorer") and renders a rotated blue bar, a quarter-circle, the page
number in red JetBrains Mono, a vertical eyebrow label, an h1 with its
last word boxed in solid ink, and a small left/right colour swatch
echoing the side encoding used on the charts below. Call sites are
unchanged (`page_header(title, description)`); a title with no table
entry still renders correctly via a `--` fallback, so a page added later
never breaks.

**`source_summary()`** now renders its four figures as a custom HTML
grid instead of four `st.metric` widgets, to get the mockup's alternating
cell colours (plain / solid ink / plain / solid yellow) that Streamlit's
own metric widget cannot take per-instance. Every other `st.metric` call
in the app (spatiotemporal tab, clinical scores, cohort summaries) is
untouched and keeps the generic hairline-cell CSS treatment.

**`chart()`** wraps every Plotly figure in a bordered `st.container`,
a small numbered "fig. N" tag (alternating red/blue), and a black
caption bar -- purely presentational, the figure itself (data, colour,
layout) is untouched. Numbering resets per page (`page_header()` does
it) rather than climbing across the whole session, since how many charts
a session actually renders depends on the loaded data and the controls
in use, unlike a fixed mockup's own static figure count; the caption
text is derived from the `key` argument every call site already passes
(`fig_timeline` -> "Joint angle timeline"), with a humanised fallback for
anything not in that table. This lives entirely in `components.py::chart()`
-- `page_pipeline.py`, `page_compare.py` and `page_pool.py` already funnel
every figure through it, so no page file needed a line of new code, and
`myogait_app/ui/page_longitudinal.py`'s matplotlib figures (rendered via
`st.pyplot`, myogait's own `plot_longitudinal`/`plot_session_comparison`)
are unaffected -- deliberately out of scope, since wrapping those would
mean touching a page file to fit the same frame around a different
rendering path, for a comparatively small visual gain.

**`sidebar_identity()`** now renders a black slab with a small two-cell
yellow/red swatch as a logo mark, the app name and the tagline, instead
of a plain `st.markdown("## ...")` heading. **`sidebar_section_marker()`**
is new: a small coloured JetBrains Mono numeral placed just above each
of the four already-numbered sidebar sections (`01` red / Signal
conditioning, `02` blue / Joint kinematics, `03` gold-mark / Gait events,
`04` ink / Cycle segmentation) -- the existing digit in each expander's
own label is left as-is, this just adds the folio treatment beside it.
`Subject` and `2b. Bias corrections` intentionally get no chip: the
mockup's four-slot numbering doesn't map cleanly onto this app's six
real sections, and inventing a fifth/sixth colour to force-fit it would
misrepresent structure that isn't there.

Verified the same way as every pass before it: `scripts/validate_palette.py`
(the two new primaries confirmed independently, not trusted from the
handoff), a manual `AppTest` sweep across every page with an extended
timeout (the harness default is too short for this app's cold start --
see "Reconciled with Nocturne" below), the full pytest suite, and a real
`streamlit run` launch confirmed serving.

## Reconciled with Nocturne (2026-08-26)

While this identity was mid-refinement, `092e27d` ("Nocturne dark
identity, pressed-pill nav, footer credits", tagged v0.3.0) landed on
`main` from another contributor: an independently art-directed **dark**
Bauhaus/constructivist world (blurple accent, Inter, a dimmed walker
photo behind the app) on almost exactly the same files as this document
describes. Two designers had redesigned the same surface in parallel,
without coordination. Put to the product owner directly; the decision
was to keep this paper-light Bauhaus world and reassert it over
Nocturne, while keeping every non-visual addition Nocturne's commit
carried alongside its CSS -- the Jobs list (no ticket to type), the
footer's partner-mark credits and package links, and the cohort/clinical
work in earlier commits of the same release. None of that is a colour
or typography decision, so none of it needed to move.

**What was reverted**: `.streamlit/config.toml`'s `[theme]` block (back
to `base = "light"`, the tokens above, Helvetica Neue); `branding.py`'s
identity tokens (the `_dark` fields go back to equalling their `_light`
counterparts -- light-only was always this identity's own deliberate
choice, not an oversight Nocturne happened to fix); `charts/theme.py`'s
`_FONT` constant (Inter -> Helvetica Neue; the rest of that file reads
`BRANDING` dynamically, so fixing the tokens was enough -- it needed no
other change); `theme_css.py` (full rewrite back to the Bauhaus rules
above, `inject()`/`background_css()`/`render_footer()` keeping the exact
function names and call signature `app.py` already used, so app.py
itself needed only one change, below).

**What was kept from Nocturne's commit, reskinned rather than reverted**:
the footer (`render_footer()`, partner marks + package links + contact,
now on a solid ink rule and `accent_mark`-coloured links instead of a
fade gradient and blurple); the `st.pills` sidebar navigation (a
perfectly good widget choice independent of which identity is on top --
restyled as pressed ink-filled boxes rather than reverted to `st.radio`).
`background_css()` is kept as a deliberate no-op rather than removed
from its `app.py` call site: the walker-photo backdrop doesn't fit a
flat, no-photography Bauhaus world (the same reason the *earlier*
chronophotography/Marey identity was replaced by Bauhaus in the first
place, see "World" above) but the asset files stay in the repo rather
than being deleted, in case a future pass wants them.

**The one app.py change**: the sidebar's identity markup was inlined
directly in `app.py` by Nocturne's commit rather than calling
`components.sidebar_identity()` -- restored the function call, since
"the single place branding surfaces" (that function's own docstring) is
an architecture rule this document has held since the first redesign,
not a preference to relitigate per identity.

**A real, pre-existing test-suite gap surfaced during this reconciliation,
left unfixed**: `tests/test_smoke_pages.py` selects the sidebar nav via
`next(r for r in app.radio if "Data" in r.options)` -- since Nocturne's
commit replaced that `st.radio` with `st.pills`, this now raises
`StopIteration` rather than a passing assertion, for the "Pipeline
explorer" case specifically. This predates every change in this section
(introduced by `092e27d` itself, confirmed by reading that commit's own
`app.py` diff) and is not this pass's file to fix unprompted. The other
`test_smoke_pages.py`/`test_cohort_smoke.py` failures are the
already-documented default-`AppTest`-timeout margin issue (3s, too short
for this app's cold start), not a regression -- reconfirmed by rerunning
every page with an extended timeout and getting zero exceptions.
