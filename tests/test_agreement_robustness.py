"""Edge-case regressions for agreement metrics."""

import numpy as np

from myogait_app.agreement import curve_metrics


def test_curve_metrics_rejects_curves_too_short_for_shape_metrics():
    assert curve_metrics([1.0, 2.0], [1.0, 2.0]) == {}


def test_curve_metrics_rejects_infinite_values():
    reference = np.linspace(0.0, 1.0, 101)
    video = reference.copy()
    video[12] = np.inf

    assert curve_metrics(video, reference) == {}
