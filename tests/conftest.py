from __future__ import annotations

import pytest


@pytest.fixture
def tiny_pivot() -> dict:
    """Minimal synthetic pivot for tests that do not call myogait itself."""
    return {
        "meta": {"fps": 30.0, "width": 1920, "height": 1080},
        "frames": [],
        "events": {"left_hs": [], "right_hs": []},
    }
