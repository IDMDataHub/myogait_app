"""Reliability and validity statistics: ICC, Bland-Altman, group biomarkers.

Streamlit-free, numpy-only core (scipy, already present through myogait, is
used only for confidence intervals behind a guarded import), so everything
here is unit-testable and reusable from the export bundle.

Statistical choices
-------------------
- **Validity (markerless video vs a C3D/Vicon reference): ICC(2,1)** --
  two-way random effects, absolute agreement, single measure (Shrout & Fleiss
  1979; McGraw & Wong 1996 ICC(A,1)). The two methods are interchangeable
  "raters" and a systematic offset between video and Vicon *must* penalise
  the coefficient; a consistency form would forgive it.
- **Test-retest (repeated runs of the same method): ICC(3,1)** -- two-way
  mixed effects, consistency, single measure. The sessions are the fixed
  facet; a uniform session shift is not the noise a clinician re-measuring a
  patient cares about. ICC(2,k) is reported alongside when the mean of k runs
  is what gets used in practice.
- **Bland-Altman**: bias = mean(a-b), limits of agreement = bias +/- 1.96*SD
  of the differences; the paired means/differences are kept on the result for
  plotting.

Guard rails mirror :mod:`myogait_app.mdc`: too little data returns ``None``
(the UI must say "not enough paired subjects"), never an unstable number.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .pooling import SAGITTAL_JOINTS, RunResult

#: Minimum subjects / raters for an ICC worth reporting.
MIN_ICC_SUBJECTS = 5
MIN_ICC_RATERS = 2
#: Minimum pairs for a Bland-Altman.
MIN_BA_PAIRS = 3

#: The scalar biomarkers extracted per run. Joint-shaped parameters expand to
#: one entry per selected joint (e.g. ``hip_rom``); the spatiotemporal names
#: are read from ``stats["spatiotemporal"]`` as-is.
SPATIOTEMPORAL_BIOMARKERS = (
    "cadence_steps_per_min",
    "stride_time_mean_s",
    "stance_pct_left",
    "stance_pct_right",
)


# ── ICC ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ICCResult:
    value: float
    form: str
    n: int              # subjects (rows)
    k: int              # raters/sessions (columns)
    msr: float          # between-subjects mean square
    msc: float          # between-raters mean square
    mse: float          # residual mean square
    ci95: tuple[float, float] | None = None


def icc(matrix, form: str = "ICC2_1") -> ICCResult | None:
    """Intraclass correlation over an (n_subjects, k_raters) matrix.

    Forms: ``"ICC2_1"`` (two-way random, absolute agreement, single measure),
    ``"ICC3_1"`` (two-way mixed, consistency, single measure) and ``"ICC2_k"``
    (absolute agreement of the k-rater mean). Rows containing any non-finite
    value are dropped. Returns ``None`` when fewer than
    :data:`MIN_ICC_SUBJECTS` complete rows or :data:`MIN_ICC_RATERS` columns
    remain -- an ICC on less is noise dressed as a coefficient.
    """
    x = np.asarray(matrix, dtype=float)
    if x.ndim != 2:
        return None
    x = x[np.isfinite(x).all(axis=1)]
    n, k = x.shape if x.ndim == 2 else (0, 0)
    if n < MIN_ICC_SUBJECTS or k < MIN_ICC_RATERS:
        return None

    grand = x.mean()
    row_means = x.mean(axis=1)
    col_means = x.mean(axis=0)
    ssr = k * ((row_means - grand) ** 2).sum()      # between subjects
    ssc = n * ((col_means - grand) ** 2).sum()      # between raters
    sst = ((x - grand) ** 2).sum()
    sse = sst - ssr - ssc                            # residual
    msr = ssr / (n - 1)
    msc = ssc / (k - 1)
    mse = sse / ((n - 1) * (k - 1))
    if not all(math.isfinite(v) for v in (msr, msc, mse)):
        return None

    if form == "ICC3_1":
        denom = msr + (k - 1) * mse
        value = (msr - mse) / denom if denom > 0 else float("nan")
    elif form == "ICC2_k":
        denom = msr + (msc - mse) / n
        value = (msr - mse) / denom if denom > 0 else float("nan")
    elif form == "ICC2_1":
        denom = msr + (k - 1) * mse + k * (msc - mse) / n
        value = (msr - mse) / denom if denom > 0 else float("nan")
    else:
        raise ValueError(f"Unknown ICC form: {form!r}")
    if not math.isfinite(value):
        return None

    return ICCResult(
        value=float(value), form=form, n=n, k=k,
        msr=float(msr), msc=float(msc), mse=float(mse),
        ci95=_icc_ci95(form, float(value), n, k, float(msr), float(msc), float(mse)),
    )


def _icc_ci95(form, value, n, k, msr, msc, mse) -> tuple[float, float] | None:
    """Exact F-based 95% CI for ICC(3,1); ``None`` for the ICC(2,*) forms.

    The ICC(3,1) interval is the classical Shrout & Fleiss one and is simple
    and safe. The ICC(2,1) interval needs the Satterthwaite-approximated
    degrees of freedom and is easy to implement subtly wrong -- better to
    show no interval than a wrong one, so the absolute-agreement forms report
    the point estimate alone for now.
    """
    if form != "ICC3_1" or mse <= 0:
        return None
    try:
        from scipy.stats import f as fdist
    except Exception:  # pragma: no cover - scipy ships with myogait
        return None
    try:
        f_obs = msr / mse
        df1, df2 = n - 1, (n - 1) * (k - 1)
        fl = f_obs / fdist.ppf(0.975, df1, df2)
        fu = f_obs * fdist.ppf(0.975, df2, df1)
        lo = (fl - 1.0) / (fl + (k - 1.0))
        hi = (fu - 1.0) / (fu + (k - 1.0))
        lo, hi = float(np.clip(lo, -1.0, 1.0)), float(np.clip(hi, -1.0, 1.0))
        return (min(lo, hi), max(lo, hi))
    except Exception:
        return None


# ── Bland-Altman ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class BlandAltman:
    bias: float
    sd: float
    loa_low: float
    loa_high: float
    n: int
    means: tuple = field(repr=False, default=())
    diffs: tuple = field(repr=False, default=())
    bias_ci95: tuple[float, float] | None = None


def bland_altman(a, b) -> BlandAltman | None:
    """Bland-Altman agreement between paired measurements *a* and *b*.

    ``diff = a - b`` (so a positive bias means *a* over-reads). Pairs with a
    non-finite member are dropped; fewer than :data:`MIN_BA_PAIRS` remaining
    pairs returns ``None``.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    if a.shape != b.shape or a.ndim != 1:
        return None
    keep = np.isfinite(a) & np.isfinite(b)
    a, b = a[keep], b[keep]
    n = int(a.size)
    if n < MIN_BA_PAIRS:
        return None
    diffs = a - b
    means = (a + b) / 2.0
    bias = float(diffs.mean())
    sd = float(diffs.std(ddof=1))
    se = sd / math.sqrt(n)
    return BlandAltman(
        bias=bias, sd=sd,
        loa_low=bias - 1.96 * sd, loa_high=bias + 1.96 * sd, n=n,
        means=tuple(float(v) for v in means),
        diffs=tuple(float(v) for v in diffs),
        bias_ci95=(bias - 1.96 * se, bias + 1.96 * se),
    )


# ── Per-run biomarker extraction ─────────────────────────────────────


def _run_joint_rom(run: RunResult, joint: str) -> float | None:
    """Mean per-cycle ROM of *joint* over one run's cycles (deg)."""
    roms = []
    for cycle in (run.cycles or {}).get("cycles", []):
        wave = (cycle.get("angles_normalized") or {}).get(joint)
        if wave:
            finite = [float(v) for v in wave if isinstance(v, (int, float)) and math.isfinite(v)]
            if len(finite) >= 2:
                roms.append(max(finite) - min(finite))
    return float(np.mean(roms)) if roms else None


def _run_scalars(run: RunResult, joints: tuple[str, ...]) -> dict[str, float]:
    """Every scalar biomarker one run yields, keyed by parameter name."""
    out: dict[str, float] = {}
    for joint in joints:
        rom = _run_joint_rom(run, joint)
        if rom is not None:
            out[f"{joint}_rom"] = rom
    spatio = (run.stats or {}).get("spatiotemporal") or {}
    for key in SPATIOTEMPORAL_BIOMARKERS:
        value = spatio.get(key)
        if isinstance(value, (int, float)) and math.isfinite(value):
            out[key] = float(value)
    step = (run.stats or {}).get("step_length") or {}
    if step.get("unit") == "m":
        lengths = [step.get("step_length_left"), step.get("step_length_right")]
        lengths = [v for v in lengths if isinstance(v, (int, float)) and math.isfinite(v)]
        if lengths:
            out["step_length_m"] = float(np.mean(lengths))
    return out


def biomarker_table(
    runs: list[RunResult],
    joints: tuple[str, ...] = SAGITTAL_JOINTS,
) -> list[dict]:
    """Long-format per-run biomarkers, ready for boxplots and group stats.

    One row per (run, parameter): ``{"patient", "run", "group", "condition",
    "kind", "parameter", "value"}``.
    """
    rows: list[dict] = []
    for run in runs:
        if not run.ok:
            continue
        for parameter, value in _run_scalars(run, joints).items():
            rows.append({
                "patient": run.patient, "run": run.run, "group": run.group,
                "condition": run.condition,
                "kind": "reference" if run.is_reference else "video",
                "parameter": parameter, "value": value,
            })
    return rows


# ── Pairings ─────────────────────────────────────────────────────────


def paired_video_reference(
    runs: list[RunResult],
    parameter: str,
    joints: tuple[str, ...] = SAGITTAL_JOINTS,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Per-patient (video, reference) pairs for *parameter*.

    Mirrors :func:`pooling.overall_agreement`'s pairing: for every patient
    with both kinds, the mean over their video runs vs the mean over their
    reference runs. Returns (video, reference, patients), possibly empty.
    """
    by_patient: dict[str, dict[str, list[float]]] = {}
    for run in runs:
        if not run.ok or run.patient == "?":
            continue
        value = _run_scalars(run, joints).get(parameter)
        if value is None:
            continue
        slot = "ref" if run.is_reference else "video"
        by_patient.setdefault(run.patient, {"video": [], "ref": []})[slot].append(value)

    video, ref, patients = [], [], []
    for patient in sorted(by_patient):
        sides = by_patient[patient]
        if sides["video"] and sides["ref"]:
            video.append(float(np.mean(sides["video"])))
            ref.append(float(np.mean(sides["ref"])))
            patients.append(patient)
    return np.asarray(video), np.asarray(ref), patients


def retest_matrix(
    runs: list[RunResult],
    parameter: str,
    joints: tuple[str, ...] = SAGITTAL_JOINTS,
) -> np.ndarray | None:
    """(n_subjects, k) matrix of repeated video measurements of *parameter*.

    Video runs only; patients with at least two runs carrying the parameter;
    truncated to the common minimum k (a balanced design, which the ICC ANOVA
    decomposition assumes). ``None`` when fewer than two such patients.
    """
    by_patient: dict[str, list[float]] = {}
    for run in runs:
        if not run.ok or run.is_reference or run.patient == "?":
            continue
        value = _run_scalars(run, joints).get(parameter)
        if value is not None:
            by_patient.setdefault(run.patient, []).append(value)

    series = [vals for vals in by_patient.values() if len(vals) >= 2]
    if len(series) < 2:
        return None
    k = min(len(vals) for vals in series)
    return np.asarray([vals[:k] for vals in series], dtype=float)


# ── Batteries ────────────────────────────────────────────────────────


def validity_battery(
    runs: list[RunResult],
    parameters: tuple[str, ...],
    joints: tuple[str, ...] = SAGITTAL_JOINTS,
) -> list[dict]:
    """Per parameter: ICC(2,1) + Bland-Altman of video vs the C3D reference."""
    rows: list[dict] = []
    for parameter in parameters:
        video, ref, patients = paired_video_reference(runs, parameter, joints)
        entry: dict = {"parameter": parameter, "n_patients": len(patients)}
        if len(patients):
            result = icc(np.column_stack([video, ref]), form="ICC2_1")
            entry["icc"] = result
            entry["bland_altman"] = bland_altman(video, ref)
        else:
            entry["icc"] = None
            entry["bland_altman"] = None
        rows.append(entry)
    return rows


def retest_battery(
    runs: list[RunResult],
    parameters: tuple[str, ...],
    joints: tuple[str, ...] = SAGITTAL_JOINTS,
) -> list[dict]:
    """Per parameter: test-retest ICC(3,1) (+ ICC(2,k)) over repeated runs."""
    rows: list[dict] = []
    for parameter in parameters:
        matrix = retest_matrix(runs, parameter, joints)
        entry: dict = {"parameter": parameter}
        if matrix is not None:
            entry["n_patients"], entry["k"] = matrix.shape
            entry["icc"] = icc(matrix, form="ICC3_1")
            entry["icc2k"] = icc(matrix, form="ICC2_k")
            entry["bland_altman"] = (
                bland_altman(matrix[:, 0], matrix[:, 1]) if matrix.shape[1] >= 2 else None
            )
        else:
            entry.update(n_patients=0, k=0, icc=None, icc2k=None, bland_altman=None)
        rows.append(entry)
    return rows


def group_comparison_biomarkers(
    runs: list[RunResult],
    group_a: str,
    group_b: str,
    parameters: tuple[str, ...],
    joints: tuple[str, ...] = SAGITTAL_JOINTS,
    by: str = "group",
) -> list[dict]:
    """Two-group biomarker comparison: n, mean±SD per group, Δ, Hedges g.

    *by* selects the grouping field (``"group"`` or ``"condition"``) -- many
    existing pivots tag a condition but leave the group as "unknown". Welch's
    p-value is added when scipy is importable.
    """
    table = biomarker_table(runs, joints)
    rows: list[dict] = []
    for parameter in parameters:
        va = [r["value"] for r in table if r["parameter"] == parameter and r[by] == group_a]
        vb = [r["value"] for r in table if r["parameter"] == parameter and r[by] == group_b]
        entry: dict = {
            "parameter": parameter,
            "n_a": len(va), "n_b": len(vb),
            "mean_a": float(np.mean(va)) if va else None,
            "sd_a": float(np.std(va, ddof=1)) if len(va) > 1 else None,
            "mean_b": float(np.mean(vb)) if vb else None,
            "sd_b": float(np.std(vb, ddof=1)) if len(vb) > 1 else None,
        }
        if va and vb:
            entry["delta"] = entry["mean_a"] - entry["mean_b"]
            entry["hedges_g"] = _hedges_g(va, vb)
            entry["p_welch"] = _welch_p(va, vb)
        else:
            entry.update(delta=None, hedges_g=None, p_welch=None)
        rows.append(entry)
    return rows


def _hedges_g(a: list[float], b: list[float]) -> float | None:
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return None
    sa, sb = np.std(a, ddof=1), np.std(b, ddof=1)
    pooled = math.sqrt(((na - 1) * sa ** 2 + (nb - 1) * sb ** 2) / (na + nb - 2))
    if pooled == 0:
        return None
    d = (float(np.mean(a)) - float(np.mean(b))) / pooled
    correction = 1.0 - 3.0 / (4.0 * (na + nb) - 9.0)   # small-sample bias
    return float(d * correction)


def _welch_p(a: list[float], b: list[float]) -> float | None:
    if len(a) < 2 or len(b) < 2:
        return None
    try:
        from scipy.stats import ttest_ind
    except Exception:  # pragma: no cover - scipy ships with myogait
        return None
    return float(ttest_ind(a, b, equal_var=False).pvalue)
