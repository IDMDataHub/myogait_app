"""Unit tests for the small pure helpers in ui/components.py.

Most of this module is Streamlit widgets and is exercised indirectly by
the AppTest smoke tests; this file covers the plain-Python pieces that
don't need a script run.
"""
from __future__ import annotations

from dataclasses import dataclass

from myogait_app.ui.components import _job_label


@dataclass
class _FakeJob:
    video_name: str
    model: str
    study: dict


def test_job_label_includes_patient_and_condition_when_tagged():
    job = _FakeJob("markers.c3d", "c3d-import", {"patient_id": "P03", "condition": "walk"})
    assert _job_label(job) == "markers.c3d — c3d-import  (P03 · walk)"


def test_job_label_omits_the_parenthetical_when_untagged():
    job = _FakeJob("clip.mp4", "sapiens2-l", {})
    assert _job_label(job) == "clip.mp4 — sapiens2-l"


def test_job_label_uses_whichever_study_field_is_present():
    job = _FakeJob("clip.mp4", "sapiens2-l", {"patient_id": "P09"})
    assert _job_label(job) == "clip.mp4 — sapiens2-l  (P09)"
