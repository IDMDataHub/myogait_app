"""Figures for a single analysis.

On these pages colour carries the *side*: left and right take the two
most separated slots of the palette, and nothing else in the figure is
allowed to use them. Everything else -- individual cycles, the normative
band, the grid -- is deliberately recessive so the two mean curves are
what the eye lands on.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..branding import BRANDING
from .theme import apply, rgba, series_colors, side_color

#: Sagittal joints, in the proximal-to-distal order clinicians read them.
SAGITTAL_JOINTS = ("hip", "knee", "ankle")
JOINT_LABELS = {
    "hip": "Hip",
    "knee": "Knee",
    "ankle": "Ankle",
    "trunk": "Trunk",
    "pelvis_obliquity": "Pelvis obliquity",
    "pelvis_list": "Pelvis list",
    "hip_adduction": "Hip adduction",
    "knee_valgus": "Knee valgus",
}

#: myogait stores per-frame angles under these keys.
_SIDE_SUFFIX = {"left": "L", "right": "R"}

#: Angles myogait stores once per frame rather than once per side --
#: "trunk" and "pelvis_obliquity" are not suffixed _L/_R the way
#: hip/knee/ankle are, so a plain f"{joint}_{side}" lookup silently finds
#: nothing for either. pelvis_obliquity only exists from myogait 0.8.0
#: (an honest rename of the frontal-plane value the historical
#: "pelvis_tilt" key already carried); the fallback covers older installs.
_GLOBAL_KEYS = {
    "trunk": ("trunk_angle",),
    "pelvis_obliquity": ("pelvis_obliquity", "pelvis_tilt"),
}


def _angle_series(data: dict, joint: str, side: str) -> tuple[np.ndarray, np.ndarray]:
    """Return (time_s, degrees) for one joint and side."""
    angles = (data or {}).get("angles") or {}
    frames = angles.get("frames") or []
    fps = float((data.get("meta") or {}).get("fps") or 30.0)
    key = f"{joint}_{_SIDE_SUFFIX.get(side, 'L')}"

    times, values = [], []
    for frame in frames:
        raw = frame.get(key)
        times.append(float(frame.get("frame_idx", 0)) / fps)
        values.append(np.nan if raw is None else float(raw))
    return np.asarray(times), np.asarray(values)


def _global_angle_series(data: dict, joint: str) -> tuple[np.ndarray, np.ndarray]:
    """Return (time_s, degrees) for a once-per-frame joint (see _GLOBAL_KEYS)."""
    angles = (data or {}).get("angles") or {}
    frames = angles.get("frames") or []
    fps = float((data.get("meta") or {}).get("fps") or 30.0)
    keys = _GLOBAL_KEYS.get(joint, (joint,))

    times, values = [], []
    for frame in frames:
        raw = next((frame.get(k) for k in keys if frame.get(k) is not None), None)
        times.append(float(frame.get("frame_idx", 0)) / fps)
        values.append(np.nan if raw is None else float(raw))
    return np.asarray(times), np.asarray(values)


def _event_frames(data: dict, kind: str, side: str) -> list[int]:
    events = (data or {}).get("events") or {}
    entries = events.get(f"{side}_{kind}") or []
    out = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("frame") is not None:
            out.append(int(entry["frame"]))
        elif isinstance(entry, (int, float)):
            out.append(int(entry))
    return out


def angle_timeline(
    data: dict,
    joints: tuple[str, ...] = SAGITTAL_JOINTS,
    sides: tuple[str, ...] = ("left", "right"),
    show_events: bool = True,
    dark: bool = False,
    height_per_joint: int = 190,
) -> go.Figure:
    """Joint angles against time, with gait events marked.

    One row per joint on a shared time axis, so a heel strike lines up
    across hip, knee and ankle -- the whole point of looking at the raw
    trace rather than the normalised cycle.
    """
    joints = tuple(joints) or SAGITTAL_JOINTS
    fig = make_subplots(
        rows=len(joints),
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        subplot_titles=[JOINT_LABELS.get(j, j.title()) for j in joints],
    )

    for row, joint in enumerate(joints, start=1):
        if joint in _GLOBAL_KEYS:
            # One value per frame, not per side (trunk_angle,
            # pelvis_obliquity) -- a side-coloured trace per side would
            # draw two identical overlapping lines and, worse, imply a
            # left/right difference that does not exist for this joint.
            times, values = _global_angle_series(data, joint)
            if len(times) and not np.all(np.isnan(values)):
                fig.add_trace(
                    go.Scatter(
                        x=times,
                        y=values,
                        name=JOINT_LABELS.get(joint, joint.title()),
                        legendgroup=joint,
                        showlegend=(row == 1),
                        mode="lines",
                        line=dict(color=BRANDING.accent, width=2),
                        hovertemplate="%{y:.1f}&deg;<extra>"
                        + JOINT_LABELS.get(joint, joint.title())
                        + "</extra>",
                    ),
                    row=row,
                    col=1,
                )
        else:
            for side in sides:
                times, values = _angle_series(data, joint, side)
                if not len(times) or np.all(np.isnan(values)):
                    continue
                fig.add_trace(
                    go.Scatter(
                        x=times,
                        y=values,
                        name=side.title(),
                        legendgroup=side,
                        showlegend=(row == 1),
                        mode="lines",
                        line=dict(color=side_color(side, dark), width=2),
                        hovertemplate="%{y:.1f}&deg;<extra>" + side.title() + "</extra>",
                    ),
                    row=row,
                    col=1,
                )
        fig.update_yaxes(title_text="deg", row=row, col=1)

    if show_events:
        _add_event_markers(fig, data, sides, len(joints), dark)

    fig.update_xaxes(title_text="Time (s)", row=len(joints), col=1)
    for annotation in fig.layout.annotations:
        annotation.font.size = 12
        annotation.font.color = BRANDING.ink_muted
        annotation.x = 0
        annotation.xanchor = "left"

    return apply(fig, dark, height=height_per_joint * len(joints) + 60)


def _add_event_markers(
    fig: go.Figure, data: dict, sides: tuple[str, ...], n_rows: int, dark: bool
) -> None:
    """Draw heel strikes as solid rules and toe offs as dotted ones.

    Events are shapes rather than traces: they are context for reading the
    curves, and putting them in the legend would imply they are data of
    the same kind.
    """
    fps = float((data.get("meta") or {}).get("fps") or 30.0)
    for side in sides:
        colour = side_color(side, dark)
        for kind, dash, opacity in (("hs", "solid", 0.45), ("to", "dot", 0.35)):
            for frame in _event_frames(data, kind, side):
                fig.add_vline(
                    x=frame / fps,
                    line=dict(color=colour, width=1, dash=dash),
                    opacity=opacity,
                )


def cycle_overlay(
    cycles: dict,
    joint: str = "knee",
    sides: tuple[str, ...] = ("left", "right"),
    show_individual: bool = True,
    show_sd: bool = True,
    normative: dict | None = None,
    dark: bool = False,
    height: int = 420,
) -> go.Figure:
    """Time-normalised cycles for one joint, mean +/- SD per side.

    Individual cycles are drawn thin and translucent underneath the mean.
    They are what tells you whether a tidy-looking mean is describing a
    consistent gait or averaging away a wide spread.
    """
    fig = go.Figure()
    percent = np.arange(101)
    summary = (cycles or {}).get("summary") or {}
    all_cycles = (cycles or {}).get("cycles") or []

    if normative:
        _add_normative_band(fig, normative, dark)

    for side in sides:
        colour = side_color(side, dark)
        side_summary = summary.get(side) or {}
        mean = side_summary.get(f"{joint}_mean")
        std = side_summary.get(f"{joint}_std")

        if show_individual:
            for cycle in all_cycles:
                if cycle.get("side") != side:
                    continue
                values = (cycle.get("angles_normalized") or {}).get(joint)
                if not values:
                    continue
                fig.add_trace(
                    go.Scatter(
                        x=percent[: len(values)],
                        y=values,
                        mode="lines",
                        line=dict(color=colour, width=1),
                        opacity=0.22,
                        showlegend=False,
                        hoverinfo="skip",
                        name=f"{side} cycle {cycle.get('cycle_id')}",
                    )
                )

        if not mean:
            continue

        mean_arr = np.asarray(mean, dtype=float)
        if show_sd and std:
            std_arr = np.asarray(std, dtype=float)
            fig.add_trace(
                go.Scatter(
                    x=np.concatenate([percent, percent[::-1]]),
                    y=np.concatenate([mean_arr + std_arr, (mean_arr - std_arr)[::-1]]),
                    fill="toself",
                    fillcolor=rgba(colour, 0.14),
                    line=dict(width=0),
                    hoverinfo="skip",
                    showlegend=False,
                    name=f"{side} SD",
                )
            )

        n_cycles = side_summary.get("n_cycles", 0)
        fig.add_trace(
            go.Scatter(
                x=percent,
                y=mean_arr,
                mode="lines",
                name=f"{side.title()} (n={n_cycles})",
                line=dict(color=colour, width=2.5),
                hovertemplate="%{y:.1f}&deg; at %{x}%<extra>" + side.title() + "</extra>",
            )
        )

    fig.update_xaxes(title_text="Gait cycle (%)", range=[0, 100], dtick=20)
    fig.update_yaxes(title_text=f"{JOINT_LABELS.get(joint, joint.title())} angle (deg)")
    return apply(fig, dark, height=height)


def _add_normative_band(fig: go.Figure, normative: dict, dark: bool) -> None:
    """Reference band, drawn achromatic and first so it sits behind."""
    lower = normative.get("lower")
    upper = normative.get("upper")
    mean = normative.get("mean")
    if not (lower and upper):
        return
    percent = np.arange(len(lower))
    fig.add_trace(
        go.Scatter(
            x=np.concatenate([percent, percent[::-1]]),
            y=np.concatenate([np.asarray(upper), np.asarray(lower)[::-1]]),
            fill="toself",
            fillcolor=rgba(BRANDING.normative, 0.16),
            line=dict(width=0),
            hoverinfo="skip",
            name="Normative +/-1 SD",
            showlegend=True,
        )
    )
    if mean:
        fig.add_trace(
            go.Scatter(
                x=percent,
                y=mean,
                mode="lines",
                line=dict(color=BRANDING.normative, width=1.5, dash="dash"),
                name="Normative mean",
                hovertemplate="%{y:.1f}&deg;<extra>Normative</extra>",
            )
        )


def rom_summary(cycles: dict, dark: bool = False, height: int = 340) -> go.Figure:
    """Range of motion per joint and side.

    Grouped bars rather than a table because the question here is
    comparative -- is one side moving less than the other -- and a length
    answers that faster than two numbers.
    """
    summary = (cycles or {}).get("summary") or {}
    joints = [j for j in SAGITTAL_JOINTS if any(
        (summary.get(s) or {}).get(f"{j}_mean") for s in ("left", "right")
    )]

    fig = go.Figure()
    for side in ("left", "right"):
        values = []
        for joint in joints:
            mean = (summary.get(side) or {}).get(f"{joint}_mean")
            values.append(
                float(np.nanmax(mean) - np.nanmin(mean)) if mean else np.nan
            )
        fig.add_trace(
            go.Bar(
                x=[JOINT_LABELS.get(j, j.title()) for j in joints],
                y=values,
                name=side.title(),
                marker=dict(
                    color=side_color(side, dark),
                    line=dict(width=2, color="rgba(0,0,0,0)"),
                ),
                hovertemplate="%{y:.1f}&deg;<extra>" + side.title() + "</extra>",
                text=[f"{v:.0f}&deg;" if np.isfinite(v) else "" for v in values],
                textposition="outside",
                textfont=dict(color=BRANDING.ink_muted, size=11),
            )
        )

    fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.08)
    fig.update_yaxes(title_text="ROM (deg)")
    return apply(fig, dark, height=height)


#: The components myogait breaks its coherence score into. Shown on
#: request because a low score alone does not say what went wrong --
#: a limb jumping between frames and a segment changing length are very
#: different extraction failures with different fixes.
COHERENCE_COMPONENTS = ("segment_stability", "velocity", "angular_continuity")


def _coherence_series(frames: list, key: str = "score") -> list[float]:
    """Pull one coherence component out of the per-frame dicts."""
    values = []
    for frame in frames:
        entry = frame.get("coherence")
        if isinstance(entry, dict):
            raw = entry.get(key)
            values.append(np.nan if raw is None else float(raw))
        elif isinstance(entry, (int, float)) and key == "score":
            values.append(float(entry))
        else:
            values.append(np.nan)
    return values


def quality_timeline(
    data: dict,
    show_components: bool = False,
    dark: bool = False,
    height: int = 260,
) -> go.Figure:
    """Per-frame detection confidence and biomechanical coherence.

    Both are diagnostics of the *extraction*, not of the gait, so they are
    kept off the kinematic figures and shown together here: a dip in one
    explains a suspicious excursion in the other.
    """
    frames = (data or {}).get("frames") or []
    fps = float((data.get("meta") or {}).get("fps") or 30.0)
    times = [float(f.get("frame_idx", i)) / fps for i, f in enumerate(frames)]
    slots = series_colors(dark)

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=times,
            y=[np.nan if f.get("confidence") is None else float(f["confidence"]) for f in frames],
            mode="lines",
            name="Detection confidence",
            line=dict(color=slots[0], width=2),
            hovertemplate="%{y:.2f}<extra>Confidence</extra>",
        )
    )

    score = _coherence_series(frames, "score")
    if any(np.isfinite(v) for v in score):
        fig.add_trace(
            go.Scatter(
                x=times,
                y=score,
                mode="lines",
                name="Frame coherence",
                line=dict(color=slots[2], width=2),
                hovertemplate="%{y:.2f}<extra>Coherence</extra>",
            )
        )
        if show_components:
            for index, component in enumerate(COHERENCE_COMPONENTS):
                values = _coherence_series(frames, component)
                if not any(np.isfinite(v) for v in values):
                    continue
                fig.add_trace(
                    go.Scatter(
                        x=times,
                        y=values,
                        mode="lines",
                        name=component.replace("_", " ").title(),
                        line=dict(color=slots[(index + 3) % len(slots)], width=1.5),
                        opacity=0.85,
                        hovertemplate="%{y:.2f}<extra>"
                        + component.replace("_", " ")
                        + "</extra>",
                    )
                )

    fig.update_yaxes(title_text="Score", range=[0, 1.02])
    fig.update_xaxes(title_text="Time (s)")
    return apply(fig, dark, height=height)


def stance_swing_bar(cycles: dict, dark: bool = False, height: int = 200) -> go.Figure:
    """Stance and swing share per side.

    A stacked pair with a 2px surface gap between the segments, so the
    boundary between stance and swing stays legible without a border.
    """
    entries = (cycles or {}).get("cycles") or []
    fig = go.Figure()
    rows, stance, swing = [], [], []
    for side in ("left", "right"):
        values = [
            c["stance_pct"] for c in entries
            if c.get("side") == side and c.get("stance_pct") is not None
        ]
        if not values:
            continue
        rows.append(side.title())
        stance.append(float(np.mean(values)))
        swing.append(100.0 - float(np.mean(values)))

    if not rows:
        return apply(go.Figure(), dark, height=height)

    for label, values, colour in (
        ("Stance", stance, BRANDING.accent),
        ("Swing", swing, BRANDING.accent_soft),
    ):
        fig.add_trace(
            go.Bar(
                y=rows,
                x=values,
                name=label,
                orientation="h",
                marker=dict(color=colour, line=dict(width=2, color="#fcfcfb" if not dark else "#1a1a19")),
                hovertemplate="%{x:.1f}%<extra>" + label + "</extra>",
                text=[f"{v:.1f}%" for v in values],
                textposition="inside",
                insidetextanchor="middle",
                textfont=dict(size=11),
            )
        )

    fig.update_layout(barmode="stack", bargap=0.45)
    fig.update_xaxes(title_text="% of cycle", range=[0, 100], dtick=20)
    return apply(fig, dark, height=height)
