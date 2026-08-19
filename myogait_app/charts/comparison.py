"""Figures for the comparator.

Here the entity carrying colour is the *model or method*, not the side.
So sides move to facets -- one column each -- and every series keeps the
same categorical slot in both columns. A model is the same colour
wherever it appears, and adding or removing one never repaints the
others, which is what makes two runs of the comparator comparable.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..branding import BRANDING
from .theme import apply, rgba, series_colors

#: Beyond this many series the categorical palette stops being able to
#: keep them apart. The interface offers faceting instead of inventing
#: a ninth hue.
MAX_SERIES = 8


def _mean_curve(cycles: dict, joint: str, side: str) -> np.ndarray | None:
    summary = (cycles or {}).get("summary") or {}
    values = (summary.get(side) or {}).get(f"{joint}_mean")
    return np.asarray(values, dtype=float) if values else None


def compare_cycles(
    series: dict[str, dict],
    joint: str = "knee",
    sides: tuple[str, ...] = ("left", "right"),
    reference: str | None = None,
    dark: bool = False,
    height: int = 420,
) -> go.Figure:
    """Overlay the mean cycle of several runs, one column per side.

    Parameters
    ----------
    series
        Ordered mapping of label -> the ``segment_cycles`` output for that
        run. Insertion order fixes the colour assignment.
    reference
        When given, that series is drawn thicker and every other one is
        read against it. Use it to pin the model you trust.
    """
    labels = list(series)[:MAX_SERIES]
    colours = series_colors(dark)
    percent = np.arange(101)

    fig = make_subplots(
        rows=1,
        cols=len(sides),
        shared_yaxes=True,
        horizontal_spacing=0.06,
        subplot_titles=[s.title() for s in sides],
    )

    for index, label in enumerate(labels):
        colour = colours[index % len(colours)]
        is_reference = label == reference
        for col, side in enumerate(sides, start=1):
            curve = _mean_curve(series[label], joint, side)
            if curve is None:
                continue
            fig.add_trace(
                go.Scatter(
                    x=percent[: len(curve)],
                    y=curve,
                    name=label,
                    legendgroup=label,
                    showlegend=(col == 1),
                    mode="lines",
                    line=dict(
                        color=colour,
                        width=3.0 if is_reference else 2.0,
                        dash="solid",
                    ),
                    hovertemplate="%{y:.1f}&deg; at %{x}%<extra>" + label + "</extra>",
                ),
                row=1,
                col=col,
            )

    fig.update_xaxes(title_text="Gait cycle (%)", range=[0, 100], dtick=25)
    fig.update_yaxes(title_text="Angle (deg)", row=1, col=1)
    for annotation in fig.layout.annotations:
        annotation.font.size = 12
        annotation.font.color = BRANDING.ink_muted

    return apply(fig, dark, height=height)


def difference_from_reference(
    series: dict[str, dict],
    reference: str,
    joint: str = "knee",
    side: str = "left",
    dark: bool = False,
    height: int = 300,
) -> go.Figure:
    """Point-by-point difference of each series against a reference.

    The overlay answers "do they agree"; this answers "where, and by how
    much". A flat line on zero is perfect agreement, and the shape of any
    departure says which phase of the cycle the models disagree about --
    which is usually far more informative than a single RMS number.
    """
    colours = series_colors(dark)
    base = _mean_curve(series.get(reference) or {}, joint, side)
    fig = go.Figure()

    if base is None:
        return apply(fig, dark, height=height)

    percent = np.arange(len(base))
    fig.add_hline(y=0, line=dict(color=BRANDING.axis, width=1))

    for index, label in enumerate(list(series)[:MAX_SERIES]):
        if label == reference:
            continue
        curve = _mean_curve(series[label], joint, side)
        if curve is None or len(curve) != len(base):
            continue
        fig.add_trace(
            go.Scatter(
                x=percent,
                y=curve - base,
                name=label,
                mode="lines",
                line=dict(color=colours[index % len(colours)], width=2),
                hovertemplate="%{y:+.1f}&deg; at %{x}%<extra>" + label + "</extra>",
            )
        )

    fig.update_xaxes(title_text="Gait cycle (%)", range=[0, 100], dtick=25)
    fig.update_yaxes(title_text=f"Difference vs {reference} (deg)")
    return apply(fig, dark, height=height)


def event_raster(
    events_by_method: dict[str, dict],
    side: str = "left",
    fps: float = 30.0,
    dark: bool = False,
    height: int | None = None,
) -> go.Figure:
    """When each detector places its events, on one shared time axis.

    Detectors are compared by *agreement*, and agreement is a spatial
    question: a vertical alignment of markers means the methods concur,
    a scatter means they do not. One row per method, heel strikes as
    filled marks and toe offs as open ones.
    """
    labels = list(events_by_method)[:MAX_SERIES]
    colours = series_colors(dark)
    fig = go.Figure()

    for index, label in enumerate(labels):
        events = events_by_method[label] or {}
        colour = colours[index % len(colours)]
        for kind, symbol, filled in (("hs", "circle", True), ("to", "circle-open", False)):
            frames = []
            for entry in events.get(f"{side}_{kind}") or []:
                if isinstance(entry, dict) and entry.get("frame") is not None:
                    frames.append(int(entry["frame"]))
                elif isinstance(entry, (int, float)):
                    frames.append(int(entry))
            if not frames:
                continue
            fig.add_trace(
                go.Scatter(
                    x=[f / fps for f in frames],
                    y=[label] * len(frames),
                    mode="markers",
                    name=f"{label} {kind.upper()}",
                    showlegend=False,
                    marker=dict(
                        color=colour,
                        size=10,
                        symbol=symbol,
                        line=dict(width=2, color=colour),
                    ),
                    hovertemplate=(
                        "%{x:.2f}s &middot; " + kind.upper() + "<extra>" + label + "</extra>"
                    ),
                )
            )

    fig.update_xaxes(title_text="Time (s)")
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(hovermode="closest")
    return apply(fig, dark, height=height or (60 + 42 * max(1, len(labels))))


def metric_bars(
    values: dict[str, float],
    label: str,
    unit: str = "",
    reference: str | None = None,
    dark: bool = False,
    height: int = 300,
) -> go.Figure:
    """One scalar metric across runs.

    Each bar keeps its series' categorical slot, so a metric chart and a
    curve chart on the same page identify the same run by the same colour.
    """
    colours = series_colors(dark)
    names = list(values)[:MAX_SERIES]
    fig = go.Figure(
        go.Bar(
            x=names,
            y=[values[n] for n in names],
            marker=dict(
                color=[colours[i % len(colours)] for i in range(len(names))],
                line=dict(width=2, color="rgba(0,0,0,0)"),
            ),
            hovertemplate="%{y:.2f}" + (f" {unit}" if unit else "") + "<extra>%{x}</extra>",
            text=[f"{values[n]:.2f}" for n in names],
            textposition="outside",
            textfont=dict(color=BRANDING.ink_muted, size=11),
            showlegend=False,
        )
    )

    if reference and reference in values:
        fig.add_hline(
            y=values[reference],
            line=dict(color=BRANDING.normative, width=1.5, dash="dash"),
            annotation_text=f"{reference}",
            annotation_position="top right",
            annotation_font=dict(color=BRANDING.ink_muted, size=11),
        )

    fig.update_yaxes(title_text=f"{label} ({unit})" if unit else label)
    fig.update_layout(bargap=0.45)
    return apply(fig, dark, height=height)


def agreement_heatmap(
    matrix: np.ndarray,
    labels: list[str],
    title: str = "RMS difference (deg)",
    dark: bool = False,
    height: int = 380,
) -> go.Figure:
    """Pairwise divergence between runs.

    Sequential single hue, light to dark: the value here is a magnitude
    with a meaningful zero, so it gets a magnitude encoding rather than
    the categorical slots used everywhere else on the page.
    """
    scale = [
        [0.00, "#cde2fb"],
        [0.25, "#86b6ef"],
        [0.50, "#3987e5"],
        [0.75, "#256abf"],
        [1.00, "#104281"],
    ]
    fig = go.Figure(
        go.Heatmap(
            z=matrix,
            x=labels,
            y=labels,
            colorscale=scale,
            hovertemplate="%{y} vs %{x}: %{z:.2f}&deg;<extra></extra>",
            colorbar=dict(
                title=dict(text="deg", font=dict(size=11, color=BRANDING.ink_muted)),
                tickfont=dict(size=10, color=BRANDING.ink_muted),
                thickness=12,
                outlinewidth=0,
            ),
            xgap=2,
            ygap=2,
        )
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(hovermode="closest")
    return apply(fig, dark, title=title, height=height)


def rms_matrix(series: dict[str, dict], joint: str, side: str) -> tuple[np.ndarray, list[str]]:
    """Pairwise RMS difference between the mean curves of each run."""
    labels = [
        label for label in series if _mean_curve(series[label], joint, side) is not None
    ]
    size = len(labels)
    matrix = np.full((size, size), np.nan)
    curves = [_mean_curve(series[label], joint, side) for label in labels]

    for i in range(size):
        for j in range(size):
            a, b = curves[i], curves[j]
            if a is None or b is None or len(a) != len(b):
                continue
            matrix[i, j] = float(np.sqrt(np.nanmean((a - b) ** 2)))
    return matrix, labels
