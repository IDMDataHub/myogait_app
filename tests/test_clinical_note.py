"""The shared clinical-note component (D1) and its accelerometry helper.

One visual language for clinical caveats: A2 (Markerbased vs Monocular) and B5
(Accelerometry) both render the *same* non-comparability warning through the
shared helper rather than each re-phrasing it (DEV-01 / DOC-01).
"""
from __future__ import annotations

import pytest


def _run(body: str):
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_string(body, default_timeout=30)
    app.run()
    assert not app.exception
    return app


def test_clinical_note_dispatches_by_kind():
    pytest.importorskip("streamlit")
    app = _run(
        "from myogait_app.ui.components import clinical_note\n"
        "clinical_note('info', 'i')\n"
        "clinical_note('warning', 'w')\n"
        "clinical_note('danger', 'd')\n"
        "clinical_note('nonsense', 'fallback')\n"
    )
    assert [e.value for e in app.info] == ["i", "fallback"]  # unknown kind -> info
    assert [e.value for e in app.warning] == ["w"]
    assert [e.value for e in app.error] == ["d"]


def test_accelerometry_note_is_a_single_shared_warning():
    pytest.importorskip("streamlit")
    from myogait_app.ui.components import ACCELEROMETRY_NON_COMPARABLE

    app = _run(
        "from myogait_app.ui.components import accelerometry_non_comparable_note\n"
        "accelerometry_non_comparable_note()\n"
    )
    assert len(app.warning) == 1
    assert app.warning[0].value == ACCELEROMETRY_NON_COMPARABLE
    assert "not the same numbers" in ACCELEROMETRY_NON_COMPARABLE
