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
