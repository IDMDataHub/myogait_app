"""Minimal Detectable Change (MDC) from pooled within-subject variability.

A clinician replacing Vicon needs to know whether a change -- between visits,
before/after treatment, or between two conditions -- is real or just
measurement noise. MDC answers that: a difference smaller than MDC is within
the method's own repeatability.

Ported from the validation report's ``repeatability_stats``. Streamlit-free.

- ``Sw`` (within-subject SD) is the pooled per-cycle SD, pooled across
  subjects so a subject with more cycles weighs more:
  ``Sw = sqrt( sum_s sum_i (x_si - mean_s)^2  /  sum_s (n_s - 1) )``.
- ``MDC95(n) = 1.96 * sqrt(2) * Sw / sqrt(n)`` for the mean of ``n`` cycles;
  the ``sqrt(2)`` is the SD of a difference of two independent measurements.
"""

from __future__ import annotations

import math
from numbers import Real

import numpy as np

#: Subjects with fewer cycles than this are skipped (their variance estimate
#: is too unstable to pool), and the parameter is dropped if too few degrees
#: of freedom remain -- mirrors the report.
MIN_CYCLES_PER_SUBJECT = 3
MIN_DOF = 10


def _finite_number(value: object) -> bool:
    """Whether *value* is a usable measurement (not a bool, NaN or infinity)."""
    return isinstance(value, Real) and not isinstance(value, bool) and math.isfinite(value)


def pooled_sw(values_by_subject: list[list[float]]) -> float | None:
    """Pooled within-subject SD from per-cycle values grouped by subject.

    ``values_by_subject`` is one list of per-cycle parameter values per
    subject. Returns ``None`` when too little data survives.
    """
    sum_sq = 0.0
    dof = 0
    for values in values_by_subject:
        arr = np.asarray(
            [v for v in values if _finite_number(v)],
            dtype=float,
        )
        if arr.size < MIN_CYCLES_PER_SUBJECT:
            continue
        sum_sq += float(np.sum((arr - arr.mean()) ** 2))
        dof += arr.size - 1
    if dof < MIN_DOF:
        return None
    return float(math.sqrt(sum_sq / dof))


def mdc95(sw: float | None, n: int = 1) -> float | None:
    """MDC95 for the mean of ``n`` cycles. ``None`` if ``sw`` is unknown."""
    if not _finite_number(sw) or sw < 0 or isinstance(n, bool) or not isinstance(n, int) or n < 1:
        return None
    return float(1.96 * math.sqrt(2.0) * sw / math.sqrt(n))


def exceeds_mdc(difference: float, mdc: float | None) -> bool:
    """True when a between-condition/visit difference is beyond measurement noise."""
    return (
        _finite_number(difference)
        and _finite_number(mdc)
        and mdc >= 0
        and abs(float(difference)) > mdc
    )
