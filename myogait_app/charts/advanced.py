"""Figures for the advanced-analysis functions.

These functions each return arrays rather than the flat metric blocks the
rest of the app renders as tables, so each one gets a small dedicated
chart here rather than a generic dict-to-dataframe flatten.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .theme import apply, series_colors, side_color


def cadence_timeline(result: dict, dark: bool = False, height: int = 280) -> go.Figure:
    """Instantaneous cadence over time, from instantaneous_cadence()."""
    times = result.get("times") or []
    cadence = result.get("cadence") or []
    mean = result.get("mean")
    slots = series_colors(dark)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=times, y=cadence, mode="lines+markers", name="Instantaneous cadence",
            line=dict(color=slots[0], width=1.5), marker=dict(size=5),
            hovertemplate="%{y:.1f} steps/min<extra></extra>",
        )
    )
    if mean is not None and times:
        fig.add_hline(
            y=mean, line=dict(color=slots[2], width=1.5, dash="dash"),
            annotation_text=f"mean {mean:.1f}", annotation_position="top left",
        )
    fig.update_xaxes(title_text="Time (s)")
    fig.update_yaxes(title_text="Cadence (steps/min)")
    return apply(fig, dark, height=height)


def com_timeline(result: dict, fps: float, dark: bool = False, height: int = 280) -> go.Figure:
    """Centre-of-mass X/Y trajectory over time, from estimate_center_of_mass()."""
    com_x = result.get("com_x") or []
    com_y = result.get("com_y") or []
    times = [i / fps for i in range(len(com_x))]
    slots = series_colors(dark)

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                         subplot_titles=("Horizontal (progression)", "Vertical"))
    fig.add_trace(
        go.Scatter(x=times, y=com_x, mode="lines", name="CoM x",
                    line=dict(color=slots[0], width=1.5)),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=times, y=com_y, mode="lines", name="CoM y",
                    line=dict(color=slots[2], width=1.5)),
        row=2, col=1,
    )
    fig.update_yaxes(title_text="norm. x", row=1, col=1)
    fig.update_yaxes(title_text="norm. y", row=2, col=1)
    fig.update_xaxes(title_text="Time (s)", row=2, col=1)
    for annotation in fig.layout.annotations:
        annotation.font.size = 12
    return apply(fig, dark, height=height)


def sway_scatter(result: dict, dark: bool = False, height: int = 340) -> go.Figure:
    """Centre-of-pressure path from postural_sway()."""
    cop_x = result.get("cop_x") or []
    cop_y = result.get("cop_y") or []
    slots = series_colors(dark)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=cop_x, y=cop_y, mode="lines+markers", name="COP path",
            line=dict(color=slots[0], width=1, dash="dot"),
            marker=dict(size=3, color=slots[0]),
            hovertemplate="x=%{x:.4f}, y=%{y:.4f}<extra></extra>",
        )
    )
    fig.update_xaxes(title_text="Mediolateral (norm. x)")
    fig.update_yaxes(title_text="Antero-posterior (norm. y)", scaleanchor="x", scaleratio=1)
    return apply(fig, dark, height=height)


def derivatives_timeline(
    velocity: dict,
    acceleration: dict | None,
    fps: float,
    joints: tuple[str, ...],
    order: str = "velocity",
    dark: bool = False,
    height: int = 300,
) -> go.Figure:
    """Angular velocity or acceleration over time, from compute_derivatives()."""
    source = velocity if order == "velocity" else (acceleration or {})
    unit = "deg/s" if order == "velocity" else "deg/s²"
    slots = series_colors(dark)

    fig = go.Figure()
    for i, joint in enumerate(joints):
        values = source.get(joint)
        if values is None:
            continue
        values = np.asarray(values)
        times = np.arange(len(values)) / fps
        side = "left" if joint.endswith("_L") else "right"
        colour = side_color(side, dark) if joint.split("_")[0] in ("hip", "knee", "ankle") else slots[i % len(slots)]
        fig.add_trace(
            go.Scatter(
                x=times, y=values, mode="lines", name=joint,
                line=dict(color=colour, width=1.5),
                hovertemplate="%{y:.1f}" + unit + "<extra>" + joint + "</extra>",
            )
        )
    fig.update_xaxes(title_text="Time (s)")
    fig.update_yaxes(title_text=unit)
    return apply(fig, dark, height=height)


def spectrogram(result: dict, dark: bool = False, height: int = 340) -> go.Figure:
    """Time-frequency power heatmap for one joint, from time_frequency_analysis()."""
    power = np.asarray(result.get("power"))
    frequencies = np.asarray(result.get("frequencies"))
    times = np.asarray(result.get("times"))
    dominant = result.get("dominant_frequency")

    fig = go.Figure(
        data=go.Heatmap(
            z=power, x=times, y=frequencies, colorscale="Viridis",
            colorbar=dict(title="Power"),
            hovertemplate="t=%{x:.2f}s, f=%{y:.2f}Hz<extra></extra>",
        )
    )
    if dominant is not None:
        fig.add_hline(
            y=dominant, line=dict(color="white", width=1, dash="dot"),
            annotation_text=f"dominant {dominant:.2f} Hz", annotation_position="right",
        )
    fig.update_xaxes(title_text="Time (s)")
    fig.update_yaxes(title_text="Frequency (Hz)")
    return apply(fig, dark, height=height)


def pca_components(result: dict, dark: bool = False, height: int = 320) -> go.Figure:
    """Mean waveform +/- each retained principal component, from pca_waveform_analysis()."""
    mean = np.asarray(result.get("mean"))
    components = np.asarray(result.get("components"))
    explained = result.get("explained_variance_ratio")
    slots = series_colors(dark)
    percent = np.linspace(0, 100, len(mean))

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=percent, y=mean, mode="lines", name="Mean",
                    line=dict(color=slots[0], width=2.5))
    )
    for i in range(components.shape[0]):
        variance = explained[i] * 100 if explained is not None else None
        scale = float(np.std(mean)) if np.std(mean) > 0 else 1.0
        label = f"PC{i + 1}" + (f" ({variance:.0f}% var)" if variance is not None else "")
        fig.add_trace(
            go.Scatter(
                x=percent, y=mean + components[i] * scale, mode="lines", name=f"{label} +",
                line=dict(color=slots[(i + 2) % len(slots)], width=1, dash="dot"),
                opacity=0.7,
            )
        )
    fig.update_xaxes(title_text="Gait cycle (%)", range=[0, 100])
    fig.update_yaxes(title_text="Angle (deg)")
    return apply(fig, dark, height=height)
