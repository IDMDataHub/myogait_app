"""A 4-section MoCap PDF report: kinematics, methodology + ISB compliance,
spatio-temporal parameters, range of motion (with the angle at heel-strike
and toe-off). Streamlit-free (matplotlib's own ``PdfPages``, the same tool
this app already uses for every other exported publication figure), and
source-kind-agnostic: it reads the same pivot ``data``/``cycles``/``stats``
every recording produces, video or C3D, since ``load_c3d`` projects a C3D
trial into the identical landmarks-per-frame schema a video extraction
produces (see CLAUDE.md's "C3D marker-convention resolution" section) --
so this report works unchanged for either.

Colour comes from ``branding.py``, the same rule as ``video_report.py``
(never a hardcoded hex of its own). The methodology section is generated
from the *actual* ``PipelineConfig`` this run used, not a fixed template --
the same "describe what happened, not what a config alone would imply"
principle the reproducibility panel (``codegen.py``) already follows.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages

from .branding import BRANDING
from .pipeline import PipelineConfig
from .video_report import SAGITTAL_JOINTS, JOINT_LABEL, _rom_and_events

_ASSETS = Path(__file__).parent / "assets"
_LOGO = _ASSETS / "logo_institut_myologie.png"
_PAGE = (11.69, 8.27)  # A4 landscape, inches

_SPATIOTEMPORAL_ROWS = (
    ("cadence_steps_per_min", "Cadence", "steps/min",
     "Steps per minute: 60 / mean step time, averaged over every segmented step."),
    ("stride_time_mean_s", "Stride time", "s",
     "Heel-strike to the next ipsilateral heel-strike, mean over every cycle."),
    ("step_time_mean_s", "Step time", "s",
     "Heel-strike to the following contralateral heel-strike."),
    ("stance_pct_left", "Stance (left)", "%",
     "Heel-strike to toe-off as a share of the left cycle."),
    ("stance_pct_right", "Stance (right)", "%",
     "Heel-strike to toe-off as a share of the right cycle."),
    ("swing_pct_left", "Swing (left)", "%", "The remainder of the left cycle after stance."),
    ("swing_pct_right", "Swing (right)", "%", "The remainder of the right cycle after stance."),
    ("double_support_pct", "Double support", "%",
     "Share of the cycle both feet are on the ground at once."),
)


def _fig():
    fig = plt.figure(figsize=_PAGE)
    fig.patch.set_facecolor(BRANDING.surface_light)
    return fig


def _logo_header(fig, title: str, subtitle: str = "") -> None:
    fig.text(0.06, 0.93, title, fontsize=22, fontweight="bold", color=BRANDING.ink_light)
    if subtitle:
        fig.text(0.06, 0.885, subtitle, fontsize=11, color=BRANDING.ink_muted_light)
    if _LOGO.is_file():
        try:
            img = mpimg.imread(str(_LOGO))
            ax = fig.add_axes((0.80, 0.90, 0.16, 0.08))
            ax.imshow(img)
            ax.axis("off")
        except Exception:
            pass
    fig.add_artist(plt.Line2D([0.06, 0.94], [0.865, 0.865], color=BRANDING.ink_light, linewidth=1.5,
                              transform=fig.transFigure))


def _footer(fig, page_label: str) -> None:
    fig.text(0.06, 0.03, "app myogait — MoCap report", fontsize=8, color=BRANDING.ink_muted_light)
    fig.text(0.94, 0.03, page_label, fontsize=8, color=BRANDING.ink_muted_light, ha="right")


# ── Data prep ────────────────────────────────────────────────────────

def _both_sides_rom(cycles: dict) -> dict:
    """{side: {"rom": {...}, "hs": {...}, "to": {...}, "n": int}}"""
    out = {}
    for side in ("LEFT", "RIGHT"):
        rom, hs, to, n = _rom_and_events(cycles, side)
        out[side] = {"rom": rom, "hs": hs, "to": to, "n": n}
    return out


# ── Section 1: kinematics ────────────────────────────────────────────

def _section_kinematics(pdf: PdfPages, data: dict, cycles: dict) -> None:
    fig = _fig()
    _logo_header(fig, "Joint kinematics", "Mean ± SD cycle curves, both sides, sagittal plane")
    summary = (cycles or {}).get("summary") or {}
    axes = [fig.add_axes(pos) for pos in ((0.07, 0.15, 0.27, 0.62), (0.385, 0.15, 0.27, 0.62),
                                           (0.70, 0.15, 0.27, 0.62))]
    percent = np.arange(101)
    side_colors = {"left": BRANDING.side_colors["left"], "right": BRANDING.side_colors["right"]}
    for ax, joint in zip(axes, SAGITTAL_JOINTS):
        for side in ("left", "right"):
            s = summary.get(side) or {}
            mean = s.get(f"{joint}_mean")
            std = s.get(f"{joint}_std")
            if not mean:
                continue
            mean = np.asarray(mean, dtype=float)
            color = side_colors[side]
            ax.plot(percent, mean, color=color, linewidth=2, label=side.title())
            if std:
                std = np.asarray(std, dtype=float)
                ax.fill_between(percent, mean - std, mean + std, color=color, alpha=0.15)
        ax.set_title(f"{JOINT_LABEL[joint]} flexion", fontsize=12, color=BRANDING.ink_light)
        ax.set_xlabel("Gait cycle (%)", fontsize=9)
        ax.set_ylabel("deg", fontsize=9)
        ax.axhline(0, color=BRANDING.grid, linewidth=0.8, zorder=0)
        ax.grid(True, color=BRANDING.grid, linewidth=0.6)
        ax.set_facecolor(BRANDING.surface_light_secondary)
        ax.legend(fontsize=8, frameon=False)
    _footer(fig, "1 · Kinematics")
    pdf.savefig(fig)
    plt.close(fig)


# ── Section 2: methodology + ISB compliance ──────────────────────────

def _methodology_lines(config: PipelineConfig, isb_tier: str | None) -> list[str]:
    a = config.angles
    lines = [
        f"Angle method: {a.method}, computed per frame from the tracked landmarks "
        "(hip = thigh vs trunk, knee = thigh vs shank, ankle = shank vs foot).",
    ]
    if a.calibrate:
        lines.append(
            f"Neutral calibration: on -- the first {a.calibration_frames} frames set each "
            "joint's zero offset (falls back to the whole-clip median when that window shows "
            "no meaningful motion, so a mid-stride start does not silently bias the zero)."
        )
    else:
        lines.append("Neutral calibration: off -- angles are reported as computed, uncalibrated.")
    lines.append(
        "Sign convention: flexion-positive, independent of walking direction "
        f"({'on' if a.canonicalize_signs else 'off'})."
    )
    if a.isb_reconstruction:
        tier_note = f" ({isb_tier})" if isb_tier else ""
        lines.append(
            "ISB reconstruction: on" + tier_note + " -- hip/knee/ankle are recomputed from proper "
            "ISB pelvis/thigh/shank/foot anatomical frames (Wu & Cavanagh 1995 / Wu et al. 2002 "
            "joint-coordinate-system convention) rather than this app's default sagittal, "
            "trunk-referenced 2-D projection. This is a different angle *definition*, not only "
            "added precision -- internal validation found the two methods correlate at r >= 0.99 "
            "in waveform shape but carry a constant 10-17 deg (hip) / 8-9 deg (knee) offset, "
            "traced to the reference segment. Ankle is closer between the two methods, since this "
            "app's default already recomputes ankle from 3-D marker positions when available."
        )
    else:
        lines.append(
            "ISB reconstruction: off -- hip/knee/ankle use this app's default sagittal-plane "
            "method (trunk-referenced 2-D projection), not full ISB anatomical frames."
        )
    if config.restore_ankle_dynamics:
        lines.append(
            "Ankle push-off restoration: on -- a calibrated deconvolution "
            "(myogait's restore_ankle_dynamics) that corrects markerless pose estimation's "
            "known under-reading of the fast ankle push-off, independent of gait shape."
        )
    return lines


def _section_methodology(pdf: PdfPages, config: PipelineConfig, isb_tier: str | None = None) -> None:
    fig = _fig()
    _logo_header(fig, "Methodology & ISB compliance",
                "What was actually computed for this recording, not a generic description")
    y = 0.78
    for line in _methodology_lines(config, isb_tier):
        fig.text(0.07, y, "•", fontsize=11, color=BRANDING.accent_mark)
        fig.text(0.095, y, line, fontsize=10.5, color=BRANDING.ink_light, wrap=True, va="top",
                 transform=fig.transFigure)
        # crude wrap-aware spacing: long lines need more vertical room
        y -= 0.05 + 0.018 * (len(line) // 92)
    fig.text(
        0.07, y - 0.03,
        "ISB (International Society of Biomechanics) standardises joint coordinate systems so an "
        "angle reported by one lab means the same thing in another: a right-handed anatomical "
        "frame per segment (pelvis, thigh, shank, foot), flexion/extension about the frame's "
        "mediolateral axis, and joint angles read as the distal segment's orientation relative to "
        "the proximal one. The ISB reconstruction path above follows this convention directly; the "
        "default sagittal method approximates the same flexion/extension angle from a single "
        "camera's 2-D projection, which is why the two agree closely in waveform shape but not in "
        "absolute offset.",
        fontsize=9.5, color=BRANDING.ink_muted_light, wrap=True, va="top", transform=fig.transFigure,
    )
    _footer(fig, "2 · Methodology")
    pdf.savefig(fig)
    plt.close(fig)


# ── Section 3: spatio-temporal parameters ────────────────────────────

def _section_spatiotemporal(pdf: PdfPages, stats: dict) -> None:
    fig = _fig()
    _logo_header(fig, "Spatio-temporal parameters", "From heel-strike / toe-off timing across every segmented cycle")
    st = (stats or {}).get("spatiotemporal") or {}
    step = (stats or {}).get("step_length") or {}
    rows = []
    for key, label, unit, note in _SPATIOTEMPORAL_ROWS:
        val = st.get(key)
        rows.append((label, f"{val:.1f} {unit}" if val is not None else "--", note))
    if step.get("unit") == "m":
        for side in ("left", "right"):
            val = step.get(f"step_length_{side}")
            rows.append((f"Step length ({side})", f"{val:.2f} m" if val is not None else "--",
                        "Antero-posterior distance between the heels at heel-strike."))
    ax = fig.add_axes((0.06, 0.10, 0.88, 0.72))
    ax.axis("off")
    table = ax.table(
        cellText=[[r[0], r[1], r[2]] for r in rows],
        colLabels=["Parameter", "Value", "How it is computed"],
        colWidths=[0.22, 0.14, 0.64], loc="upper left", cellLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1, 1.9)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor(BRANDING.grid)
        if r == 0:
            cell.set_facecolor(BRANDING.ink_light)
            cell.set_text_props(color=BRANDING.surface_light, fontweight="bold")
        else:
            cell.set_facecolor(BRANDING.surface_light_secondary if r % 2 else BRANDING.surface_light)
    _footer(fig, "3 · Spatio-temporal")
    pdf.savefig(fig)
    plt.close(fig)


# ── Section 4: range of motion ────────────────────────────────────────

def _section_rom(pdf: PdfPages, cycles: dict) -> None:
    fig = _fig()
    _logo_header(fig, "Range of motion", "Peak-to-peak per cycle, plus the angle at heel-strike and toe-off")
    both = _both_sides_rom(cycles)
    rows = []
    for side_key, side_label in (("LEFT", "Left"), ("RIGHT", "Right")):
        d = both[side_key]
        for joint in SAGITTAL_JOINTS:
            rom = d["rom"].get(joint)
            hs = d["hs"].get(joint)
            to = d["to"].get(joint)
            if rom is None:
                continue
            rows.append([
                side_label, JOINT_LABEL[joint], f"{rom:.1f}°",
                f"{hs:.1f}°" if hs is not None else "--",
                f"{to:.1f}°" if to is not None else "--",
                str(d["n"]),
            ])
    ax = fig.add_axes((0.06, 0.10, 0.88, 0.72))
    ax.axis("off")
    table = ax.table(
        cellText=rows,
        colLabels=["Side", "Joint", "RoM", "At heel-strike", "At toe-off", "Cycles"],
        colWidths=[0.14, 0.16, 0.16, 0.20, 0.18, 0.16], loc="upper left", cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2.0)
    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor(BRANDING.grid)
        if r == 0:
            cell.set_facecolor(BRANDING.ink_light)
            cell.set_text_props(color=BRANDING.surface_light, fontweight="bold")
        else:
            cell.set_facecolor(BRANDING.surface_light_secondary if r % 2 else BRANDING.surface_light)
    fig.text(
        0.06, 0.16,
        "Heel-strike is 0% of the cycle by definition; toe-off is read at that cycle's own "
        "stance-percentage mark. Both are the already cycle-normalised curve myogait's "
        "segment_cycles produces, averaged over every cycle on that side -- no separate "
        "computation.", fontsize=8.5, color=BRANDING.ink_muted_light, wrap=True, va="top",
        transform=fig.transFigure,
    )
    _footer(fig, "4 · Range of motion")
    pdf.savefig(fig)
    plt.close(fig)


# ── Entry point ──────────────────────────────────────────────────────

def render_mocap_report(
    data: dict,
    cycles: dict,
    stats: dict,
    config: PipelineConfig,
    out_path: str,
    isb_tier: str | None = None,
) -> Path:
    """Write the 4-section PDF to *out_path* and return it.

    *config* is the ``PipelineConfig`` that actually produced *data*/
    *cycles*/*stats* -- the methodology section describes what ran, not a
    generic template (see ``_methodology_lines``). *isb_tier* is an
    optional extra ("tier1"/"tier2"/"tier3"), since which ISB calibration
    tier ran depends on files attached at C3D load time that this
    function's other inputs do not carry on their own.
    """
    with PdfPages(str(out_path)) as pdf:
        _section_kinematics(pdf, data, cycles)
        _section_methodology(pdf, config, isb_tier)
        _section_spatiotemporal(pdf, stats)
        _section_rom(pdf, cycles)
    return Path(out_path)
