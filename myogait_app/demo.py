"""A synthetic dataset, so the workbench is usable with nothing loaded.

Two audiences need this. A researcher opening the app for the first time
should be able to move every slider and watch the curves react before
committing a real recording to it. And the app itself needs a fixture it
can be tested against without a video file.

The skeleton follows the same landmark layout as the myogait test suite,
which is what guarantees the pipeline accepts it. Forward progression and
a little noise are added on top, because a subject walking on the spot
with a perfect sinusoid produces degenerate step lengths and a variability
of exactly zero -- which teaches the user nothing about what the metrics
do.

Nothing here is clinical data. It is a mathematical gait-like signal, and
the interface labels it as such wherever it is shown.
"""

from __future__ import annotations

import numpy as np

#: Landmark layout shared with the myogait fixtures (MediaPipe naming).
_LANDMARKS = (
    "NOSE", "LEFT_EYE", "RIGHT_EYE", "LEFT_EAR", "RIGHT_EAR",
    "LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_ELBOW", "RIGHT_ELBOW",
    "LEFT_WRIST", "RIGHT_WRIST", "LEFT_HIP", "RIGHT_HIP",
    "LEFT_KNEE", "RIGHT_KNEE", "LEFT_ANKLE", "RIGHT_ANKLE",
    "LEFT_HEEL", "RIGHT_HEEL", "LEFT_FOOT_INDEX", "RIGHT_FOOT_INDEX",
)

DEMO_NAME = "synthetic_walk"


def make_demo_data(
    n_frames: int = 300,
    fps: float = 30.0,
    cycle_period: float = 1.0,
    noise: float = 0.0015,
    progression: float = 0.0,
    asymmetry: float = 0.0,
    seed: int = 12345,
) -> dict:
    """Build a pivot dict of gait-like landmarks.

    Parameters
    ----------
    n_frames, fps
        Clip length and sampling rate.
    cycle_period
        Seconds per gait cycle. Drives the cadence the app will report.
    noise
        SD of the jitter added to every coordinate, in normalised units.
        Set to 0 for a noise-free signal, which is useful for showing what
        a filter does and does not change.
    progression
        Total forward travel of the pelvis across the clip, in normalised
        units. Non-zero makes step length and walking speed meaningful.
    asymmetry
        Fraction by which the right-side amplitude differs from the left.
        0.2 gives a visibly asymmetric gait, which makes the symmetry
        indices move off zero.
    seed
        Fixes the jitter so the demo is reproducible between reruns --
        a workbench whose numbers change on refresh is not a workbench.
    """
    from myogait.schema import create_empty

    rng = np.random.default_rng(seed)
    data = create_empty(
        f"{DEMO_NAME}.mp4", fps=fps, width=1920, height=1080, n_frames=n_frames
    )
    data["extraction"] = {
        "model": "synthetic",
        "note": "Generated signal, not a recording.",
    }

    frames = []
    ankle_amp = 0.08
    arm_amp = 0.04
    right_scale = 1.0 + asymmetry

    for i in range(n_frames):
        t = i / fps
        phase_l = 2 * np.pi * t / cycle_period
        phase_r = phase_l + np.pi
        # Pelvis advances linearly; the camera is assumed static.
        hip_x = 0.50 + progression * (i / max(1, n_frames - 1))

        sin_l = np.sin(phase_l)
        sin_r = np.sin(phase_r) * right_scale

        positions = {
            "NOSE": (hip_x, 0.10),
            "LEFT_EYE": (hip_x - 0.01, 0.08),
            "RIGHT_EYE": (hip_x + 0.01, 0.08),
            "LEFT_EAR": (hip_x - 0.02, 0.10),
            "RIGHT_EAR": (hip_x + 0.02, 0.10),
            "LEFT_SHOULDER": (hip_x, 0.25),
            "RIGHT_SHOULDER": (hip_x + 0.01, 0.25),
            # Arms swing against the ipsilateral leg.
            "LEFT_ELBOW": (hip_x + arm_amp * sin_r * 0.5, 0.37),
            "RIGHT_ELBOW": (hip_x + 0.01 + arm_amp * sin_l * 0.5, 0.37),
            "LEFT_WRIST": (hip_x + arm_amp * sin_r, 0.48),
            "RIGHT_WRIST": (hip_x + 0.01 + arm_amp * sin_l, 0.48),
            "LEFT_HIP": (hip_x, 0.50),
            "RIGHT_HIP": (hip_x + 0.01, 0.50),
            "LEFT_KNEE": (hip_x + 0.04 * sin_l, 0.65),
            "RIGHT_KNEE": (hip_x + 0.01 + 0.04 * sin_r, 0.65),
            "LEFT_ANKLE": (hip_x + ankle_amp * sin_l, 0.80),
            "RIGHT_ANKLE": (hip_x + 0.01 + ankle_amp * sin_r, 0.80),
            "LEFT_HEEL": (hip_x + ankle_amp * sin_l + 0.01, 0.82),
            "RIGHT_HEEL": (hip_x + 0.01 + ankle_amp * sin_r + 0.01, 0.82),
            "LEFT_FOOT_INDEX": (hip_x + ankle_amp * sin_l - 0.03, 0.82),
            "RIGHT_FOOT_INDEX": (hip_x + 0.01 + ankle_amp * sin_r - 0.03, 0.82),
        }

        landmarks = {}
        for name in _LANDMARKS:
            x, y = positions[name]
            if noise:
                x = float(x + rng.normal(0.0, noise))
                y = float(y + rng.normal(0.0, noise))
            landmarks[name] = {"x": float(x), "y": float(y), "visibility": 0.95}

        frames.append(
            {
                "frame_idx": i,
                "time_s": round(t, 4),
                "landmarks": landmarks,
                "confidence": 0.95,
            }
        )

    data["frames"] = frames
    return data


#: Presets offered in the interface. Each one is chosen to make a
#: different part of the analysis visibly react.
DEMO_PRESETS: dict[str, dict] = {
    "Clean walk": {
        "noise": 0.0,
        "progression": 0.0,
        "asymmetry": 0.0,
        "cycle_period": 1.0,
        "note": "Noise-free sinusoid. Filters should change almost nothing.",
    },
    "Noisy walk": {
        "noise": 0.004,
        "progression": 0.0,
        "asymmetry": 0.0,
        "cycle_period": 1.0,
        "note": "Landmark jitter. Shows what the Butterworth cutoff buys you.",
    },
    "Walk with progression": {
        "noise": 0.0015,
        "progression": 0.25,
        "asymmetry": 0.0,
        "cycle_period": 1.0,
        "note": "Pelvis advances, so step length and speed become meaningful.",
    },
    "Asymmetric gait": {
        "noise": 0.0015,
        "progression": 0.25,
        "asymmetry": 0.25,
        "cycle_period": 1.1,
        "note": "Right amplitude raised 25%. Symmetry indices move off zero.",
    },
}
