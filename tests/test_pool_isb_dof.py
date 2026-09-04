"""Advanced -> Groups -> One group also plots the ISB abd/add + rotation
DOF when a marker (C3D) source in the cohort carried them (audit B2
extension) -- previously the pooled cycle curves were SAGITTAL_JOINTS-only
regardless of what the loaded runs actually had.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from myogait_app.pooling import RunResult

APP_PY = Path(__file__).resolve().parents[1] / "app.py"


def _sagittal_curve() -> list[float]:
    return [float(i) for i in range(101)]


def _isb_curve() -> list[float]:
    return [float(i) / 5.0 for i in range(101)]


def _cycles_with_isb_dof() -> dict:
    return {
        "cycles": [
            {"side": "left", "cycle_id": 1, "angles_normalized": {
                "hip": _sagittal_curve(), "knee": _sagittal_curve(), "ankle": _sagittal_curve(),
                "hip_abd_add_deg": _isb_curve(),
            }},
            {"side": "right", "cycle_id": 2, "angles_normalized": {
                "hip": _sagittal_curve(), "knee": _sagittal_curve(), "ankle": _sagittal_curve(),
                "hip_abd_add_deg": _isb_curve(),
            }},
        ],
        "summary": {},
    }


def _cycles_sagittal_only() -> dict:
    return {
        "cycles": [
            {"side": "left", "cycle_id": 1, "angles_normalized": {
                "hip": _sagittal_curve(), "knee": _sagittal_curve(), "ankle": _sagittal_curve(),
            }},
        ],
        "summary": {},
    }


def _cohort_with_isb_reference() -> list[RunResult]:
    study = {"patient_id": "P01", "run": "visit-01", "condition": "baseline"}
    return [
        RunResult("video.json", study, ok=True, kind="video", duration_s=2.0,
                  cycles=_cycles_sagittal_only(), stats={}),
        RunResult("reference.json", study, ok=True, kind="vicon", duration_s=2.0,
                  cycles=_cycles_with_isb_dof(), stats={}),
    ]


def _run_one_group(runs: list[RunResult]):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(APP_PY), default_timeout=60)
    app.run()
    app.session_state["nav_page"] = "Advanced"
    app.session_state["pool_runs"] = runs
    app.run()
    assert not app.exception
    return app


def test_isb_dof_curve_plotted_when_a_run_carries_it():
    app = _run_one_group(_cohort_with_isb_reference())

    captions = " ".join(c.value for c in app.caption)
    assert "ISB abd/add + rotation DOF" in captions


def test_no_isb_caption_when_nothing_carries_it():
    study = {"patient_id": "P01", "run": "visit-01", "condition": "baseline"}
    runs = [RunResult("video.json", study, ok=True, kind="video", duration_s=2.0,
                       cycles=_cycles_sagittal_only(), stats={})]
    app = _run_one_group(runs)

    captions = " ".join(c.value for c in app.caption)
    assert "ISB abd/add + rotation DOF" not in captions
