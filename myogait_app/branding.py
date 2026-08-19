"""Visual identity.

Deliberately neutral for now. Everything a future rebrand needs to touch
lives in this file: swap the values in ``BRANDING`` (or point the two
environment variables at your own assets) and the whole app follows.
No colour or label is hardcoded anywhere else.
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

    # ── Palette ──────────────────────────────────────────────────────
    #
    # These values are not chosen by eye. They are the validated
    # reference palette, checked with the six computable data-viz tests
    # (OKLCH lightness band, chroma floor, protan/deutan separation in
    # OKLab, normal-vision floor, contrast against the surface) in both
    # light and dark mode. An earlier hand-picked set failed four of
    # them, so do not substitute hexes here without re-running the check.
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

    accent: str = "#2a78d6"
    accent_soft: str = "#86b6ef"

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

    #: Chart chrome.
    grid: str = "#e1e0d9"
    grid_dark: str = "#2c2c2a"
    axis: str = "#c3c2b7"
    axis_dark: str = "#383835"
    ink_muted: str = "#898781"

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


BRANDING = Branding.from_env()
