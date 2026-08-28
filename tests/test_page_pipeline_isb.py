"""_available_isb_cycle_joints and the ISB normative-joint mapping.

Pure-function slices of page_pipeline.py's Cycles tab -- not the full
Streamlit render (tests/test_smoke_pages.py's AppTest already exercises
that end to end). These just pin down the "only offer a joint the loaded
run actually has data for" contract from CLAUDE.md's ISB reconstruction
section.
"""

from __future__ import annotations

from myogait_app.charts import kinematics as K
from myogait_app.ui.page_pipeline import _available_isb_cycle_joints


def test_available_isb_cycle_joints_empty_when_no_isb_summary():
    cycles = {"summary": {"left": {"hip_mean": [0.0] * 101}, "right": {}}}
    assert _available_isb_cycle_joints(cycles) == []


def test_available_isb_cycle_joints_empty_for_none_or_missing_cycles():
    assert _available_isb_cycle_joints(None) == []
    assert _available_isb_cycle_joints({}) == []


def test_available_isb_cycle_joints_reports_present_dof_in_a_stable_order():
    cycles = {
        "summary": {
            "left": {
                "hip_mean": [0.0] * 101,
                "ankle_int_ext_rot_deg_mean": [0.0] * 101,
                "hip_abd_add_deg_mean": [0.0] * 101,
            },
            "right": {
                "knee_abd_add_deg_mean": [0.0] * 101,
            },
        }
    }
    result = _available_isb_cycle_joints(cycles)
    # In K.ISB_CYCLE_JOINTS's declared order, not insertion order.
    assert result == ["hip_abd_add_deg", "knee_abd_add_deg", "ankle_int_ext_rot_deg"]


def test_isb_normative_joint_mapping_covers_only_hip_and_knee_abd_add():
    assert K.ISB_NORMATIVE_JOINT == {
        "hip_abd_add_deg": "hip_adduction",
        "knee_abd_add_deg": "knee_valgus",
    }
    # Ankle abd/add and every rotation DOF fall through unmapped -- there
    # is no normative band for them anywhere in myogait yet.
    for joint in ("ankle_abd_add_deg", "hip_int_ext_rot_deg",
                  "knee_int_ext_rot_deg", "ankle_int_ext_rot_deg"):
        assert joint not in K.ISB_NORMATIVE_JOINT
