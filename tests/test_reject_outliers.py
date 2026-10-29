"""Outlier-cycle rejection is on by default and delegates to myogait."""
from myogait_app.pipeline import CyclesConfig


def test_reject_outliers_default_on():
    assert CyclesConfig().reject_outliers is True
