"""The app-level wiring of the opt-in ankle push-off restoration. The
numerical behaviour is validated in myogait's own test_ankle_dynamics; here we
only check the config flag and that the runner accepts it."""
from __future__ import annotations

from dataclasses import replace

import pytest


def test_flag_defaults_on_and_is_settable():
    # On by default: validated, cannot fabricate an absent push-off, and only
    # ever adds the systematic deficit back. Still switchable (it changes the
    # ankle measurement on every source).
    from myogait_app.pipeline import PipelineConfig
    cfg = PipelineConfig()
    assert cfg.restore_ankle_dynamics is True
    assert replace(cfg, restore_ankle_dynamics=False).restore_ankle_dynamics is False


def test_flag_participates_in_the_analysis_cache_key():
    # Two configs differing only by the flag must not collide in the cache.
    from myogait_app.pipeline import PipelineConfig
    a = PipelineConfig()
    b = replace(a, restore_ankle_dynamics=False)
    assert a.to_dict()["restore_ankle_dynamics"] != b.to_dict()["restore_ankle_dynamics"]


def test_restore_function_is_exported_by_myogait():
    pytest.importorskip("myogait")
    import myogait as mg
    assert callable(getattr(mg, "restore_ankle_dynamics", None))


def test_runner_accepts_the_flag():
    pytest.importorskip("myogait")
    from myogait_app.pipeline import PipelineConfig, PipelineRunner
    runner = PipelineRunner({"frames": [], "meta": {"fps": 30}}, "synthetic")
    result = runner.run(replace(PipelineConfig(), restore_ankle_dynamics=True))
    assert result.outcomes  # runs to completion (no cycles on an empty pivot, but no crash)
