"""Angle-correction settings, exercised in combination (audit DEV-06).

Each correction has its own unit coverage; what was missing is a check
that turning several on *together* still produces a usable run rather than
a silently-wrong one. The guided cohort scopes (Analysis) and the Phase 3
group views run the pipeline over many recordings at once, so a bad
interaction between, say, perspective + detrend or canonicalize + frontal
would otherwise only surface as "one patient's curve looks odd".

These run the synthetic demo (markerless, so ISB reconstruction is a
no-op) through each combination and assert: the run completes, cycles
survive, every normalised angle value is finite, and a correction that is
switched on actually moves the output -- i.e. it is not being quietly
skipped when combined with another.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest


def _run(angles_overrides=None, bias_overrides=None):
    pytest.importorskip("myogait")
    from myogait_app.demo import make_demo_data
    from myogait_app.pipeline import PipelineConfig, PipelineRunner

    config = PipelineConfig()
    if angles_overrides:
        config = config.with_stage("angles", replace(config.angles, **angles_overrides))
    if bias_overrides:
        config = config.with_stage("bias", replace(config.bias, **bias_overrides))
    runner = PipelineRunner(make_demo_data(), "demo-combo")
    return runner.run(config)


def _all_cycle_values(cycles: dict) -> list[float]:
    out: list[float] = []
    for cycle in (cycles or {}).get("cycles", []):
        for series in (cycle.get("angles_normalized") or {}).values():
            out.extend(float(v) for v in series)
    return out


def _hip_curve(result) -> list[float]:
    for cycle in (result.cycles or {}).get("cycles", []):
        series = (cycle.get("angles_normalized") or {}).get("hip")
        if series:
            return [float(v) for v in series]
    return []


COMBINATIONS = {
    "perspective + detrend": {"perspective": True, "detrend": True},
    "canonicalize + perspective + frontal": {
        "canonicalize_signs": True, "perspective": True, "frontal": True,
    },
    "every angle correction at once": {
        "canonicalize_signs": True, "perspective": True, "detrend": True,
        "frontal": True, "c3d_reference_ankle": True, "isb_reconstruction": True,
    },
    "nothing (all corrections off)": {
        "canonicalize_signs": False, "perspective": False, "detrend": False,
        "frontal": False, "c3d_reference_ankle": False, "isb_reconstruction": False,
    },
}


@pytest.mark.parametrize("label", list(COMBINATIONS))
def test_angle_correction_combination_produces_a_finite_usable_run(label):
    result = _run(COMBINATIONS[label])
    assert result.ok, f"{label}: pipeline failed at {result.failed_stage}"
    assert result.n_cycles, f"{label}: no cycle survived"
    values = _all_cycle_values(result.cycles)
    assert values, f"{label}: cycles carry no angle series"
    assert all(math.isfinite(v) for v in values), f"{label}: non-finite angle value"


def test_isb_plus_bias_together_does_not_crash_the_run():
    """The UI hard-blocks bias while ISB reconstruction is on; the pipeline
    itself trusts the caller (CLAUDE.md). If a caller does pass both, the
    run must still complete rather than raise -- ISB is a no-op on this
    markerless fixture, so bias then applies to the sagittal angles as it
    always would."""
    result = _run(
        angles_overrides={"isb_reconstruction": True, "perspective": True},
        bias_overrides={"ankle": True, "hip": True, "knee": True},
    )
    assert result.ok, f"ISB + bias: pipeline failed at {result.failed_stage}"
    assert result.n_cycles


def test_perspective_actually_changes_the_output_when_combined_with_detrend():
    """Guards against a correction being silently ordered out of effect by
    another: detrend runs after perspective, and both must land."""
    base = _hip_curve(_run({"perspective": False, "detrend": True}))
    both = _hip_curve(_run({"perspective": True, "detrend": True}))
    assert base and both
    assert base != both, "enabling perspective on top of detrend changed nothing"
