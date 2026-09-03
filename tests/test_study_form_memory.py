"""_study_form's cross-tab Patient ID / Condition memory.

New assessment's video and C3D tabs each call _study_form with their own
key_prefix, so each has always kept its own independent widget state --
both defaulting to "P001"/"baseline" regardless of what was typed in the
other. The audit (UX-04) flagged this as the fragile part of the app's
flagship "pair a video with its Vicon C3D" workflow: a stray space or
different casing between the two forms silently keeps them from being
paired. This checks that the *second* form a user reaches pre-fills from
whatever the first one currently holds, instead of resetting to the
hardcoded default.

The C3D form is only ever instantiated once a C3D file is actually present
(page_data._c3d_tab returns before calling _study_form otherwise) -- the
harness below reproduces that gating with a session-state flag, since it
is exactly what makes the fix work: the shared default is only read the
*first* time a given key_prefix's widget is created, and in the real app
that first time is always after the video tab (filled first, per the
documented workflow) already set it.
"""

from __future__ import annotations

import pytest


def _two_forms_app() -> None:
    from pathlib import Path

    import streamlit as st

    from myogait_app.ui.page_data import _study_form

    _study_form(Path("video.mp4"), key_prefix="study")
    if st.session_state.get("_c3d_ready"):
        _study_form(Path("static.c3d"), key_prefix="c3d_study")


def test_c3d_form_prefills_patient_id_from_the_already_filled_video_form():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_function(_two_forms_app, default_timeout=30)
    app.run()
    assert app.text_input(key="study_patient").value == "P001"

    app.text_input(key="study_patient").set_value("P042").run()
    assert app.text_input(key="study_patient").value == "P042"

    # The C3D tab is reached for the first time only now (a file was just
    # attached) -- its Patient ID widget has never existed before this run.
    app.session_state["_c3d_ready"] = True
    app.run()

    assert app.text_input(key="c3d_study_patient").value == "P042"


def test_c3d_form_prefills_condition_from_the_already_filled_video_form():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_function(_two_forms_app, default_timeout=30)
    app.run()
    app.text_input(key="study_condition").set_value("post-op").run()

    app.session_state["_c3d_ready"] = True
    app.run()

    assert app.text_input(key="c3d_study_condition").value == "post-op"


def test_a_form_the_user_already_typed_into_is_never_overwritten():
    """The shared default must never clobber a value the user already set
    for that specific tab -- it only ever seeds a widget's *first* render."""
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_function(_two_forms_app, default_timeout=30)
    app.run()
    app.session_state["_c3d_ready"] = True
    app.run()
    app.text_input(key="c3d_study_patient").set_value("P099").run()

    # Now change the video tab's value -- the C3D tab already has its own,
    # user-typed value and must keep it.
    app.text_input(key="study_patient").set_value("P007").run()

    assert app.text_input(key="c3d_study_patient").value == "P099"
