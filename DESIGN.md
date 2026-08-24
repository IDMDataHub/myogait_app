# Design

<!-- impeccable:design-doc -->

Written directly rather than by the shipped documenter subagent: this is a
Streamlit app with no browser or image-generation tool available in the
session that built it, so there is no screenshot or comp for that agent
to work from. Disclosed per the skill's own finish contract rather than
silently substituted.

## World

Chronophotography (Étienne-Jules Marey): a walking figure decomposed into
a sequence of luminous marker positions against a controlled ground. The
direction round (`concept-seed.mjs --scope direction --mode operate`)
assigned a different grounded candidate (an engraved anatomical atlas
plate, index 5 of 7); the user overrode it with their own top-ranked pick,
which a pinned decision always outranks. Three disciplines were raised
into the build from declined catalog challengers: one fully-committed
accent reserved for the active/interactive element only (from a
transforming-textile challenger); colour confined to precise thin
encoding lines rather than filled regions (from an iridescent-cloud-edge
challenger); disabled/absent states rendered as deliberately as present
ones, not merely hidden (from a seven-segment-display challenger — this
one also reinforced a rule the app already followed: every disabled
control states why, never just greys out).

Color strategy: **Restrained** (neutrals plus one accent) — Operate
mode's default, and the correct one here: the categorical/side/status
data-visualization colours are functional encoding, not brand identity,
and were deliberately left unchanged (see below).

## Palette

Validated by `scripts/validate_palette.py` (WCAG contrast + OKLab deltaE
under simulated protanopia/deuteranopia) — re-run it before changing any
value here. Source of truth: `myogait_app/branding.py`; mirrored into
`.streamlit/config.toml` for Streamlit's own chrome.

| Token | Light | Dark | Role |
|---|---|---|---|
| surface | `#eff1f0` | `#0d1012` | Page ground — published engraving-plate paper (light) / glass-plate negative (dark) |
| surface (secondary) | `#e2e6e3` | `#181c1f` | Sidebar, widget backgrounds |
| ink | `#12161a` | `#eef1f0` | Primary text |
| ink (muted) | `#5b6461` | `#9aa39f` | Secondary/annotation text |
| border | `#c7cdc9` | `#2a3033` | Hairline rules, widget borders |
| accent | `#8a5a12` | `#e0a24f` | The one saturated colour — active/interactive elements only |

Dark is the default `base` (deliberate: the world's own source material —
Marey's actual apparatus — is a dark-ground medium; light is its
secondary, derived translation). Both are fully specified and the user
can switch either way; Streamlit's own light/dark toggle governs which
renders, and `myogait_app/ui/components.py::is_dark()` tells server-side
chart code which one is active.

**Left unchanged, by design decision, not oversight:** the eight-slot
categorical palette, the left/right side colours, the achromatic
normative-band colour, and the four reserved status colours. These
already pass the same validation and are functional data-encoding
choices ("colour carries one entity per chart") independent of the
identity redesign — re-deriving them was out of scope for this pass.

## Typography

- **Archivo** (Google Fonts, loaded via `.streamlit/config.toml`'s
  `font` key) — UI text and headings. A grotesk with a technical,
  engineering register rather than a friendly-app one; avoided the
  category-default list (Space Grotesk, IBM Plex, DM Sans, Inter-as-
  display, etc.) per the skill's own calibration guidance.
- **JetBrains Mono** (`codeFont`, same loading mechanism) — code blocks
  and the reproducibility panel. Not a "technical" costume: this app's
  own generated Python/YAML/CLI snippets are literal code, so monospace
  here is functional, not decorative.
- Plotly figures (`myogait_app/charts/theme.py`) share the Archivo family
  so charts and chrome read as one typeface, not two.

## Shape

`baseRadius = "none"`, `buttonRadius = "none"` (`.streamlit/config.toml`)
— hard-edged, precision-instrument corners rather than Streamlit's
default soft-rounded chrome. No other structural change: Streamlit's own
component layout, spacing, and interaction model were preserved
throughout: this is a token-level identity change (colour, type, radius),
not a rebuild of the interface's structure.

## What this redesign did not touch

- Component layout, page structure, and interaction flows — unchanged.
- The categorical/side/status data-viz palette (see above).
- `myogait_app/ui/components.py::is_dark()`'s detection logic — still
  correct against the new `base = "dark"` default.

## Verification performed

No comp existed to compare against (code-led by necessity: no image
generation tool in this session), so verification was:

1. `scripts/validate_palette.py` — every new fg/bg pair, both themes:
   WCAG contrast ≥4.5:1 (≥3:1 for the achromatic hairline/border pairs,
   the correct bar for non-text UI chrome) and OKLab deltaE ≥10 under
   simulated protanopia and deuteranopia. All passed.
2. `streamlit.testing.v1.AppTest` — every page (Data, Pipeline explorer,
   Comparator, Longitudinal, Export, Experimental, Reference), both cold
   and with a real loaded C3D recording, zero exceptions.
3. A real `streamlit run` launch on a live port, confirmed HTTP 200 and a
   clean startup log — Streamlit's own config loader (stricter than
   generic TOML parsing) accepts the nested `theme.light`/`theme.dark`/
   `*.sidebar` structure.
4. `scripts/detect.mjs` (the skill's mechanical defect scanner) run over
   the changed files — returned no findings; it is built for HTML/CSS/JS
   and has no verdict on Python/TOML, so this is a clean pass by
   inapplicability, not a substantive check, and is reported as such.

No visual screenshot review happened at any point (no browser tool
available in this session) — this is the one real gap against the
skill's normal finish process, disclosed rather than hidden.
