"""Two-condition ROM comparison against the MDC (pooling.condition_comparison).

Pure: RunResult objects are built directly, no Streamlit/myogait needed.
The MDC math itself is covered by test_mdc; here we lock the pooling glue —
per-cycle ROM grouping by subject and the A-vs-B verdict.
"""
from __future__ import annotations

import numpy as np

from myogait_app.pooling import RunResult, condition_comparison, rom_values_by_subject


def _cycle(rom: float, joint: str = "hip") -> dict:
    # A ramp from 0 to `rom` has range-of-motion exactly `rom`.
    wave = np.linspace(0.0, rom, 101).tolist()
    return {"side": "left", "angles_normalized": {j: wave for j in ("hip", "knee", "ankle")}}


def _run(patient: str, condition: str, roms: list[float]) -> RunResult:
    return RunResult(
        name=f"{patient}_{condition}",
        study={"patient_id": patient, "condition": condition},
        ok=True,
        kind="video",
        cycles={"cycles": [_cycle(r) for r in roms]},
    )


def _condition(condition: str, base: float) -> list[RunResult]:
    # 4 patients x 4 near-identical cycles (tiny within-subject jitter -> small Sw).
    jitter = [-1.0, 0.0, 1.0, 0.0]
    return [
        _run(f"P{i}", condition, [base + j for j in jitter])
        for i in range(4)
    ]


def test_rom_values_by_subject_groups_per_patient():
    runs = _condition("A", 30.0)
    vbs = rom_values_by_subject(runs, "hip")
    assert len(vbs) == 4                      # one list per patient
    assert all(len(v) == 4 for v in vbs)      # four cycles each
    assert abs(np.mean([x for sub in vbs for x in sub]) - 30.0) < 0.5


def test_large_change_exceeds_mdc():
    rows = condition_comparison(_condition("A", 30.0), _condition("B", 15.0))
    hip = next(r for r in rows if r["parameter"].startswith("hip"))
    assert abs(hip["a"] - 30.0) < 0.5
    assert abs(hip["b"] - 15.0) < 0.5
    assert abs(hip["delta"] - 15.0) < 0.5
    assert hip["mdc"] is not None and hip["mdc"] < 5.0     # tight repeatability
    assert hip["exceeds"] is True                          # 15 deg >> MDC


def test_no_change_is_within_noise():
    rows = condition_comparison(_condition("A", 30.0), _condition("B", 30.0))
    hip = next(r for r in rows if r["parameter"].startswith("hip"))
    assert abs(hip["delta"]) < 0.5
    assert hip["exceeds"] is False                          # within the MDC


def test_all_three_joints_reported():
    rows = condition_comparison(_condition("A", 30.0), _condition("B", 20.0))
    params = {r["parameter"] for r in rows}
    assert params == {"hip ROM (deg)", "knee ROM (deg)", "ankle ROM (deg)"}


def test_insufficient_cycles_gives_undetermined_mdc():
    # Fewer than MIN_DOF cycles overall -> pooled_sw returns None -> verdict None.
    a = [_run("P0", "A", [30.0, 30.0]), _run("P1", "A", [30.0, 30.0])]
    b = [_run("P0", "B", [20.0, 20.0]), _run("P1", "B", [20.0, 20.0])]
    rows = condition_comparison(a, b)
    hip = next(r for r in rows if r["parameter"].startswith("hip"))
    assert hip["mdc"] is None
    assert hip["exceeds"] is None
    # The values/delta are still reported.
    assert abs(hip["delta"] - 10.0) < 0.5


def test_empty_condition_yields_no_rows():
    assert condition_comparison(_condition("A", 30.0), []) == []
