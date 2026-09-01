"""The cohort export bundle: every table and figure of a study, on disk.

Streamlit-free and filesystem-pure (writes into a caller-supplied directory),
so it is unit-testable and reusable outside the UI. The UI wraps it with the
zip + provenance + download plumbing the single-run exports already use.

Contents written under *out_dir*:

- ``tables/``: overview by condition, the per-patient per-cycle table
  (every gait cycle, one row), video-vs-reference agreement,
  between-condition MDC comparison, the long-format biomarker table, ICC
  validity and test-retest batteries, Bland-Altman parameters -- each as CSV,
  plus one ``cohort.xlsx`` workbook with a sheet per table.
- ``figures/``: pooled mean±SD angle curves per condition and side (drawn by
  myogait's own matplotlib ``plot_cycles``, so the exported figure is the
  package's figure, not a lookalike), plus Bland-Altman and between-group
  boxplot figures.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .pooling import (
    SAGITTAL_JOINTS,
    condition_comparison,
    condition_summary,
    group_by_condition,
    overall_agreement,
    pool_cycles,
)
from .reliability import (
    biomarker_table,
    retest_battery,
    validity_battery,
)


def write_cohort_bundle(
    runs: list,
    out_dir: Path,
    *,
    joints: tuple[str, ...] = SAGITTAL_JOINTS,
    sides: tuple[str, ...] = ("left", "right"),
    dpi: int = 300,
    figure_format: str = "png",
) -> Path:
    """Write the full cohort bundle into *out_dir* and return it."""
    out_dir = Path(out_dir)
    tables = out_dir / "tables"
    figures = out_dir / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)

    ok_runs = [r for r in runs if r.ok]
    groups = group_by_condition(ok_runs)
    frames: dict[str, pd.DataFrame] = {}

    frames["overview_by_condition"] = _overview_frame(groups, joints)
    frames["cycles_by_patient"] = _cycles_frame(ok_runs, joints)
    frames["biomarkers_long"] = pd.DataFrame(biomarker_table(ok_runs, joints))
    frames["agreement_by_joint"] = _agreement_frame(ok_runs, joints, sides)
    frames["condition_comparison_mdc"] = _comparison_frame(groups, joints)
    params = tuple(frames["biomarkers_long"]["parameter"].unique()) \
        if not frames["biomarkers_long"].empty else ()
    frames["icc_validity"], frames["bland_altman"] = _validity_frames(ok_runs, params, joints)
    frames["icc_retest"] = _retest_frame(ok_runs, params, joints)

    for name, frame in frames.items():
        frame.to_csv(tables / f"{name}.csv", index=False)
    with pd.ExcelWriter(tables / "cohort.xlsx") as writer:
        for name, frame in frames.items():
            # Excel sheet names are capped at 31 chars.
            frame.to_excel(writer, sheet_name=name[:31], index=False)

    _write_figures(groups, ok_runs, figures, joints, sides, params,
                   dpi=dpi, figure_format=figure_format)
    return out_dir


# ── Tables ───────────────────────────────────────────────────────────


def _overview_frame(groups: dict, joints) -> pd.DataFrame:
    rows = []
    for label, runs in groups.items():
        summary = condition_summary(runs, joints)
        row = {
            "condition": label,
            "n_patients": summary["n_patients"],
            "n_runs": summary["n_runs"],
            "n_reference": summary["n_reference"],
            "n_cycles": summary["n_cycles"],
            "duration_s": summary.get("duration_s"),
            "step_length_m": summary.get("step_length_m"),
        }
        row.update({f"spatio_{k}": v for k, v in summary["spatiotemporal"].items()})
        row.update({f"{j}_rom_deg": summary["rom_deg"].get(j) for j in joints})
        rows.append(row)
    return pd.DataFrame(rows)


def _cycles_frame(runs, joints) -> pd.DataFrame:
    """One row per gait cycle: the per-patient, per-cycle CSV.

    The finest export -- every cycle of every run, tagged by patient / run /
    group / condition / side, with its per-joint ROM, peak and minimum. This
    is what feeds a stats package (mixed models, per-cycle variability) that
    the aggregated tables cannot.
    """
    rows = []
    for run in runs:
        for index, cycle in enumerate((run.cycles or {}).get("cycles", [])):
            angles = cycle.get("angles_normalized") or {}
            row = {
                "patient": run.patient, "run": run.run, "group": run.group,
                "condition": run.condition,
                "kind": "reference" if run.is_reference else "video",
                "side": cycle.get("side"),
                "cycle_id": cycle.get("cycle_id", index),
                "duration_s": cycle.get("duration"),
                "stance_pct": cycle.get("stance_pct"),
            }
            for joint in joints:
                wave = angles.get(joint)
                if wave:
                    finite = [float(v) for v in wave
                              if isinstance(v, (int, float)) and np.isfinite(v)]
                    if len(finite) >= 2:
                        row[f"{joint}_rom_deg"] = max(finite) - min(finite)
                        row[f"{joint}_peak_deg"] = max(finite)
                        row[f"{joint}_min_deg"] = min(finite)
            rows.append(row)
    return pd.DataFrame(rows)


def _agreement_frame(runs, joints, sides) -> pd.DataFrame:
    agreement = overall_agreement(runs, joints, sides)
    if agreement is None:
        return pd.DataFrame()
    return pd.DataFrame(agreement["per_joint_side"])


def _comparison_frame(groups: dict, joints) -> pd.DataFrame:
    labels = list(groups)
    rows = []
    for i, a in enumerate(labels):
        for b in labels[i + 1:]:
            for row in condition_comparison(groups[a], groups[b], joints=joints):
                rows.append({"condition_a": a, "condition_b": b, **row})
    return pd.DataFrame(rows)


def _validity_frames(runs, params, joints) -> tuple[pd.DataFrame, pd.DataFrame]:
    icc_rows, ba_rows = [], []
    for entry in validity_battery(runs, params, joints):
        result, ba = entry["icc"], entry["bland_altman"]
        icc_rows.append({
            "parameter": entry["parameter"],
            "n_patients": entry["n_patients"],
            "icc2_1": result.value if result else None,
            "n": result.n if result else None,
        })
        if ba is not None:
            ba_rows.append({
                "parameter": entry["parameter"], "n": ba.n, "bias": ba.bias,
                "sd": ba.sd, "loa_low": ba.loa_low, "loa_high": ba.loa_high,
            })
    return pd.DataFrame(icc_rows), pd.DataFrame(ba_rows)


def _retest_frame(runs, params, joints) -> pd.DataFrame:
    rows = []
    for entry in retest_battery(runs, params, joints):
        result, icc2k = entry["icc"], entry.get("icc2k")
        rows.append({
            "parameter": entry["parameter"],
            "n_patients": entry["n_patients"], "k": entry["k"],
            "icc3_1": result.value if result else None,
            "icc3_1_ci_low": result.ci95[0] if result and result.ci95 else None,
            "icc3_1_ci_high": result.ci95[1] if result and result.ci95 else None,
            "icc2_k": icc2k.value if icc2k else None,
        })
    return pd.DataFrame(rows)


# ── Figures (matplotlib, print-grade) ────────────────────────────────


def _write_figures(groups, runs, figures: Path, joints, sides, params,
                   *, dpi: int, figure_format: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    # Pooled angle curves: myogait's own figure, one per condition and side.
    try:
        from myogait.plotting import plot_cycles
    except Exception:  # pragma: no cover - myogait is a hard dependency
        plot_cycles = None
    if plot_cycles is not None:
        for label, condition_runs in groups.items():
            pooled = pool_cycles(condition_runs, joints)
            for side in sides:
                if not pooled["summary"].get(side, {}).get("n_cycles"):
                    continue
                try:
                    fig = plot_cycles(pooled, side=side, joints=list(joints))
                    fig.savefig(
                        figures / f"curves_{_safe(label)}_{side}.{figure_format}",
                        dpi=dpi, bbox_inches="tight",
                    )
                    plt.close(fig)
                except Exception:  # noqa: BLE001 - a figure must not sink the bundle
                    plt.close("all")

    # Bland-Altman per parameter with enough pairs.
    for entry in validity_battery(runs, params, joints):
        ba = entry["bland_altman"]
        if ba is None:
            continue
        fig, ax = plt.subplots(figsize=(5.4, 3.4))
        ax.scatter(ba.means, ba.diffs, s=28, alpha=0.75)
        ax.axhline(ba.bias, lw=1.8, label=f"bias {ba.bias:+.2f}")
        for value in (ba.loa_low, ba.loa_high):
            ax.axhline(value, lw=1.2, ls="--")
        ax.axhline(0, lw=0.8, alpha=0.4)
        ax.set_xlabel("Mean of the two methods")
        ax.set_ylabel("Difference (video − reference)")
        ax.set_title(f"Bland-Altman — {entry['parameter']}", fontsize=10, loc="left")
        ax.legend(frameon=False, fontsize=8)
        fig.savefig(figures / f"bland_altman_{_safe(entry['parameter'])}.{figure_format}",
                    dpi=dpi, bbox_inches="tight")
        plt.close(fig)

    # Between-group boxplots when at least two conditions exist.
    labels = list(groups)
    if len(labels) >= 2:
        table = biomarker_table(runs, joints)
        for parameter in params:
            data = [
                [r["value"] for r in table
                 if r["parameter"] == parameter and r["condition"] == label]
                for label in labels
            ]
            if not any(data):
                continue
            fig, ax = plt.subplots(figsize=(5.0, 3.4))
            ax.boxplot(data, tick_labels=labels)
            for i, values in enumerate(data, start=1):
                if values:
                    x = np.random.default_rng(0).normal(i, 0.04, size=len(values))
                    ax.scatter(x, values, s=18, alpha=0.6)
            ax.set_ylabel(parameter)
            ax.set_title(f"Groups — {parameter}", fontsize=10, loc="left")
            fig.savefig(figures / f"boxplot_{_safe(parameter)}.{figure_format}",
                        dpi=dpi, bbox_inches="tight")
            plt.close(fig)


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(name))
