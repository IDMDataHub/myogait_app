"""Outlier-cycle rejection is on by default and delegates to myogait."""
from myogait_app.pipeline import CyclesConfig


def test_reject_outliers_default_on():
    assert CyclesConfig().reject_outliers is True


def test_sidebar_cycles_section_keeps_direction_and_outlier_flags():
    """The expert cycles section must carry filter_direction / reject_outliers
    through (they were silently reset before 0.10.6)."""
    import inspect

    from myogait_app.ui import sidebar

    src = inspect.getsource(sidebar._cycles_section)
    assert "filter_direction=filter_direction" in src
    assert "reject_outliers=reject_outliers" in src


def test_validated_backend_is_sapiens2():
    from myogait_app.runtime import BACKENDS, VALIDATED_BACKEND

    assert VALIDATED_BACKEND == "sapiens2-quick"
    assert VALIDATED_BACKEND in {b.name for b in BACKENDS}


def test_unnamed_recordings_never_pair():
    from myogait_app import pooling

    src = __import__("inspect").getsource(pooling)
    assert 'in ("", "?")' in src
