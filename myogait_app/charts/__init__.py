"""Chart layer: Plotly on screen, matplotlib (via myogait) for export."""

from .theme import PLOTLY_CONFIG, apply, register, series_colors, side_color, template_for

__all__ = [
    "PLOTLY_CONFIG",
    "apply",
    "register",
    "series_colors",
    "side_color",
    "template_for",
]
