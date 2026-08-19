"""Plotly theme.

One template, built from the validated palette in :mod:`branding`, applied
to every figure so the app reads as one system rather than a pile of
plots. Dark mode is a *selected* set of steps against the dark surface,
not an automatic inversion of the light one.

Chrome is deliberately recessive: hairline grid, muted axis text, no
chart border. The data is the only thing with saturation.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

from ..branding import BRANDING

LIGHT_SURFACE = "#fcfcfb"
DARK_SURFACE = "#1a1a19"
LIGHT_INK = "#0b0b0b"
DARK_INK = "#ffffff"

#: Registered template names.
TEMPLATE_LIGHT = "myogait_light"
TEMPLATE_DARK = "myogait_dark"

_FONT = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, "
    "'Helvetica Neue', Arial, sans-serif"
)


def _build(dark: bool) -> go.layout.Template:
    surface = DARK_SURFACE if dark else LIGHT_SURFACE
    ink = DARK_INK if dark else LIGHT_INK
    grid = BRANDING.grid_dark if dark else BRANDING.grid
    axis = BRANDING.axis_dark if dark else BRANDING.axis
    colorway = BRANDING.categorical_dark if dark else BRANDING.categorical

    axis_style = dict(
        showgrid=True,
        gridcolor=grid,
        gridwidth=1,
        zeroline=False,
        linecolor=axis,
        linewidth=1,
        ticks="outside",
        ticklen=4,
        tickcolor=axis,
        tickfont=dict(color=BRANDING.ink_muted, size=11),
        title=dict(font=dict(color=BRANDING.ink_muted, size=12)),
        automargin=True,
    )

    return go.layout.Template(
        layout=dict(
            colorway=list(colorway),
            paper_bgcolor=surface,
            plot_bgcolor=surface,
            font=dict(family=_FONT, size=12, color=ink),
            title=dict(font=dict(size=15, color=ink), x=0, xanchor="left", pad=dict(b=8)),
            xaxis=axis_style,
            yaxis=axis_style,
            # Crosshair + shared tooltip: on a kinematic trace the useful
            # question is always "what are all the joints doing at this
            # instant", not "what is this one point".
            hovermode="x unified",
            hoverlabel=dict(
                bgcolor=surface,
                bordercolor=axis,
                font=dict(family=_FONT, size=12, color=ink),
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="left",
                x=0,
                font=dict(size=11, color=ink),
                bgcolor="rgba(0,0,0,0)",
                borderwidth=0,
            ),
            margin=dict(l=8, r=8, t=48, b=8),
        )
    )


def register() -> None:
    """Register both templates with Plotly. Safe to call repeatedly."""
    pio.templates[TEMPLATE_LIGHT] = _build(dark=False)
    pio.templates[TEMPLATE_DARK] = _build(dark=True)


register()


def template_for(dark: bool) -> str:
    return TEMPLATE_DARK if dark else TEMPLATE_LIGHT


def series_colors(dark: bool) -> tuple[str, ...]:
    """Categorical slots for the active mode, in fixed order."""
    return BRANDING.categorical_dark if dark else BRANDING.categorical


def side_color(side: str, dark: bool) -> str:
    """Colour for a limb side.

    Slot 8 (left) and slot 1 (right), taken from the mode's own steps.
    """
    slots = series_colors(dark)
    return slots[7] if str(side).lower().startswith("l") else slots[0]


def apply(fig: go.Figure, dark: bool, title: str = "", height: int | None = None) -> go.Figure:
    """Apply the template and the shared layout decisions to *fig*."""
    fig.update_layout(template=template_for(dark))
    if title:
        fig.update_layout(title=dict(text=title))
    if height:
        fig.update_layout(height=height)
    return fig


def rgba(hex_color: str, alpha: float) -> str:
    """Translucent fill from a palette hex, for SD and normative bands."""
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


#: Standard Plotly config: no modebar clutter, but keep the export button
#: because this app is used to prepare figures for publication.
PLOTLY_CONFIG = {
    "displaylogo": False,
    "modeBarButtonsToRemove": [
        "select2d",
        "lasso2d",
        "autoScale2d",
        "hoverClosestCartesian",
        "hoverCompareCartesian",
        "toggleSpikelines",
    ],
    "toImageButtonOptions": {"format": "png", "scale": 3},
    "responsive": True,
}
