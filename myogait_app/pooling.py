"""Pool many pivot JSONs and aggregate them by study condition.

Streamlit-free and testable. Each output JSON carries the identifiers the
Data page wrote into it (``data["study"]`` = patient / run / group /
condition; see ``page_data._study_form``). This module loads a batch of
those pivots, runs the same downstream pipeline the rest of the app uses,
and groups the per-run results by condition so a whole study can be read
at once -- roughly the analyses of the validation report, per condition,
with the individual runs still reachable underneath.

The per-condition charts reuse the app's own kinematics figures
(``charts.kinematics``): those read ``cycles["cycles"]`` and
``cycles["summary"]``, so :func:`pool_cycles` merges the runs' cycles and
recomputes the per-side summary in exactly that shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import numpy as np

from .pipeline import PipelineConfig, PipelineRunner

#: The sagittal joints every figure and summary is built around.
SAGITTAL_JOINTS = ("hip", "knee", "ankle")

#: Study key used to group; falls back to this when a JSON has no
#: condition recorded (e.g. an older export, or a C3D import not yet
#: tagged). Kept explicit so the UI can say what "unspecified" means.
UNSPECIFIED = "unspecified"


@dataclass
class RunResult:
    """One recording after the downstream pipeline has run on it."""

    name: str
    study: dict
    ok: bool
    cycles: dict | None = None
    stats: dict | None = None
    error: str = ""

    def _s(self, key: str, default: str = "") -> str:
        value = self.study.get(key)
        return str(value) if value not in (None, "") else default

    @property
    def condition(self) -> str:
        return self._s("condition", UNSPECIFIED)

    @property
    def patient(self) -> str:
        return self._s("patient_id", "?")

    @property
    def run(self) -> str:
        return self._s("run", self.name)

    @property
    def group(self) -> str:
        return self._s("group")

    @property
    def n_cycles(self) -> int:
        return len((self.cycles or {}).get("cycles", []))


def load_run(path, config: PipelineConfig | None = None) -> RunResult:
    """Load one pivot JSON and run the pipeline, capturing any failure.

    Never raises: a bad file becomes an ``ok=False`` result carrying the
    reason, so one unreadable recording does not abort a whole batch.
    """
    from myogait import load_json

    config = config or PipelineConfig()
    name = Path(path).name
    try:
        data = load_json(str(path))
    except Exception as exc:  # noqa: BLE001 - reported per-run, not raised
        return RunResult(name=name, study={}, ok=False, error=f"read: {exc}")

    study = dict(data.get("study") or {})
    try:
        result = PipelineRunner(data, source_key=str(path)).run(config)
    except Exception as exc:  # noqa: BLE001
        return RunResult(name=name, study=study, ok=False, error=f"pipeline: {exc}")

    if not result.ok:
        failed = result.failed_stage
        reason = f"{failed.name}: {failed.error}" if failed else "pipeline failed"
        return RunResult(name=name, study=study, ok=False, error=reason)

    return RunResult(
        name=name, study=study, ok=True,
        cycles=result.cycles, stats=result.stats,
    )


def load_runs(paths: Iterable, config: PipelineConfig | None = None) -> list[RunResult]:
    """Load and run a batch of pivots, preserving order."""
    return [load_run(p, config) for p in paths]


def group_by_condition(runs: Iterable[RunResult]) -> dict[str, list[RunResult]]:
    """Group the successful runs by their study condition (sorted by name)."""
    groups: dict[str, list[RunResult]] = {}
    for run in runs:
        if run.ok:
            groups.setdefault(run.condition, []).append(run)
    return dict(sorted(groups.items()))


def pool_cycles(runs: Iterable[RunResult]) -> dict:
    """Merge several runs' cycles into one figure-ready ``cycles`` dict.

    Concatenates every cycle and recomputes the per-side ``summary`` (mean
    and SD curve per joint, plus ``n_cycles``) over the pooled set, so the
    condition-level figures show the aggregate rather than any single run.
    """
    merged: list[dict] = []
    for index, run in enumerate(runs):
        for cycle in (run.cycles or {}).get("cycles", []):
            copy = dict(cycle)
            # Namespace the id so cycles from different runs stay distinct.
            copy["cycle_id"] = f"{index}:{cycle.get('cycle_id')}"
            merged.append(copy)

    summary: dict[str, dict] = {}
    for side in ("left", "right"):
        side_cycles = [c for c in merged if c.get("side") == side]
        entry: dict = {"n_cycles": len(side_cycles)}
        for joint in SAGITTAL_JOINTS:
            curves = [
                c["angles_normalized"][joint]
                for c in side_cycles
                if (c.get("angles_normalized") or {}).get(joint) is not None
                and len(c["angles_normalized"][joint]) == 101
            ]
            if curves:
                arr = np.asarray(curves, dtype=float)
                entry[f"{joint}_mean"] = arr.mean(axis=0).tolist()
                entry[f"{joint}_std"] = arr.std(axis=0).tolist()
        summary[side] = entry

    return {"cycles": merged, "summary": summary}


def _spatiotemporal(run: RunResult) -> dict:
    return (run.stats or {}).get("spatiotemporal") or {}


def condition_summary(runs: list[RunResult]) -> dict:
    """Aggregate figures for one condition: counts, spatiotemporal, ROM.

    Spatiotemporal metrics are averaged over runs (any numeric key present
    in at least one run's ``stats["spatiotemporal"]``). ROM per joint is
    the range of the pooled mean curve, so it matches the figures.
    """
    runs = list(runs)
    pooled = pool_cycles(runs)

    # Mean over runs of every numeric spatiotemporal metric.
    keys: list[str] = []
    for run in runs:
        for key in _spatiotemporal(run):
            if key not in keys:
                keys.append(key)
    spatiotemporal: dict[str, float] = {}
    for key in keys:
        values = [
            float(_spatiotemporal(run)[key])
            for run in runs
            if isinstance(_spatiotemporal(run).get(key), (int, float))
        ]
        if values:
            spatiotemporal[key] = float(np.mean(values))

    rom: dict[str, float] = {}
    for joint in SAGITTAL_JOINTS:
        spans = []
        for side in ("left", "right"):
            mean = (pooled["summary"].get(side) or {}).get(f"{joint}_mean")
            if mean:
                spans.append(float(np.nanmax(mean) - np.nanmin(mean)))
        if spans:
            rom[joint] = float(np.mean(spans))

    return {
        "n_runs": len(runs),
        "n_patients": len({run.patient for run in runs}),
        "n_cycles": len(pooled["cycles"]),
        "spatiotemporal": spatiotemporal,
        "rom_deg": rom,
        "cycles": pooled,
    }
