"""Cohort export bundle: file tree, tables and figures on synthetic runs."""
from __future__ import annotations

import numpy as np

from myogait_app.cohort_export import write_cohort_bundle
from myogait_app.pooling import RunResult


def _cycles(rom: float) -> dict:
    wave = np.linspace(0.0, rom, 101).tolist()
    return {"cycles": [
        {"side": side, "cycle_id": i,
         "angles_normalized": {j: wave for j in ("hip", "knee", "ankle")}}
        for i, side in enumerate(("left", "right"))
    ], "summary": {}}


def _run(patient, kind="video", rom=30.0, run="r1", condition="base") -> RunResult:
    return RunResult(
        name=f"{patient}_{run}_{kind}",
        study={"patient_id": patient, "run": run, "condition": condition},
        ok=True, kind=kind, cycles=_cycles(rom),
        stats={"spatiotemporal": {"cadence_steps_per_min": 108.0}},
    )


def _cohort() -> list[RunResult]:
    runs = []
    for i in range(6):
        runs.append(_run(f"P{i}", "video", rom=30.0 + i, condition="pre"))
        runs.append(_run(f"P{i}", "vicon", rom=32.0 + i, condition="pre"))
        runs.append(_run(f"P{i}", "video", rom=25.0 + i, run="r2", condition="post"))
    return runs


def test_bundle_writes_expected_tree(tmp_path):
    out = write_cohort_bundle(_cohort(), tmp_path / "bundle", dpi=80)
    tables = out / "tables"
    figures = out / "figures"
    expected = {
        "overview_by_condition.csv", "biomarkers_long.csv",
        "agreement_by_joint.csv", "condition_comparison_mdc.csv",
        "icc_validity.csv", "icc_retest.csv", "bland_altman.csv",
        "cohort.xlsx",
    }
    assert expected.issubset({p.name for p in tables.iterdir()})
    names = {p.name for p in figures.iterdir()}
    # Pooled curves for both conditions and sides, BA plots, boxplots.
    assert any(n.startswith("curves_pre") for n in names)
    assert any(n.startswith("curves_post") for n in names)
    assert any(n.startswith("bland_altman_") for n in names)
    assert any(n.startswith("boxplot_") for n in names)


def test_bundle_tables_have_content(tmp_path):
    import pandas as pd

    out = write_cohort_bundle(_cohort(), tmp_path / "bundle", dpi=80)
    bio = pd.read_csv(out / "tables" / "biomarkers_long.csv")
    assert {"patient", "parameter", "value", "condition", "kind"} <= set(bio.columns)
    assert (bio["parameter"] == "hip_rom").any()
    overview = pd.read_csv(out / "tables" / "overview_by_condition.csv")
    assert set(overview["condition"]) == {"pre", "post"}
    # The xlsx opens and carries a sheet per table.
    sheets = pd.ExcelFile(out / "tables" / "cohort.xlsx").sheet_names
    assert "biomarkers_long" in sheets and "icc_validity" in sheets


def test_bundle_has_per_patient_per_cycle_csv(tmp_path):
    import pandas as pd

    out = write_cohort_bundle(_cohort(), tmp_path / "bundle", dpi=80)
    cycles = pd.read_csv(out / "tables" / "cycles_by_patient.csv")
    assert {"patient", "run", "group", "condition", "side", "cycle_id",
            "hip_rom_deg"} <= set(cycles.columns)
    # One row per cycle: 6 video patients x (2 pre + 2 post cycles) + 6 refs x 2.
    assert len(cycles) == sum(len(r.cycles["cycles"]) for r in _cohort())
    assert (cycles["hip_rom_deg"] > 0).all()
    assert set(cycles["condition"]) == {"pre", "post"}


def test_bundle_gracious_on_video_only_cohort(tmp_path):
    runs = [_run(f"P{i}", "video", rom=30.0 + i) for i in range(3)]
    out = write_cohort_bundle(runs, tmp_path / "bundle", dpi=80)
    # No reference and one condition: agreement/BA empty but present, no crash.
    assert (out / "tables" / "agreement_by_joint.csv").exists()
    assert (out / "tables" / "cohort.xlsx").exists()


def test_bundle_respects_figure_format(tmp_path):
    out = write_cohort_bundle(_cohort(), tmp_path / "bundle", dpi=80,
                              figure_format="pdf")
    figures = {p.suffix for p in (out / "figures").iterdir()}
    assert figures == {".pdf"}


def test_bundle_joint_selection(tmp_path):
    import pandas as pd

    out = write_cohort_bundle(_cohort(), tmp_path / "bundle", dpi=80,
                              joints=("knee",))
    bio = pd.read_csv(out / "tables" / "biomarkers_long.csv")
    rom_params = {p for p in bio["parameter"] if p.endswith("_rom")}
    assert rom_params == {"knee_rom"}
