"""Palette validator: WCAG contrast + CVD (colour-blind) separation.

``myogait_app/branding.py``'s comments have long promised a check like
this ("do not substitute hexes here without re-running the check") with
no runnable script anywhere in the repo to back it up. This is that
script. Run with no arguments to validate the identity tokens currently
in ``BRANDING`` (surface/ink/border/accent, both themes); pass a JSON
array of ``{"label", "fg", "bg", "min_ratio"}`` pairs to check something
else -- a proposed replacement palette, for instance, before committing
to it.

    python scripts/validate_palette.py
    python scripts/validate_palette.py '[{"label": "x", "fg": "#...", "bg": "#..."}]'

Does not touch the categorical/side/status data-viz colours: those were
validated separately (OKLCH lightness band, chroma floor, normal-vision
floor -- checks this script does not reimplement) and were deliberately
left unchanged by the identity redesign this script was written for.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c: float) -> float:
    c = max(0.0, min(1.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def relative_luminance(hexcolor: str) -> float:
    r, g, b = (srgb_to_linear(c) for c in hex_to_rgb(hexcolor))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(hex1: str, hex2: str) -> float:
    """WCAG 2.x contrast ratio, 1:1 (identical) to 21:1 (black on white)."""
    l1, l2 = relative_luminance(hex1), relative_luminance(hex2)
    l1, l2 = max(l1, l2), min(l1, l2)
    return (l1 + 0.05) / (l2 + 0.05)


# Machado, Oliveira & Fernandes 2009 colour-vision-deficiency simulation
# matrices (severity=1.0), applied directly to linear-light sRGB.
CVD_MATRICES = {
    "protanopia": [
        [0.152286, 1.052583, -0.204868],
        [0.114503, 0.786281, 0.099216],
        [-0.003882, -0.048116, 1.051998],
    ],
    "deuteranopia": [
        [0.367322, 0.860646, -0.227968],
        [0.280085, 0.672501, 0.047413],
        [-0.011820, 0.042940, 0.968881],
    ],
}


def simulate_cvd(hexcolor: str, kind: str) -> tuple[float, float, float]:
    r, g, b = (srgb_to_linear(c) for c in hex_to_rgb(hexcolor))
    m = CVD_MATRICES[kind]
    r2 = m[0][0] * r + m[0][1] * g + m[0][2] * b
    g2 = m[1][0] * r + m[1][1] * g + m[1][2] * b
    b2 = m[2][0] * r + m[2][1] * g + m[2][2] * b
    return tuple(linear_to_srgb(c) for c in (r2, g2, b2))


def srgb_to_oklab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (srgb_to_linear(c) for c in rgb)
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b

    def cbrt(x: float) -> float:
        return x ** (1 / 3) if x >= 0 else -((-x) ** (1 / 3))

    l_, m_, s_ = cbrt(l), cbrt(m), cbrt(s)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    bb = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, a, bb


def oklch(hexcolor: str) -> tuple[float, float, float]:
    """(lightness 0-1, chroma, hue degrees)."""
    L, a, b = srgb_to_oklab(hex_to_rgb(hexcolor))
    return L, math.hypot(a, b), math.degrees(math.atan2(b, a)) % 360


def delta_e_oklab(hex1: str, hex2: str) -> float:
    """Perceptual difference, roughly comparable to CIE deltaE scale."""
    L1, a1, b1 = srgb_to_oklab(hex_to_rgb(hex1))
    L2, a2, b2 = srgb_to_oklab(hex_to_rgb(hex2))
    return math.sqrt((L1 - L2) ** 2 + (a1 - a2) ** 2 + (b1 - b2) ** 2) * 100


def check_pair(label: str, fg: str, bg: str, min_ratio: float = 4.5) -> bool:
    """Print and return whether *fg* on *bg* clears contrast and CVD checks.

    *min_ratio* should be 4.5 for body/placeholder text, 3.0 for large
    text or non-text UI components (borders, icons) per WCAG 2.x.
    """
    cr = contrast_ratio(fg, bg)
    ok = cr >= min_ratio
    print(f"\n{label}")
    print(f"  [{'OK' if ok else 'FAIL'}] contrast: {fg} on {bg} = {cr:.2f}:1 (need >= {min_ratio})")

    de_normal = delta_e_oklab(fg, bg)
    for kind in ("protanopia", "deuteranopia"):
        fg_sim = simulate_cvd(fg, kind)
        bg_sim = simulate_cvd(bg, kind)
        fg_hex = "#%02x%02x%02x" % tuple(round(c * 255) for c in fg_sim)
        bg_hex = "#%02x%02x%02x" % tuple(round(c * 255) for c in bg_sim)
        de = delta_e_oklab(fg_hex, bg_hex)
        cvd_ok = de >= 10
        ok = ok and cvd_ok
        print(f"    [{'OK' if cvd_ok else 'WEAK'}] {kind}: deltaE={de:.1f} (normal-vision deltaE={de_normal:.1f})")

    L, C, H = oklch(fg)
    print(f"    OKLCH(fg): L={L:.3f} C={C:.3f} H={H:.1f}")
    return ok


def default_pairs() -> list[dict]:
    """The identity tokens currently in BRANDING, both themes."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from myogait_app.branding import BRANDING as B

    pairs = []
    for mode, dark in (("light", False), ("dark", True)):
        pairs += [
            {"label": f"{mode}: text on background", "fg": B.ink_for(dark), "bg": B.surface_for(dark)},
            {"label": f"{mode}: muted text on background", "fg": B.ink_muted_for(dark), "bg": B.surface_for(dark), "min_ratio": 4.5},
            # accent itself is fill-only (this identity's yellow is too
            # light-valued to also serve as a mark on the paper ground);
            # accent_mark is the token real call sites use for text/thin
            # marks/lines, and accent_ink_for is what sits on the fill.
            {"label": f"{mode}: accent_mark on background", "fg": B.accent_mark_for(dark), "bg": B.surface_for(dark), "min_ratio": 3.0},
            {"label": f"{mode}: ink on accent (button fill)", "fg": B.accent_ink_for(dark), "bg": B.accent_for(dark)},
            {"label": f"{mode}: border on background (non-text)", "fg": B.border_for(dark), "bg": B.surface_for(dark), "min_ratio": 1.4},
            {"label": f"{mode}: side left on background", "fg": B.side_colors["left"], "bg": B.surface_for(dark), "min_ratio": 3.0},
            {"label": f"{mode}: side right on background", "fg": B.side_colors["right"], "bg": B.surface_for(dark), "min_ratio": 3.0},
        ]
    return pairs


if __name__ == "__main__":
    pairs = json.loads(sys.argv[1]) if len(sys.argv) > 1 else default_pairs()
    all_ok = True
    for p in pairs:
        all_ok = check_pair(p["label"], p["fg"], p["bg"], p.get("min_ratio", 4.5)) and all_ok
    print("\n" + ("ALL PASS" if all_ok else "SOME FAILED"))
    sys.exit(0 if all_ok else 1)
