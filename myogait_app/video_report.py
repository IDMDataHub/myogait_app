"""Animated MP4 report: the source video, its markerless skeleton, and this
run's own kinematics/spatio-temporal/RoM results, narrated over five staged
segments with the same storyboard shape as the pedagogical video this module
is modelled on (intro -> angles -> spatio-temporal -> RoM -> summary).

Streamlit-free and testable, following the pattern of ``autoconfig.py``/
``calibration.py``/``step_length.py``: pure computation (here, pure pixel
computation) driven entirely by a pivot ``data`` dict, ``cycles`` and
``stats`` -- the same three objects every other export already works from.
No IMU, no virtual accelerometer, no biomarker cohort: those three segments
of the original pedagogical script have no equivalent in a normal
``app_myogait`` run, so segments 3-5 are re-purposed to what this app
*does* compute for every recording -- spatio-temporal parameters, range of
motion (plus the angle at heel-strike/toe-off), and a comparison against
the normative band already used throughout the app (``clinical.
normative_bands``).

Colour and type come from ``branding.py`` (this app's own validated
palette) rather than the source script's own hardcoded Bauhaus hexes and
Windows-only Century Gothic font -- see CLAUDE.md's "Charts and colour"
section for why colour is never hardcoded a second time. The bundled
JetBrains Mono files (``assets/fonts/``, OFL-licensed) are what the app's
own web chrome already uses, so the video reads as the same identity
rather than a second, parallel one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .branding import BRANDING
from .clinical import normative_bands, select_stratum

_ASSETS = Path(__file__).parent / "assets"
_FONTS = _ASSETS / "fonts"

#: Output video geometry -- matches the pedagogical script's own canvas so a
#: side-by-side comparison of the two looks like the same family of output.
W_OUT, H_OUT = 1920, 1080
FPS_OUT = 30

#: Left video panel / right info panel split.
VID_X, VID_W = 16, 608
RX0 = VID_X + VID_W + 40
RX1 = 1900

#: The landmark set every myogait pose backend's pivot schema carries.
LANDMARK_NAMES = (
    "NOSE", "LEFT_EYE", "RIGHT_EYE", "LEFT_SHOULDER", "RIGHT_SHOULDER",
    "LEFT_ELBOW", "RIGHT_ELBOW", "LEFT_WRIST", "RIGHT_WRIST",
    "LEFT_HIP", "RIGHT_HIP", "LEFT_KNEE", "RIGHT_KNEE",
    "LEFT_ANKLE", "RIGHT_ANKLE", "LEFT_HEEL", "RIGHT_HEEL",
    "LEFT_FOOT_INDEX", "RIGHT_FOOT_INDEX",
)
BONES = (
    ("LEFT_SHOULDER", "RIGHT_SHOULDER"), ("LEFT_HIP", "RIGHT_HIP"),
    ("LEFT_SHOULDER", "LEFT_HIP"), ("RIGHT_SHOULDER", "RIGHT_HIP"),
    ("LEFT_SHOULDER", "LEFT_ELBOW"), ("LEFT_ELBOW", "LEFT_WRIST"),
    ("RIGHT_SHOULDER", "RIGHT_ELBOW"), ("RIGHT_ELBOW", "RIGHT_WRIST"),
    ("LEFT_HIP", "LEFT_KNEE"), ("LEFT_KNEE", "LEFT_ANKLE"),
    ("LEFT_ANKLE", "LEFT_HEEL"), ("LEFT_HEEL", "LEFT_FOOT_INDEX"),
    ("LEFT_ANKLE", "LEFT_FOOT_INDEX"),
    ("RIGHT_HIP", "RIGHT_KNEE"), ("RIGHT_KNEE", "RIGHT_ANKLE"),
    ("RIGHT_ANKLE", "RIGHT_HEEL"), ("RIGHT_HEEL", "RIGHT_FOOT_INDEX"),
    ("RIGHT_ANKLE", "RIGHT_FOOT_INDEX"),
)
JOINTS_DRAWN = (
    "LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW",
    "LEFT_WRIST", "RIGHT_WRIST", "LEFT_HIP", "RIGHT_HIP",
    "LEFT_KNEE", "RIGHT_KNEE", "LEFT_ANKLE", "RIGHT_ANKLE",
    "LEFT_HEEL", "RIGHT_HEEL", "LEFT_FOOT_INDEX", "RIGHT_FOOT_INDEX",
)
SAGITTAL_JOINTS = ("hip", "knee", "ankle")
JOINT_LABEL = {"hip": "Hip", "knee": "Knee", "ankle": "Ankle"}


def hx(h: str) -> tuple[int, int, int]:
    """'#RRGGBB' -> BGR tuple (OpenCV's native channel order)."""
    h = h.lstrip("#")
    return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))


def rgb(bgr: tuple[int, int, int]) -> tuple[int, int, int]:
    return (bgr[2], bgr[1], bgr[0])


# ── Palette, drawn from branding.py -- never a hardcoded hex of its own ──

def _palette() -> dict:
    b = BRANDING
    return {
        "bg": hx(b.surface_light),
        "card": hx(b.surface_light_secondary),
        "card2": hx(b.surface_light_secondary),
        "border": hx(b.ink_light),
        "text": hx(b.ink_light),
        "muted": hx(b.ink_muted_light),
        "grid": hx(b.grid),
        "accent": hx(b.accent),
        "accent_mark": hx(b.accent_mark),
        "blue": hx(b.primary_blue),
        "red": hx(b.primary_red),
        # Per-joint triad for the angle panel: the categorical slots, same
        # ones the Comparator uses for "more than one series, side is not
        # the entity" -- here the entity is the joint, not the side (only
        # one side is visible in a lateral 2-D video at a time).
        "joint": {
            "hip": hx(b.categorical[0]), "knee": hx(b.categorical[1]),
            "ankle": hx(b.categorical[2]),
        },
    }


def _fonts() -> dict:
    reg = str(_FONTS / "JetBrainsMono-Regular.ttf")
    bold = str(_FONTS / "JetBrainsMono-Bold.ttf")
    return {
        "title": ImageFont.truetype(bold, 46),
        "sub": ImageFont.truetype(reg, 24),
        "h2": ImageFont.truetype(bold, 26),
        "h3": ImageFont.truetype(bold, 20),
        "body": ImageFont.truetype(reg, 19),
        "small": ImageFont.truetype(reg, 16),
        "tiny": ImageFont.truetype(reg, 13),
        "num": ImageFont.truetype(bold, 34),
        "chip": ImageFont.truetype(bold, 16),
    }


# ── Easing / fades ────────────────────────────────────────────────────

def ease(t: float, t0: float, dur: float) -> float:
    u = np.clip((t - t0) / max(dur, 1e-6), 0, 1)
    return float(u * u * (3 - 2 * u))


def fade_io(t: float, t_in: float, d_in: float, t_out: float, d_out: float) -> float:
    return min(ease(t, t_in, d_in), 1 - ease(t, t_out, d_out))


# ── Data extraction (pure, no drawing) ───────────────────────────────

@dataclass
class VideoReportData:
    """Everything a segment renderer needs, computed once up front."""

    landmarks: np.ndarray          # (n_frames, n_landmarks, 3) x,y,vis
    fps_src: float
    side: str                      # "LEFT" or "RIGHT"
    angle_t: np.ndarray            # seconds, one per angle frame
    angles: dict                   # {"hip": arr, "knee": arr, "ankle": arr}
    spatiotemporal: dict
    rom_deg: dict                  # {joint: rom_value}
    at_heel_strike: dict           # {joint: angle_deg}
    at_toe_off: dict               # {joint: angle_deg}
    normative: dict                # {joint: {lower, upper, mean}} or {}
    model_name: str
    n_cycles: int


def _landmark_array(data: dict) -> np.ndarray:
    frames = data.get("frames") or []
    n = len(frames)
    arr = np.full((max(n, 1), len(LANDMARK_NAMES), 3), np.nan)
    for i, f in enumerate(frames):
        lms = f.get("landmarks") or {}
        for k, name in enumerate(LANDMARK_NAMES):
            lm = lms.get(name)
            if lm is not None:
                arr[i, k, 0] = lm["x"]
                arr[i, k, 1] = lm["y"]
                arr[i, k, 2] = lm.get("visibility", 1.0)
    return arr


def _pick_side(landmarks: np.ndarray) -> str:
    idx = {n: i for i, n in enumerate(LANDMARK_NAMES)}
    def vis(side: str) -> float:
        ks = [idx[f"{side}_HIP"], idx[f"{side}_KNEE"], idx[f"{side}_ANKLE"]]
        return float(np.nanmean(landmarks[:, ks, 2]))
    return "LEFT" if vis("LEFT") >= vis("RIGHT") else "RIGHT"


def _angle_series(data: dict, side: str) -> tuple[np.ndarray, dict]:
    frames = ((data.get("angles") or {}).get("frames")) or []
    fps = float((data.get("meta") or {}).get("fps") or 30.0)
    suffix = "_L" if side == "LEFT" else "_R"
    t = np.array([f.get("frame_idx", i) / fps for i, f in enumerate(frames)])
    out = {}
    for joint in SAGITTAL_JOINTS:
        key = f"{joint}{suffix}"
        out[joint] = np.array([_finite(f.get(key)) for f in frames])
    return t, out


def _finite(v) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return float("nan")
    return v if math.isfinite(v) else float("nan")


def _rom_and_events(cycles: dict, side: str) -> tuple[dict, dict, dict, int]:
    """RoM plus the angle at heel-strike (0% of cycle) and toe-off

    (``stance_pct``% of cycle) for *side*, averaged over that side's
    segmented cycles -- both are direct reads of the already
    cycle-normalised curve myogait's own ``segment_cycles`` produces, no
    new computation.
    """
    side_key = side.lower()
    all_cycles = [c for c in (cycles or {}).get("cycles", []) if c.get("side") == side_key]
    rom: dict[str, float] = {}
    hs: dict[str, float] = {}
    to: dict[str, float] = {}
    for joint in SAGITTAL_JOINTS:
        hs_vals, to_vals, rom_vals = [], [], []
        for c in all_cycles:
            curve = (c.get("angles_normalized") or {}).get(joint)
            if not curve or len(curve) != 101:
                continue
            arr = np.asarray(curve, dtype=float)
            if not np.isfinite(arr).any():
                continue
            hs_vals.append(arr[0])
            stance_idx = int(round(np.clip(c.get("stance_pct", 60.0), 0, 100)))
            to_vals.append(arr[stance_idx])
            rom_vals.append(float(np.nanmax(arr) - np.nanmin(arr)))
        if rom_vals:
            rom[joint] = float(np.mean(rom_vals))
            hs[joint] = float(np.mean(hs_vals))
            to[joint] = float(np.mean(to_vals))
    return rom, hs, to, len(all_cycles)


def prepare(data: dict, cycles: dict, stats: dict) -> VideoReportData:
    landmarks = _landmark_array(data)
    side = _pick_side(landmarks)
    fps_src = float((data.get("meta") or {}).get("fps") or 30.0)
    angle_t, angles = _angle_series(data, side)
    rom, hs, to, n_cycles = _rom_and_events(cycles, side)
    stratum = select_stratum((data.get("subject") or {}).get("age"))
    return VideoReportData(
        landmarks=landmarks,
        fps_src=fps_src,
        side=side,
        angle_t=angle_t,
        angles=angles,
        spatiotemporal=dict((stats or {}).get("spatiotemporal") or {}),
        rom_deg=rom,
        at_heel_strike=hs,
        at_toe_off=to,
        normative=normative_bands(SAGITTAL_JOINTS, stratum),
        model_name=str((data.get("extraction") or {}).get("model") or "unknown"),
        n_cycles=n_cycles,
    )


# ── Drawing primitives ───────────────────────────────────────────────
#
# A frame is drawn in two passes: shapes straight onto the BGR canvas
# (OpenCV, fast), then every piece of text queued via ``put`` is flushed
# in one PIL layer at the end (``flush_texts``) -- OpenCV has no
# anti-aliased proportional-font text renderer, PIL does, and compositing
# once per frame instead of once per string is what keeps this at a
# usable frame rate.

class Scene:
    """One frame's mutable canvas plus its queued text, so segment
    renderers do not each need to thread a text list through every call.
    """

    def __init__(self, pal: dict, fonts: dict):
        self.canvas = np.empty((H_OUT, W_OUT, 3), np.uint8)
        self.canvas[:] = pal["bg"]
        self.pal = pal
        self.fonts = fonts
        self.texts: list = []

    def put(self, x, y, txt, font="body", color=None, alpha=1.0, anchor="la"):
        if alpha <= 0.02 or not txt:
            return
        color = color if color is not None else self.pal["text"]
        self.texts.append((x, y, txt, self.fonts[font], rgb(color), alpha, anchor))

    def flush(self):
        if not self.texts:
            return
        layer = Image.new("RGBA", (W_OUT, H_OUT), (0, 0, 0, 0))
        dr = ImageDraw.Draw(layer)
        for (x, y, txt, font, col, a, anchor) in self.texts:
            dr.text((x, y), txt, font=font, fill=col + (int(255 * a),), anchor=anchor)
        arr = np.asarray(layer)
        a = arr[:, :, 3:4].astype(np.float32) / 255.0
        fg = arr[:, :, [2, 1, 0]].astype(np.float32)
        self.canvas = (fg * a + self.canvas.astype(np.float32) * (1 - a)).astype(np.uint8)
        self.texts = []


def rrect(canvas, x0, y0, x1, y1, color, alpha=1.0, border=None, thickness=-1):
    if alpha <= 0.02 or x1 <= x0 or y1 <= y0:
        return
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, W_OUT), min(y1, H_OUT)
    if x1 <= x0 or y1 <= y0:
        return
    sub = canvas[y0:y1, x0:x1]
    ov = sub.copy()
    h, w = ov.shape[:2]
    cv2.rectangle(ov, (0, 0), (w - 1, h - 1), color, thickness)
    if border is not None:
        cv2.rectangle(ov, (0, 0), (w - 1, h - 1), border, 2)
    cv2.addWeighted(ov, alpha, sub, 1 - alpha, 0, sub)


def line_a(canvas, p0, p1, color, thickness, alpha=1.0):
    if alpha <= 0.02:
        return
    x0 = max(min(p0[0], p1[0]) - thickness - 2, 0)
    y0 = max(min(p0[1], p1[1]) - thickness - 2, 0)
    x1 = min(max(p0[0], p1[0]) + thickness + 2, W_OUT)
    y1 = min(max(p0[1], p1[1]) + thickness + 2, H_OUT)
    if x1 <= x0 or y1 <= y0:
        return
    sub = canvas[y0:y1, x0:x1]
    ov = sub.copy()
    cv2.line(ov, (p0[0] - x0, p0[1] - y0), (p1[0] - x0, p1[1] - y0), color, thickness, cv2.LINE_AA)
    cv2.addWeighted(ov, alpha, sub, 1 - alpha, 0, sub)


def circle_a(canvas, c, r, color, thickness, alpha=1.0):
    if alpha <= 0.02:
        return
    x0 = max(c[0] - r - thickness - 2, 0)
    y0 = max(c[1] - r - thickness - 2, 0)
    x1 = min(c[0] + r + thickness + 2, W_OUT)
    y1 = min(c[1] + r + thickness + 2, H_OUT)
    if x1 <= x0 or y1 <= y0:
        return
    sub = canvas[y0:y1, x0:x1]
    ov = sub.copy()
    cv2.circle(ov, (c[0] - x0, c[1] - y0), r, color, thickness, cv2.LINE_AA)
    cv2.addWeighted(ov, alpha, sub, 1 - alpha, 0, sub)


def vid_px(pt) -> tuple[int, int]:
    return (VID_X + int(pt[0] * VID_W), int(pt[1] * H_OUT))


_BONE_HEAD = {"LEFT_EYE", "RIGHT_EYE", "NOSE"}


def draw_skeleton(canvas, pal, landmarks, j: float, alpha=1.0, stagger: float | None = None,
                   color=None):
    """*stagger*: 0..1 cascade progression, top of the body first."""
    if alpha <= 0.02:
        return
    color = color if color is not None else pal["blue"]
    idx = {n: i for i, n in enumerate(LANDMARK_NAMES)}
    i = int(np.clip(j, 0, landmarks.shape[0] - 1))
    y0, y1 = np.nanmin(landmarks[:, :, 1]), np.nanmax(landmarks[:, :, 1])
    span = max(y1 - y0, 1e-6)

    def rank(name_a, name_b):
        ya = landmarks[i, idx[name_a], 1]
        yb = landmarks[i, idx[name_b], 1]
        m = np.nanmean([ya, yb])
        return float(np.clip((m - y0) / span, 0, 1)) if np.isfinite(m) else 1.0

    x0r, y0r = VID_X, 0
    ov = canvas[y0r:H_OUT, x0r:x0r + VID_W].copy()
    for (a, b) in BONES:
        pa, pb = landmarks[i, idx[a], :2], landmarks[i, idx[b], :2]
        if not (np.all(np.isfinite(pa)) and np.all(np.isfinite(pb))):
            continue
        ba = alpha
        if stagger is not None:
            r = rank(a, b)
            ba = alpha * float(np.clip((stagger - r * 0.75) / 0.25, 0, 1))
            if ba <= 0.02:
                continue
        qa = (int(pa[0] * VID_W), int(pa[1] * H_OUT))
        qb = (int(pb[0] * VID_W), int(pb[1] * H_OUT))
        cv2.line(ov, qa, qb, pal["card"], 7, cv2.LINE_AA)
        cv2.line(ov, qa, qb, color, 3, cv2.LINE_AA)
    for name in JOINTS_DRAWN:
        p = landmarks[i, idx[name], :2]
        if not np.all(np.isfinite(p)):
            continue
        if stagger is not None:
            r = float(np.clip((p[1] - y0) / span, 0, 1))
            if stagger - r * 0.75 < 0:
                continue
        q = (int(p[0] * VID_W), int(p[1] * H_OUT))
        cv2.circle(ov, q, 6, pal["card"], -1, cv2.LINE_AA)
        cv2.circle(ov, q, 4, color, -1, cv2.LINE_AA)
    pe = np.nanmean([landmarks[i, idx["LEFT_EYE"], :2], landmarks[i, idx["RIGHT_EYE"], :2]], axis=0)
    if np.all(np.isfinite(pe)) and (stagger is None or stagger > 0.05):
        q = (int(pe[0] * VID_W), int(pe[1] * H_OUT + 8))
        cv2.circle(ov, q, 16, pal["card"], 5, cv2.LINE_AA)
        cv2.circle(ov, q, 16, color, 2, cv2.LINE_AA)
    ga = alpha if stagger is None else alpha * min(1.0, stagger * 3)
    sub = canvas[y0r:H_OUT, x0r:x0r + VID_W]
    cv2.addWeighted(ov, ga, sub, 1 - ga, 0, sub)


def draw_angle_arc(scene: Scene, landmarks, j, joint, alpha, color, label):
    idx = {n: i for i, n in enumerate(LANDMARK_NAMES)}
    i = int(np.clip(j, 0, landmarks.shape[0] - 1))
    if joint == "hip":
        b, a, c = "LEFT_SHOULDER", "LEFT_HIP", "LEFT_KNEE"
    elif joint == "knee":
        b, a, c = "LEFT_HIP", "LEFT_KNEE", "LEFT_ANKLE"
    else:
        b, a, c = "LEFT_KNEE", "LEFT_ANKLE", "LEFT_FOOT_INDEX"
    pb, pa, pc = landmarks[i, idx[b], :2], landmarks[i, idx[a], :2], landmarks[i, idx[c], :2]
    if not np.all(np.isfinite([pb, pa, pc])):
        return
    canvas = scene.canvas
    ppa = vid_px(pa)
    v1 = np.array(vid_px(pb)) - np.array(ppa)
    v2 = np.array(vid_px(pc)) - np.array(ppa)
    a1 = math.degrees(math.atan2(v1[1], v1[0]))
    a2 = math.degrees(math.atan2(v2[1], v2[0]))
    d = (a2 - a1) % 360
    if d > 180:
        a1, a2 = a2, a1
        d = 360 - d
    x0, y0 = max(ppa[0] - 46, 0), max(ppa[1] - 46, 0)
    x1, y1 = min(ppa[0] + 46, W_OUT), min(ppa[1] + 46, H_OUT)
    if x1 <= x0 or y1 <= y0:
        return
    sub = canvas[y0:y1, x0:x1]
    ov = sub.copy()
    cv2.ellipse(ov, (ppa[0] - x0, ppa[1] - y0), (30, 30), 0, a1, a1 + d, color, 3, cv2.LINE_AA)
    cv2.addWeighted(ov, alpha, sub, 1 - alpha, 0, sub)
    lx, ly = ppa[0] + 48, ppa[1]
    rrect(canvas, lx - 6, ly - 21, lx + 118, ly + 21, scene.pal["card"], alpha=0.85 * alpha,
          border=scene.pal["border"])
    scene.put(lx + 2, ly - 11, label, "tiny", color, alpha)


def draw_chart(scene: Scene, x0, y0, x1, y1, ts, vs, t_now, twin, yr, color, alpha,
               title=None, unit="deg"):
    if alpha <= 0.02:
        return
    canvas = scene.canvas
    pal = scene.pal
    rrect(canvas, x0, y0, x1, y1, pal["card2"], alpha=alpha * 0.9, border=pal["border"])
    gx0, gy0, gx1, gy1 = x0 + 56, y0 + 32, x1 - 90, y1 - 12
    ov = canvas[y0:y1, x0:x1].copy()
    for frac in (0.0, 0.5, 1.0):
        yt = yr[0] + frac * (yr[1] - yr[0])
        py = int(gy1 - frac * (gy1 - gy0))
        cv2.line(ov, (gx0 - x0, py - y0), (gx1 - x0, py - y0), pal["grid"], 1, cv2.LINE_AA)
        scene.put(x0 + 46, py, f"{yt:.0f}", "tiny", pal["muted"], alpha * 0.9, anchor="rm")
    m = (ts >= t_now - twin) & (ts <= t_now)
    cur = float("nan")
    if m.sum() >= 2:
        tt, vv = ts[m], np.clip(vs[m], yr[0], yr[1])
        finite = np.isfinite(vv)
        if finite.sum() >= 2:
            tt, vv = tt[finite], vv[finite]
            px = gx0 + (tt - (t_now - twin)) / twin * (gx1 - gx0)
            py = gy1 - (vv - yr[0]) / (yr[1] - yr[0]) * (gy1 - gy0)
            pts = np.column_stack([px - x0, py - y0]).astype(np.int32)
            cv2.polylines(ov, [pts], False, color, 2, cv2.LINE_AA)
            cv2.circle(ov, tuple(pts[-1]), 5, color, -1, cv2.LINE_AA)
            cur = float(vv[-1])
    cv2.addWeighted(ov, alpha, canvas[y0:y1, x0:x1], 1 - alpha, 0, canvas[y0:y1, x0:x1])
    if title:
        scene.put(x0 + 14, y0 + 8, title, "h3", color, alpha)
    if np.isfinite(cur):
        scene.put(x1 - 14, (y0 + y1) // 2 - 12, f"{cur:5.1f}°", "num", pal["text"], alpha, anchor="rm")


def draw_bar(scene: Scene, x0, y0, w, h, label, value, vmax, color, alpha, unit="", fmt="{:.0f}"):
    """One labelled, animated horizontal bar -- used for RoM and the
    spatio-temporal parameter cards.
    """
    if alpha <= 0.02:
        return
    pal = scene.pal
    rrect(scene.canvas, x0, y0, x0 + w, y0 + h, pal["card2"], alpha=alpha * 0.9)
    frac = 0 if vmax <= 0 else np.clip(value / vmax, 0, 1)
    filled = max(int(w * frac), 4)
    rrect(scene.canvas, x0, y0, x0 + filled, y0 + h, color, alpha=alpha * 0.85)
    scene.put(x0 + 10, y0 + h // 2, label, "chip", pal["text"] if frac < 0.6 else pal["card"],
              alpha, anchor="lm")
    scene.put(x0 + w - 10, y0 + h // 2, fmt.format(value) + unit, "h3", pal["text"], alpha, anchor="rm")


STEPS = ("1 · Skeleton", "2 · Angles", "3 · Spatio-temporal", "4 · Range of motion", "5 · Summary")


def draw_stepper(scene: Scene, active: int, alpha: float):
    if alpha <= 0.02:
        return
    pal = scene.pal
    w = (RX1 - RX0 - 4 * 12) // 5
    for k, s in enumerate(STEPS):
        x0 = RX0 + k * (w + 12)
        on = k == active
        rrect(scene.canvas, x0, 24, x0 + w, 70, pal["accent"] if on else pal["card"], alpha=alpha,
              border=pal["border"])
        scene.put(x0 + w // 2, 47, s, "chip", pal["text"] if on else pal["muted"], alpha, anchor="mm")


def logo_chip(scene: Scene, logo_bgr: np.ndarray | None, alpha: float):
    """Institut de Myologie mark, bottom-right of the info panel -- present

    alongside the app's own identity, not in place of it (see the video
    report's own call site for where the app's identity is asserted). The
    source PNG has its own white background (no alpha channel), so it sits
    on a matching paper card here rather than pasted directly onto the
    dark video panel or over the small credit line -- a bare paste there
    read as a stray rectangle, not a mark.
    """
    if logo_bgr is None or alpha <= 0.02:
        return
    h, w = logo_bgr.shape[:2]
    scale = min(150 / w, 52 / h)
    lw, lh = max(int(w * scale), 1), max(int(h * scale), 1)
    resized = cv2.resize(logo_bgr, (lw, lh), interpolation=cv2.INTER_AREA)
    pad = 14
    cx1, cy1 = RX1, H_OUT - 40
    cx0, cy0 = cx1 - lw - 2 * pad, cy1 - lh - 2 * pad
    rrect(scene.canvas, cx0, cy0, cx1, cy1, scene.pal["card"], alpha=alpha, border=scene.pal["border"])
    x0, y0 = cx1 - pad - lw, cy0 + pad
    roi = scene.canvas[y0:y0 + lh, x0:x0 + lw].astype(np.float32)
    scene.canvas[y0:y0 + lh, x0:x0 + lw] = (
        resized.astype(np.float32) * alpha + roi * (1 - alpha)
    ).astype(np.uint8)


# ── Segments ─────────────────────────────────────────────────────────
#
# Segments 1-2 (intro, angles) mirror the pedagogical script this module
# is modelled on directly -- both are real for any markerless recording.
# Segments 3-5 replace its IMU/virtual-accelerometer/biomarker content
# (nothing in a normal app_myogait run supplies that) with the app's own
# spatio-temporal parameters, range of motion, and normative comparison.

_SIDE_LABEL = {"LEFT": "left", "RIGHT": "right"}


def render_intro(scene: Scene, rd: VideoReportData, t, j, tl):
    stag = ease(t, 1.6, 2.2)
    draw_skeleton(scene.canvas, scene.pal, rd.landmarks, j, alpha=1.0, stagger=stag)
    ga = fade_io(t, 0.3, 0.7, 5.3, 0.6)
    scene.put(RX0 + 10, 300, "Markerless", "title", scene.pal["text"], ga)
    scene.put(RX0 + 10, 356, "gait analysis", "title", scene.pal["text"], ga)
    line_a(scene.canvas, (RX0 + 14, 424), (RX0 + 320, 424), scene.pal["border"], 4, ga)
    if ga > 0.02:
        ov = scene.canvas.copy()
        cv2.rectangle(ov, (RX0 + 14, 448), (RX0 + 42, 476), scene.pal["red"], -1)
        cv2.circle(ov, (RX0 + 76, 462), 15, scene.pal["blue"], -1, cv2.LINE_AA)
        cv2.fillPoly(ov, [np.array([[RX0 + 106, 476], [RX0 + 122, 448], [RX0 + 138, 476]])],
                     scene.pal["accent"], cv2.LINE_AA)
        cv2.addWeighted(ov, ga, scene.canvas, 1 - ga, 0, scene.canvas)
    meta_line = f"Pose model: {rd.model_name}  ·  {rd.fps_src:.0f} fps  ·  side analysed: {_SIDE_LABEL[rd.side]}"
    scene.put(RX0 + 12, 500, meta_line, "sub", scene.pal["muted"], ga)
    b1 = fade_io(t, 2.1, 0.6, 5.3, 0.6)
    scene.put(RX0 + 12, 574, "•  Skeleton estimated from the video alone -- no markers on the subject",
              "body", scene.pal["text"], b1)
    b2 = fade_io(t, 3.0, 0.6, 5.3, 0.6)
    scene.put(RX0 + 12, 612, f"•  {rd.n_cycles} gait cycle(s) segmented on this side", "body",
              scene.pal["text"], b2)
    b3 = fade_io(t, 3.9, 0.6, 5.3, 0.6)
    scene.put(RX0 + 12, 650, "•  Joint kinematics computed sagittal-plane, per myogait's pipeline",
              "body", scene.pal["blue"], b3)


def render_angles(scene: Scene, rd: VideoReportData, t, j, tl):
    a = fade_io(t, 6.0, 0.6, 19.4, 0.6)
    draw_skeleton(scene.canvas, scene.pal, rd.landmarks, j, alpha=0.95)
    t_src = j / rd.fps_src
    for k, joint in enumerate(SAGITTAL_JOINTS):
        aa = a * ease(t, 6.3 + 0.35 * k, 0.5)
        draw_angle_arc(scene, rd.landmarks, j, joint, aa, scene.pal["joint"][joint],
                       JOINT_LABEL[joint])
    ca = a * ease(t, 6.6, 0.7)
    rrect(scene.canvas, RX0, 104, RX1, 900, scene.pal["card"], alpha=ca * 0.95, border=scene.pal["border"])
    scene.put(RX0 + 24, 122, "Joint kinematics · sagittal plane", "h2", scene.pal["text"], ca)
    scene.put(RX1 - 24, 130, f"{_SIDE_LABEL[rd.side]} side", "small", scene.pal["muted"], ca, anchor="ra")
    yrs = {"hip": (-30, 50), "knee": (-10, 80), "ankle": (-30, 30)}
    for k, joint in enumerate(SAGITTAL_JOINTS):
        y0 = 168 + k * 240
        draw_chart(scene, RX0 + 24, y0, RX1 - 24, y0 + 220, rd.angle_t, rd.angles[joint],
                   t_src, 4.0, yrs[joint], scene.pal["joint"][joint],
                   ca * ease(t, 6.9 + 0.3 * k, 0.5),
                   title=f"{JOINT_LABEL[joint]} flexion")


def render_spatiotemporal(scene: Scene, rd: VideoReportData, t, j, tl):
    a = fade_io(t, 20.0, 0.6, 31.4, 0.6)
    draw_skeleton(scene.canvas, scene.pal, rd.landmarks, j, alpha=0.4)
    ca = a * ease(t, 20.3, 0.6)
    rrect(scene.canvas, RX0, 104, RX1, 960, scene.pal["card"], alpha=ca * 0.95, border=scene.pal["border"])
    scene.put(RX0 + 24, 122, "Spatio-temporal parameters", "h2", scene.pal["text"], ca)
    scene.put(RX0 + 24, 156, "From heel-strike / toe-off timing across every segmented cycle",
              "small", scene.pal["muted"], ca)
    st = rd.spatiotemporal
    rows = [
        ("Cadence", st.get("cadence_steps_per_min"), 160, " steps/min"),
        ("Stride time", st.get("stride_time_mean_s"), 2.5, " s"),
        ("Step time", st.get("step_time_mean_s"), 1.5, " s"),
        ("Stance (L)", st.get("stance_pct_left"), 100, " %"),
        ("Stance (R)", st.get("stance_pct_right"), 100, " %"),
        ("Swing (L)", st.get("swing_pct_left"), 100, " %"),
        ("Swing (R)", st.get("swing_pct_right"), 100, " %"),
        ("Double support", st.get("double_support_pct"), 100, " %"),
    ]
    bw, bh, gap = RX1 - RX0 - 48, 70, 16
    for k, (label, val, vmax, unit) in enumerate(rows):
        y0 = 196 + k * (bh + gap)
        ra = ca * ease(tl, 0.5 + 0.18 * k, 0.5)
        if val is None:
            continue
        draw_bar(scene, RX0 + 24, y0, bw, bh, label, float(val), vmax,
                 scene.pal["joint"]["hip"] if k < 3 else scene.pal["joint"]["knee"], ra,
                 unit=unit, fmt="{:.1f}")


def render_rom(scene: Scene, rd: VideoReportData, t, j, tl):
    a = fade_io(t, 32.0, 0.6, 43.4, 0.6)
    draw_skeleton(scene.canvas, scene.pal, rd.landmarks, j, alpha=0.4)
    ca = a * ease(t, 32.3, 0.6)
    rrect(scene.canvas, RX0, 104, RX1, 560, scene.pal["card"], alpha=ca * 0.95, border=scene.pal["border"])
    scene.put(RX0 + 24, 122, "Range of motion", "h2", scene.pal["text"], ca)
    scene.put(RX0 + 24, 156, f"Peak-to-peak per cycle, {_SIDE_LABEL[rd.side]} side, mean over "
              f"{rd.n_cycles} cycle(s)", "small", scene.pal["muted"], ca)
    vmax = {"hip": 60.0, "knee": 90.0, "ankle": 50.0}
    for k, joint in enumerate(SAGITTAL_JOINTS):
        y0 = 196 + k * 110
        ra = ca * ease(tl, 0.4 + 0.3 * k, 0.5)
        rom = rd.rom_deg.get(joint)
        if rom is None:
            continue
        draw_bar(scene, RX0 + 24, y0, RX1 - 48, 80, f"{JOINT_LABEL[joint]} RoM", rom,
                 vmax[joint], scene.pal["joint"][joint], ra, unit="°", fmt="{:.1f}")

    ea = a * ease(t, 37.5, 0.7)
    rrect(scene.canvas, RX0, 592, RX1, 900, scene.pal["card"], alpha=ea * 0.95, border=scene.pal["border"])
    scene.put(RX0 + 24, 610, "Angle at heel-strike and toe-off", "h2", scene.pal["text"], ea)
    cw = (RX1 - RX0 - 48 - 2 * 20) // 3
    for k, joint in enumerate(SAGITTAL_JOINTS):
        x0 = RX0 + 24 + k * (cw + 20)
        ja = ea * ease(tl, 5.6 + 0.3 * k, 0.5)
        rrect(scene.canvas, x0, 654, x0 + cw, 862, scene.pal["card2"], alpha=ja * 0.9,
              border=scene.pal["border"])
        scene.put(x0 + cw // 2, 672, JOINT_LABEL[joint], "h3", scene.pal["joint"][joint], ja, anchor="ma")
        hs = rd.at_heel_strike.get(joint)
        to = rd.at_toe_off.get(joint)
        scene.put(x0 + 16, 730, "Heel-strike", "small", scene.pal["muted"], ja)
        scene.put(x0 + cw - 16, 730, f"{hs:5.1f}°" if hs is not None else "--", "num",
                  scene.pal["text"], ja, anchor="ra")
        scene.put(x0 + 16, 800, "Toe-off", "small", scene.pal["muted"], ja)
        scene.put(x0 + cw - 16, 800, f"{to:5.1f}°" if to is not None else "--", "num",
                  scene.pal["text"], ja, anchor="ra")


def render_summary(scene: Scene, rd: VideoReportData, t, j, tl):
    a = ease(t, 44.0, 0.6)
    draw_skeleton(scene.canvas, scene.pal, rd.landmarks, j, alpha=0.4)
    ca = a * ease(t, 44.3, 0.6)
    rrect(scene.canvas, RX0, 104, RX1, 760, scene.pal["card"], alpha=ca * 0.95, border=scene.pal["border"])
    scene.put(RX0 + 24, 122, "This recording vs the normative band", "h2", scene.pal["text"], ca)
    scene.put(RX1 - 24, 130, "adult reference", "small", scene.pal["muted"], ca, anchor="ra")
    cw = (RX1 - RX0 - 48 - 2 * 20) // 3
    for k, joint in enumerate(SAGITTAL_JOINTS):
        x0 = RX0 + 24 + k * (cw + 20)
        ja = ca * ease(tl, 0.5 + 0.3 * k, 0.6)
        _draw_normative_mini(scene, x0, 168, x0 + cw, 720, joint, rd, ja)

    ba = ease(tl, 3.4, 0.9)
    rrect(scene.canvas, RX0, 786, RX1, 1006, scene.pal["border"], alpha=ba * 0.97)
    scene.put((RX0 + RX1) // 2, 814, "Markerless summary", "h2", scene.pal["card"], ba, anchor="ma")
    parts = [f"{JOINT_LABEL[j_]} RoM {rd.rom_deg[j_]:.0f}°" for j_ in SAGITTAL_JOINTS if j_ in rd.rom_deg]
    scene.put((RX0 + RX1) // 2, 864, "   ·   ".join(parts), "body", scene.pal["card"], ba, anchor="ma")
    cad = rd.spatiotemporal.get("cadence_steps_per_min")
    cad_txt = f"cadence {cad:.0f} steps/min" if cad is not None else ""
    scene.put((RX0 + RX1) // 2, 906, f"{rd.n_cycles} cycle(s) analysed  ·  {cad_txt}", "body",
              scene.pal["accent"], ease(tl, 4.2, 0.7), anchor="ma")
    scene.put((RX0 + RX1) // 2, 958, "No markers placed on the subject", "small", scene.pal["muted"],
              ease(tl, 5.0, 0.7), anchor="ma")


def _draw_normative_mini(scene: Scene, x0, y0, x1, y1, joint, rd: VideoReportData, alpha):
    if alpha <= 0.02:
        return
    pal = scene.pal
    rrect(scene.canvas, x0, y0, x1, y1, pal["card2"], alpha=alpha * 0.9, border=pal["border"])
    scene.put((x0 + x1) // 2, y0 + 14, JOINT_LABEL[joint], "h3", pal["joint"][joint], alpha, anchor="ma")
    band = rd.normative.get(joint) or {}
    lower, upper = band.get("lower"), band.get("upper")
    gx0, gy0, gx1, gy1 = x0 + 40, y0 + 48, x1 - 16, y1 - 16
    ov = scene.canvas[y0:y1, x0:x1].copy()
    if lower and upper:
        n = len(lower)
        lo, hi = np.asarray(lower), np.asarray(upper)
        yr = (float(min(lo.min(), hi.min())) - 5, float(max(lo.max(), hi.max())) + 5)
        px = gx0 + np.arange(n) / (n - 1) * (gx1 - gx0)
        py_lo = gy1 - (lo - yr[0]) / (yr[1] - yr[0]) * (gy1 - gy0)
        py_hi = gy1 - (hi - yr[0]) / (yr[1] - yr[0]) * (gy1 - gy0)
        band_poly = np.column_stack([
            np.concatenate([px, px[::-1]]) - x0,
            np.concatenate([py_hi, py_lo[::-1]]) - y0,
        ]).astype(np.int32)
        cv2.fillPoly(ov, [band_poly], pal["grid"], cv2.LINE_AA)
    cv2.addWeighted(ov, alpha, scene.canvas[y0:y1, x0:x1], 1 - alpha, 0, scene.canvas[y0:y1, x0:x1])
    rom = rd.rom_deg.get(joint)
    if rom is not None:
        scene.put((x0 + x1) // 2, y1 - 20, f"this recording: {rom:.0f}° RoM", "small",
                  pal["joint"][joint], alpha, anchor="ma")


RENDER = {
    "intro": render_intro, "angles": render_angles, "spatiotemporal": render_spatiotemporal,
    "rom": render_rom, "summary": render_summary,
}
STEP_OF = {"intro": 0, "angles": 1, "spatiotemporal": 2, "rom": 3, "summary": 4}

#: (name, t0, t1, j0, speed) -- j0/speed pick which pivot frame plays under
#: each segment, in pivot-frames-per-output-frame, wrapping via modulo so a
#: short recording still fills the whole video instead of freezing on the
#: last frame.
_SEGMENTS = (
    ("intro", 0.0, 6.0, 0.15, 0.6),
    ("angles", 6.0, 20.0, 0.0, 1.0),
    ("spatiotemporal", 20.0, 32.0, 0.0, 0.8),
    ("rom", 32.0, 44.0, 0.0, 0.8),
    ("summary", 44.0, 56.0, 0.0, 0.6),
)
DURATION_S = _SEGMENTS[-1][2]


def _seg_at(t: float):
    for seg in _SEGMENTS:
        if t < seg[2]:
            return seg
    return _SEGMENTS[-1]


def render_video_report(
    data: dict,
    cycles: dict,
    stats: dict,
    video_path: str,
    out_path: str,
    progress_callback: Callable[[float], None] | None = None,
) -> Path:
    """Render the 5-segment animated report to *out_path* (MP4, H.264 via

    OpenCV's own FFmpeg-backed writer -- already a transitive dependency,
    nothing new to install). Needs the original source video: this is the
    one export that reads the actual frames, not only the pivot's own
    landmark data (see page_export.py's gating on ``source.path``).
    """
    rd = prepare(data, cycles, stats)
    pal = _palette()
    fonts = _fonts()
    n_pivot = max(rd.landmarks.shape[0], 1)

    logo_path = _ASSETS / "logo_institut_myologie.png"
    logo_bgr = cv2.imread(str(logo_path), cv2.IMREAD_COLOR) if logo_path.is_file() else None

    cap = cv2.VideoCapture(str(video_path))
    n_frames_out = int(DURATION_S * FPS_OUT)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, FPS_OUT, (W_OUT, H_OUT))
    if not writer.isOpened():
        raise RuntimeError(f"Could not open a video writer for {out_path}")

    cur_src = -10
    last_img = None
    try:
        for fi in range(n_frames_out):
            t = fi / FPS_OUT
            name, t0, t1, j0, spd = _seg_at(t)
            j = (j0 * n_pivot + (t - t0) * FPS_OUT * spd) % n_pivot
            target = int(round(j))
            if target != cur_src:
                if target < cur_src or target > cur_src + 12 or cur_src < 0:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
                    ok, frm = cap.read()
                else:
                    ok, frm = True, None
                    for _ in range(target - cur_src):
                        ok, frm = cap.read()
                if ok and frm is not None:
                    last_img = cv2.resize(frm, (VID_W, H_OUT), interpolation=cv2.INTER_AREA)
                cur_src = target

            scene = Scene(pal, fonts)
            if last_img is not None:
                scene.canvas[0:H_OUT, VID_X:VID_X + VID_W] = last_img
            cv2.rectangle(scene.canvas, (VID_X - 1, 0), (VID_X + VID_W, H_OUT - 1), pal["border"], 1)

            RENDER[name](scene, rd, t, j, t - t0)
            draw_stepper(scene, STEP_OF[name], ease(t, 0.8, 0.5))
            logo_chip(scene, logo_bgr, ease(t, 0.8, 0.5))
            scene.put(RX1, H_OUT - 26, "Markerless pipeline · myogait", "tiny", pal["muted"], 0.75,
                      anchor="ra")

            scene.flush()
            canvas = scene.canvas
            gfade = min(ease(t, 0.0, 0.5), 1 - ease(t, DURATION_S - 0.7, 0.7))
            if gfade < 1:
                bgf = np.empty_like(canvas)
                bgf[:] = pal["bg"]
                g = max(gfade, 0.0)
                canvas = (canvas.astype(np.float32) * g + bgf.astype(np.float32) * (1 - g)).astype(np.uint8)

            writer.write(canvas)
            if progress_callback is not None and fi % 10 == 0:
                progress_callback(fi / n_frames_out)
    finally:
        cap.release()
        writer.release()

    if progress_callback is not None:
        progress_callback(1.0)
    return Path(out_path)
