"""Unit tests for Cohort minimal-detectable-change helpers."""

from __future__ import annotations

import math

import pytest

from myogait_app.mdc import MIN_DOF, exceeds_mdc, mdc95, pooled_sw


def test_pooled_sw_combines_within_subject_variance() -> None:
    """Each subject is centred independently before its variance is pooled."""
    values = [
        [0.0, 2.0, 4.0, 6.0, 8.0, 10.0],
        [10.0, 12.0, 14.0, 16.0, 18.0, 20.0],
    ]

    # Each group has sum((x - mean(x)) ** 2) == 70; together dof == 10.
    assert pooled_sw(values) == pytest.approx(math.sqrt(14.0))


def test_pooled_sw_ignores_missing_values_and_short_subjects() -> None:
    values = [
        [float("nan"), 0.0, 2.0, 4.0, 6.0, 8.0, 10.0],
        [100.0, 101.0],  # Too few cycles to give a reliable SD.
        [10.0, 12.0, 14.0, 16.0, 18.0, 20.0],
    ]

    assert pooled_sw(values) == pytest.approx(math.sqrt(14.0))


def test_pooled_sw_requires_enough_degrees_of_freedom() -> None:
    # Two five-cycle subjects yield 8 degrees of freedom, below the threshold.
    assert MIN_DOF == 10
    assert pooled_sw([[0, 1, 2, 3, 4], [10, 11, 12, 13, 14]]) is None


def test_mdc95_scales_with_the_square_root_of_cycle_count() -> None:
    single_cycle = mdc95(2.0)

    assert single_cycle == pytest.approx(1.96 * math.sqrt(2.0) * 2.0)
    assert mdc95(2.0, n=4) == pytest.approx(single_cycle / 2.0)
    assert mdc95(None) is None
    assert mdc95(2.0, n=0) is None


def test_exceeds_mdc_is_strict_and_uses_absolute_difference() -> None:
    assert exceeds_mdc(2.1, 2.0)
    assert exceeds_mdc(-2.1, 2.0)
    assert not exceeds_mdc(2.0, 2.0)
    assert not exceeds_mdc(9.0, None)
