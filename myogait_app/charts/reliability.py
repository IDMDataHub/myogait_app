"""Figures for the reliability statistics: Bland-Altman and group boxplots.

Same visual family as every other chart in the app: colours come from the
shared theme's categorical palette, layout from ``theme.apply``, so these sit
next to the kinematics and comparison figures without a seam.
"""

from __future__ import annotations

import plotly.graph_objects as go

from .theme import apply, rgba, series_colors


def bland_altman_plot(
    ba,
    parameter: str = "",
    dark: bool = False,
    height: int = 360,
) -> go.Figure:
    """Mean-vs-difference scatter with bias and limits of agreement.

    *ba* is a :class:`myogait_app.reliability.BlandAltman`. The bias is a
    solid line, the +/- 1.96 SD limits dashed, and the bias 95% CI a shaded
    band when present.
    """
    colours = series_colors(dark)
    accent, muted = colours[0], colours[1]

    fig = go.Figure()
    if ba.bias_ci95 is not None:
        lo, hi = ba.bias_ci95
        fig.add_hrect(y0=lo, y1=hi, line_width=0, fillcolor=rgba(accent, 0.12))
    fig.add_hline(y=ba.bias, line_color=accent, line_width=2,
                  annotation_text=f"bias {ba.bias:+.2f}", annotation_position="top left")
    for value, label in ((ba.loa_low, "-1.96 SD"), (ba.loa_high, "+1.96 SD")):
        fig.add_hline(y=value, line_color=muted, line_dash="dash", line_width=1.4,
                      annotation_text=f"{label} ({value:+.2f})",
                      annotation_position="bottom right" if value == ba.loa_low else "top right")
    fig.add_hline(y=0, line_color=rgba(muted, 0.5), line_width=1)
    fig.add_trace(go.Scatter(
        x=list(ba.means), y=list(ba.diffs), mode="markers",
        marker={"color": accent, "size": 9, "opacity": 0.75,
                "line": {"color": rgba(accent, 0.9), "width": 1}},
        name="patients", hovertemplate="mean %{x:.2f}<br>diff %{y:+.2f}<extra></extra>",
    ))
    fig.update_xaxes(title_text=f"Mean of the two methods{f' — {parameter}' if parameter else ''}")
    fig.update_yaxes(title_text="Difference (video − reference)")
    return apply(fig, dark, height=height)


def biomarker_trend_plot(
    labels: list[str],
    values: list[float],
    parameter: str = "",
    mdc: float | None = None,
    dark: bool = False,
    height: int = 340,
) -> go.Figure:
    """One parameter's value across sessions, in the order given.

    Advanced -> Patient over time's biomarker trend (audit B1 extension):
    when *mdc* is available (a within-session cycle-to-cycle repeatability
    estimate for a joint-ROM-type parameter, see ``page_longitudinal.
    _param_mdc``), a shaded band +/- MDC95 around the first session marks
    the zone a later point cannot leave without being a real change rather
    than measurement noise -- the trend equivalent of the pairwise MDC
    table already on this page.
    """
    colours = series_colors(dark)
    accent = colours[0]
    fig = go.Figure()
    if mdc is not None and values:
        baseline = values[0]
        fig.add_hrect(
            y0=baseline - mdc, y1=baseline + mdc, line_width=0,
            fillcolor=rgba(accent, 0.12),
            annotation_text=f"±MDC95 ({mdc:.2f}) around session 1",
            annotation_position="top left",
        )
    fig.add_trace(go.Scatter(
        x=labels, y=values, mode="lines+markers",
        line=dict(color=accent, width=2.5), marker=dict(size=9),
        name=parameter or "value",
        hovertemplate="%{x}<br>%{y:.2f}<extra></extra>",
    ))
    fig.update_yaxes(title_text=parameter or "Value")
    fig.update_xaxes(title_text="Session")
    return apply(fig, dark, height=height)


def group_boxplot(
    rows: list[dict],
    parameter: str,
    group_a: str,
    group_b: str,
    by: str = "group",
    dark: bool = False,
    height: int = 360,
) -> go.Figure:
    """Between-group boxplot of one biomarker, individual runs overlaid.

    *rows* is the long-format output of
    :func:`myogait_app.reliability.biomarker_table`.
    """
    colours = series_colors(dark)
    fig = go.Figure()
    for index, label in enumerate((group_a, group_b)):
        values = [r["value"] for r in rows
                  if r["parameter"] == parameter and r.get(by) == label]
        colour = colours[index % len(colours)]
        fig.add_trace(go.Box(
            y=values, name=label, boxpoints="all", jitter=0.35, pointpos=0,
            marker={"color": colour, "size": 6, "opacity": 0.7},
            line={"color": colour}, fillcolor=rgba(colour, 0.18),
            hovertemplate="%{y:.2f}<extra>" + label + "</extra>",
        ))
    fig.update_yaxes(title_text=parameter)
    fig.update_layout(showlegend=False)
    return apply(fig, dark, height=height)
