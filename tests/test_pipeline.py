from __future__ import annotations

import pytest


def test_pipeline_requires_the_optional_myogait_dependency():
    pytest.importorskip("myogait")
    from myogait_app.pipeline import PipelineConfig, PipelineRunner

    runner = PipelineRunner({"frames": [], "meta": {"fps": 30}}, "synthetic")
    result = runner.run(PipelineConfig())
    assert result.outcomes
