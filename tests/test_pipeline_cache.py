"""Contracts for PipelineRunner's dependency-free LRU cache."""

from __future__ import annotations

from myogait_app.pipeline import PipelineRunner


def test_pipeline_cache_reuses_values_and_evicts_the_least_recent_entry() -> None:
    runner = PipelineRunner({"frames": []}, "fixture", max_entries=2)
    produced: list[str] = []

    def produce(value: str) -> str:
        produced.append(value)
        return value

    assert runner._memo(("one",), lambda: produce("one")) == ("one", False)
    assert runner._memo(("two",), lambda: produce("two")) == ("two", False)
    # Refresh one, so two becomes the least-recently-used entry.
    assert runner._memo(("one",), lambda: produce("unexpected")) == ("one", True)
    assert runner._memo(("three",), lambda: produce("three")) == ("three", False)

    assert produced == ["one", "two", "three"]
    assert runner.cache_stats == {"hits": 1, "misses": 3, "entries": 2}
    assert ("one",) in runner._cache
    assert ("three",) in runner._cache
    assert ("two",) not in runner._cache


def test_pipeline_cache_can_be_cleared_without_recreating_the_runner() -> None:
    runner = PipelineRunner({"frames": []}, "fixture", max_entries=1)
    runner._memo(("entry",), lambda: {"value": 1})

    runner.clear_cache()

    assert runner.cache_stats["entries"] == 0
    assert runner._cache == {}
