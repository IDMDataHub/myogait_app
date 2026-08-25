from __future__ import annotations

import pytest

from myogait_app.validation import validate_pivot


@pytest.mark.parametrize(
    ("pivot", "message"),
    [
        ([], "root"),
        ({}, "frames"),
        ({"frames": [{}], "meta": {"fps": 0}}, "fps"),
        ({"frames": ["bad"]}, "Frame 0"),
        ({"frames": [{"landmarks": []}]}, "landmarks"),
    ],
)
def test_invalid_pivots_produce_actionable_errors(pivot, message):
    assert message in " ".join(validate_pivot(pivot))


def test_minimal_valid_pivot_is_accepted():
    assert validate_pivot({"meta": {"fps": 30}, "frames": [{"landmarks": {}}]}) == []
