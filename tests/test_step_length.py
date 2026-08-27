"""Unit tests for the automatic marker-based metric step length.

Synthetic heel/hip markers with a known geometry: each heel oscillates about
the pelvis in antiphase with amplitude A, so at a heel strike (this heel most
forward) the two heels sit 2A apart -- the step length the code must recover.
Locks the value, the unit auto-detection, direction independence and the
graceful None paths.
"""

from __future__ import annotations

import numpy as np

from myogait_app.step_length import step_length_m_from_markers


def _walk(amplitude: float = 0.3, n: int = 240, axis: int = 0, scale: float = 1.0):
    """Two feet walking along `axis`, antiphase, step length == 2*amplitude."""
    t = np.linspace(0.0, 12.0, n)
    forward = t  # steady drift so `axis` is unambiguously the walking axis
    phase = 2.0 * np.pi * t
    this_l = forward + amplitude * np.sin(phase)
    this_r = forward + amplitude * np.sin(phase + np.pi)

    def triplet(fwd, lateral):
        cols = [np.full(n, lateral), np.full(n, lateral), np.full(n, lateral)]
        cols[axis] = fwd
        cols[(axis + 1) % 3] = np.full(n, lateral)  # small constant off-axis
        return (np.column_stack(cols) * scale)

    pelvis_fwd = forward
    return {
        "LEFT_HEEL": triplet(this_l, 0.1),
        "RIGHT_HEEL": triplet(this_r, -0.1),
        "LEFT_HIP": triplet(pelvis_fwd, 0.1),
        "RIGHT_HIP": triplet(pelvis_fwd, -0.1),
    }


def test_recovers_the_known_step_length():
    value = step_length_m_from_markers(_walk(amplitude=0.3))
    assert value is not None
    assert abs(value - 0.6) < 0.05  # 2 * amplitude


def test_millimetre_units_are_detected():
    metres = step_length_m_from_markers(_walk(amplitude=0.3, scale=1.0))
    millis = step_length_m_from_markers(_walk(amplitude=0.3, scale=1000.0))
    assert metres is not None and millis is not None
    assert abs(metres - millis) < 0.02  # same length regardless of unit


def test_direction_independent():
    along_x = step_length_m_from_markers(_walk(amplitude=0.3, axis=0))
    along_y = step_length_m_from_markers(_walk(amplitude=0.3, axis=1))
    assert along_x is not None and along_y is not None
    assert abs(along_x - along_y) < 0.05


def test_leading_nans_do_not_break_it():
    markers = _walk(amplitude=0.3)
    for name in ("LEFT_HEEL", "RIGHT_HEEL", "LEFT_HIP", "RIGHT_HIP"):
        markers[name][:8] = np.nan
    value = step_length_m_from_markers(markers)
    assert value is not None
    assert abs(value - 0.6) < 0.06


def test_missing_markers_return_none():
    markers = _walk()
    del markers["LEFT_HEEL"]
    assert step_length_m_from_markers(markers) is None
    assert step_length_m_from_markers({}) is None
    assert step_length_m_from_markers(None) is None


def test_malformed_marker_values_return_none():
    markers = _walk()
    markers["LEFT_HEEL"] = "not marker coordinates"

    assert step_length_m_from_markers(markers) is None


def test_implausibly_small_steps_are_dropped():
    # 2 * 0.05 = 0.1 m, below the physiological floor -> nothing survives.
    assert step_length_m_from_markers(_walk(amplitude=0.05)) is None
