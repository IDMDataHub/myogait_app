"""Visual identity.

Reconfigurable by design, not neutral by default: swap the values in
``BRANDING`` (or point the two environment variables at your own assets)
and the whole app follows. No colour or label is hardcoded anywhere else.

The default identity draws on chronophotography (Étienne-Jules Marey): a
walking figure decomposed into a sequence of luminous marker positions
against a controlled ground. Colour is restrained on purpose -- one
accent, reserved for the active/interactive element; everything else
achromatic -- because colour is what *encodes information* here, on
charts and in the UI alike, and an identity that spent it on page
texture would compete with that job instead of serving it.
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
    # substituting any of these hexes. surface_dark/ink_dark are the
    # glass-plate/velvet negative (Marey's original apparatus); surface_
    # light/ink_light are its published-engraving counterpart. accent is
    # the one saturated colour in the interface chrome, reserved for the
    # active/interactive element only -- never scattered as page texture.

    surface_light: str = "#eff1f0"
    surface_light_secondary: str = "#e2e6e3"
    ink_light: str = "#12161a"
    ink_muted_light: str = "#5b6461"
    border_light: str = "#c7cdc9"

    surface_dark: str = "#0d1012"
    surface_dark_secondary: str = "#181c1f"
    ink_dark: str = "#eef1f0"
    ink_muted_dark: str = "#9aa39f"
    border_dark: str = "#2a3033"

    accent: str = "#8a5a12"
    accent_dark: str = "#e0a24f"
    accent_soft: str = "#c69a5c"

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

    #: Left / right limb. Slot 8 against slot 1 -- the widest separation
    #: available in the palette (CVD deltaE 21.6, normal 32.3).
    side_colors: dict = field(
        default_factory=lambda: {"left": "#e34948", "right": "#2a78d6"}
    )

    #: Normative band. Deliberately achromatic: the reference is context,
    #: not a series, and must never compete with the patient curve.
    normative: str = "#898781"

    #: Chart chrome, retuned to the new cool-graphite ground family
    #: (was a warm gray unrelated to any surface colour in the app).
    grid: str = "#e4e7e5"
    grid_dark: str = "#20262a"
    axis: str = "#c7cdc9"
    axis_dark: str = "#2a3033"
    #: Kept for call sites that do not (yet) branch on ``dark`` -- prefer
    #: ``ink_muted_light``/``ink_muted_dark`` in any new code.
    ink_muted: str = "#6b716d"

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
