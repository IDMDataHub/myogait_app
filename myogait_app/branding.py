"""Visual identity.

Reconfigurable by design, not neutral by default: swap the values in
``BRANDING`` (or point the two environment variables at your own assets)
and the whole app follows. No colour or label is hardcoded anywhere else.

The identity draws on Bauhaus, ~1960s international-typographic-style
print: sharp geometric edges (no radius anywhere), a warm paper ground,
Helvetica Neue set in tracked-out uppercase, and one saturated primary
reserved for the active/interactive element -- everything else
achromatic -- because colour is what *encodes information* here, on
charts and in the UI alike, and an identity that spent it on page
texture would compete with that job instead of serving it. Committed to
a single light, paper-toned world on purpose (not a token-swap dark
counterpart): Bauhaus's own print language is inherently light-ground,
and inventing an undemonstrated dark variant would dilute a deliberate,
single visual world into a generic one. See DESIGN.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Branding:
    """Names, colours and assets used across the interface."""

    app_name: str = "app myogait"
    tagline: str = "Interactive workbench for the myogait toolkit"
    #: Optional path to a logo image shown in the sidebar. When absent,
    #: the sidebar falls back to the app name as plain text.
    logo_path: Path | None = None
    #: Optional link target for the logo / title.
    home_url: str | None = None

    # ── Identity: ground, ink and accent ────────────────────────────
    #
    # The one part of the palette this redesign actually changed. Every
    # value is validated the same way as the categorical palette below
    # (WCAG contrast ratio, OKLab deltaE under simulated protanopia and
    # deuteranopia) by scripts/validate_palette.py -- run it before
    # substituting any of these hexes. Light-only by deliberate choice
    # (see the module docstring): the _dark fields below are kept, equal
    # to their light counterparts, purely so call sites that still branch
    # on ``dark`` (Streamlit's own OS-preference escape hatch) render the
    # same correct Bauhaus look rather than a stale mix of the previous
    # identity's dark tokens with this one's light structure.

    surface_light: str = "#e8e8e2"
    surface_light_secondary: str = "#dedcd4"
    ink_light: str = "#16181a"
    ink_muted_light: str = "#5b6461"
    border_light: str = "#b9b6ac"

    surface_dark: str = "#e8e8e2"
    surface_dark_secondary: str = "#dedcd4"
    ink_dark: str = "#16181a"
    ink_muted_dark: str = "#5b6461"
    border_dark: str = "#b9b6ac"

    #: The one saturated colour in the interface chrome, reserved for the
    #: active/interactive element only -- never scattered as page texture.
    #: Yellow needs dark text on fill, unlike the mockup's other three
    #: primaries (red/blue/black all pair with near-white) -- see
    #: ``accent_ink_for`` below and its call sites.
    accent: str = "#e0a80f"
    accent_dark: str = "#e0a80f"
    accent_soft: str = "#f0d386"
    #: Same hue as ``accent``, darkened (OKLCH L 0.763 -> 0.465) for any
    #: use as a *mark on the paper ground itself* rather than a filled
    #: block -- thin rules, small numerals, chart lines, focus outlines.
    #: Measured, not guessed: the bright accent is only 1.75:1 against
    #: `surface_light` (needs 3:1 even for non-text marks; both colours
    #: sit at the light end), so it reads as a legible gold rather than
    #: vanishing into the paper. 5.8:1 on surface_light, 5.2:1 on
    #: surface_light_secondary -- see scripts/validate_palette.py.
    accent_mark: str = "#7f4c00"
    accent_mark_dark: str = "#7f4c00"

    # ── Data-viz palette: unchanged by this redesign ────────────────
    #
    # These were not touched: they are validated against the same six
    # computable tests (OKLCH lightness band, chroma floor, protan/deutan
    # separation in OKLab, normal-vision floor, contrast) in both light
    # and dark mode, and re-deriving eight categorical hues plus the
    # side/status pairs is a colour-design exercise independent of the
    # ground/accent identity above -- see scripts/validate_palette.py
    # before ever substituting a hex below.
    #
    # One encoding rule holds everywhere in the app:
    #
    #   colour carries ONE entity per chart.
    #
    # On the analysis pages the entity is the *side*, so left and right
    # take two maximally separated slots. On the comparator the entity is
    # the *model or method*, so those take the categorical slots in fixed
    # order and the side moves to a facet instead. A chart never asks
    # colour to mean both at once.

    #: Categorical slots, assigned in fixed order and never cycled.
    #: A ninth series folds into a facet, not a generated hue.
    categorical: tuple[str, ...] = (
        "#2a78d6",  # 1 blue
        "#eb6834",  # 2 orange
        "#1baf7a",  # 3 aqua
        "#eda100",  # 4 yellow
        "#e87ba4",  # 5 magenta
        "#008300",  # 6 green
        "#4a3aa7",  # 7 violet
        "#e34948",  # 8 red
    )

    #: Dark-mode steps of the same slots. Selected against the dark
    #: surface, not derived by flipping the light values.
    categorical_dark: tuple[str, ...] = (
        "#3987e5", "#d95926", "#199e70", "#c98500",
        "#d55181", "#008300", "#9085e9", "#e66767",
    )

    #: Left / right limb. Blue against ink -- re-specified by this
    #: redesign (was red/blue): the source mockup hardcodes left as its
    #: own blue constant, distinct from the accent, with right as plain
    #: ink rather than a second saturated hue. Large lightness *and* hue
    #: separation, so it survives protan/deutan simulation same as the
    #: pair it replaces -- reconfirm with scripts/validate_palette.py.
    side_colors: dict = field(
        default_factory=lambda: {"left": "#1c4fb0", "right": "#16181a"}
    )

    #: Normative band. Deliberately achromatic: the reference is context,
    #: not a series, and must never compete with the patient curve.
    normative: str = "#898781"

    #: Chart chrome, matched to this redesign's warm paper ground.
    grid: str = "#c9c7bf"
    grid_dark: str = "#c9c7bf"
    axis: str = "#b9b6ac"
    axis_dark: str = "#b9b6ac"
    #: Kept for call sites that do not (yet) branch on ``dark`` -- prefer
    #: ``ink_muted_light``/``ink_muted_dark`` in any new code.
    ink_muted: str = "#5b6461"

    #: Status colours, reserved. Never reused as a series colour.
    status: dict = field(
        default_factory=lambda: {
            "good": "#0ca30c",
            "warning": "#fab219",
            "serious": "#ec835a",
            "critical": "#d03b3b",
        }
    )

    @classmethod
    def from_env(cls) -> "Branding":
        logo = os.environ.get("MYOGAIT_APP_LOGO", "").strip()
        return cls(
            app_name=os.environ.get("MYOGAIT_APP_NAME", "").strip() or "app myogait",
            logo_path=Path(logo) if logo else None,
            home_url=os.environ.get("MYOGAIT_APP_HOME_URL", "").strip() or None,
        )

    def color_for_index(self, index: int) -> str:
        """Return a stable categorical colour for series *index*."""
        return self.categorical[index % len(self.categorical)]

    def color_for_side(self, side: str) -> str:
        return self.side_colors.get(str(side).lower(), self.accent)

    def accent_for(self, dark: bool) -> str:
        return self.accent_dark if dark else self.accent

    def accent_mark_for(self, dark: bool) -> str:
        return self.accent_mark_dark if dark else self.accent_mark

    def accent_ink_for(self, dark: bool) -> str:
        """Text/icon colour to place *on top of* a solid accent fill.

        Not simply ``ink_for``'s opposite: the source mockup's other three
        primaries (red/blue/black) all pair with near-white text at
        WCAG AA, but this yellow accent is too light-valued for that --
        white-on-yellow lands under 2:1. Dark ink on yellow clears 13:1,
        so every "on" chip/button/fill state in the UI must call this
        instead of hardcoding a light text colour.
        """
        return self.ink_for(dark)

    def surface_for(self, dark: bool) -> str:
        return self.surface_dark if dark else self.surface_light

    def surface_secondary_for(self, dark: bool) -> str:
        return self.surface_dark_secondary if dark else self.surface_light_secondary

    def ink_for(self, dark: bool) -> str:
        return self.ink_dark if dark else self.ink_light

    def ink_muted_for(self, dark: bool) -> str:
        return self.ink_muted_dark if dark else self.ink_muted_light

    def border_for(self, dark: bool) -> str:
        return self.border_dark if dark else self.border_light


BRANDING = Branding.from_env()
