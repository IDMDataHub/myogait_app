"""Plotly theme.

One template, built from the validated palette in :mod:`branding`, applied
to every figure so the app reads as one system rather than a pile of
plots. Light-only by this redesign's own deliberate choice (see
branding.py's module docstring) -- the dark template is kept registered,
built from the same light tokens, purely so a figure requested with
``dark=True`` (Streamlit's own OS-preference escape hatch) still renders
correctly rather than mixing an old dark palette with this one's chrome.

Chrome is deliberately recessive: hairline grid, muted axis text, no
chart border. The data is the only thing with saturation.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

from ..branding import BRANDING

#: Registered template names.
TEMPLATE_LIGHT = "myogait_light"
TEMPLATE_DARK = "myogait_dark"

#: Helvetica Neue: the international-typographic-style workhorse this
#: identity's world is built from (see .streamlit/config.toml, which
#: loads it for the whole UI too, so charts and chrome read as one
#: typeface, not two).
_FONT = "Helvetica Neue, Helvetica, Arial, -apple-system, 'Segoe UI', sans-serif"


def _build(dark: bool) -> go.layout.Template:
    surface = BRANDING.surface_for(dark)
    ink = BRANDING.ink_for(dark)
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
        tickfont=dict(color=BRANDING.ink_muted_for(dark), size=11),
        title=dict(font=dict(color=BRANDING.ink_muted_for(dark), size=12)),
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
    """Colour for a limb side, from ``BRANDING.side_colors`` directly.

    Previously re-derived from categorical slots 8/1 -- correct only
    because the old side_colors dict happened to hold the same two
    hexes. This redesign's side_colors (blue/ink) are not in the
    categorical tuple at all, so that shortcut silently went stale;
    delegating to color_for_side keeps the two definitions from ever
    drifting apart again. ``dark`` is unused: side_colors is light-only.
    """
    return BRANDING.color_for_side(side)


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
