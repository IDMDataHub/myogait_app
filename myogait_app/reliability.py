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
- **Two independent groups (Advanced -> Groups -> Two groups)**: the test is
  picked from the data -- Welch's t-test when a Shapiro-Wilk check does not
  reject normality in *both* groups, Mann-Whitney U otherwise (also whenever a
  group is too small to assess, n < 3). Effect size follows the test: Hedges g
  (bias-corrected standardised mean difference) for the t-test, rank-biserial
  correlation for Mann-Whitney. No multiple-comparison correction is applied --
  when many parameters are compared at once the UI warns and reports how many
  reach p < 0.05, leaving the correction choice to the reader (audit action
  plan, chantier B3).

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

#: Accelerometry-family scalars (trunk/pelvis smoothness metrics classically
#: measured with a lumbar IMU, here derived from the pelvis-centre trajectory):
#: read from ``stats["accelerometric"]`` (see :func:`accelerometric_scalars`)
#: plus myogait's own harmonic ratio under ``stats["harmonic_ratio"]``.
ACCELEROMETRIC_BIOMARKERS = (
    "rms_accel_ap",
    "rms_accel_vertical",
    "index_of_harmonicity_ap",
    "lf_hf_ratio_ap",
    "hr_ap",
    "hr_vertical",
)

#: Spectral split for the LF/HF power ratio (Hz): the locomotor band vs the
#: faster content above it. A crude but reproducible smoothness index.
LF_BAND = (0.5, 3.0)
HF_BAND = (3.0, 10.0)


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


# ── Accelerometric scalars from the pelvis trajectory ────────────────


def _pelvis_series(data: dict) -> tuple[np.ndarray, np.ndarray, float] | None:
    """(ap, vertical, fps) pelvis-centre position series from a pivot."""
    frames = data.get("frames") or []
    fps = (data.get("meta") or {}).get("fps")
    if not frames or not isinstance(fps, (int, float)) or not math.isfinite(fps) or fps <= 0:
        return None
    xs, ys = [], []
    for frame in frames:
        lm = frame.get("landmarks") or {}
        lh, rh = lm.get("LEFT_HIP"), lm.get("RIGHT_HIP")
        try:
            x = (float(lh["x"]) + float(rh["x"])) / 2.0
            y = (float(lh["y"]) + float(rh["y"])) / 2.0
        except (TypeError, KeyError, ValueError):
            x = y = float("nan")
        xs.append(x)
        ys.append(y)
    ap = np.asarray(xs, dtype=float)
    vert = np.asarray(ys, dtype=float)
    if np.isfinite(ap).sum() < 64:            # too short for any spectrum
        return None
    return ap, vert, float(fps)


def _accel(series: np.ndarray, fps: float) -> np.ndarray:
    """Double-differentiated, linearly detrended acceleration (finite only)."""
    keep = np.isfinite(series)
    series = np.interp(np.arange(series.size), np.flatnonzero(keep), series[keep]) \
        if keep.any() and not keep.all() else series
    vel = np.gradient(series, 1.0 / fps)
    acc = np.gradient(vel, 1.0 / fps)
    t = np.arange(acc.size)
    slope, intercept = np.polyfit(t, acc, 1)
    return acc - (slope * t + intercept)


def _band_power(freqs: np.ndarray, power: np.ndarray, band: tuple[float, float]) -> float:
    mask = (freqs >= band[0]) & (freqs < band[1])
    return float(power[mask].sum())


def accelerometric_scalars(data: dict) -> dict[str, float]:
    """Trunk-accelerometry-style smoothness scalars from the pelvis centre.

    Classically measured with a lumbar IMU; here the pelvis-centre trajectory
    is double-differentiated instead. Positions are image-normalised, so the
    RMS values are in arbitrary units -- comparable across recordings that
    share the pipeline, not against published IMU numbers (state this wherever
    they are displayed).

    - ``rms_accel_ap`` / ``rms_accel_vertical``: RMS of the detrended
      acceleration.
    - ``index_of_harmonicity_ap``: power at the dominant locomotor frequency
      divided by the summed power of its first six harmonics (Lamoth et al.);
      1.0 = perfectly harmonic (smooth), lower = noisier gait.
    - ``lf_hf_ratio_ap``: spectral power in :data:`LF_BAND` over
      :data:`HF_BAND` -- higher means the movement lives in the locomotor
      band rather than in fast noise.
    """
    series = _pelvis_series(data)
    if series is None:
        return {}
    ap_pos, vert_pos, fps = series
    out: dict[str, float] = {}

    ap = _accel(ap_pos, fps)
    vert = _accel(vert_pos, fps)
    out["rms_accel_ap"] = float(np.sqrt(np.mean(ap ** 2)))
    out["rms_accel_vertical"] = float(np.sqrt(np.mean(vert ** 2)))

    freqs = np.fft.rfftfreq(ap.size, d=1.0 / fps)
    power = np.abs(np.fft.rfft(ap - ap.mean())) ** 2

    # Dominant locomotor frequency inside the LF band.
    lf_mask = (freqs >= LF_BAND[0]) & (freqs < LF_BAND[1])
    if lf_mask.any() and power[lf_mask].max() > 0:
        f0 = float(freqs[lf_mask][int(np.argmax(power[lf_mask]))])
        df = freqs[1] - freqs[0] if freqs.size > 1 else 0.0
        harmonic_power = []
        for h in range(1, 7):
            target = h * f0
            window = (freqs >= target - df) & (freqs <= target + df)
            harmonic_power.append(float(power[window].sum()) if window.any() else 0.0)
        total = sum(harmonic_power)
        if total > 0:
            out["index_of_harmonicity_ap"] = float(harmonic_power[0] / total)

    hf = _band_power(freqs, power, HF_BAND)
    lf = _band_power(freqs, power, LF_BAND)
    if hf > 0:
        out["lf_hf_ratio_ap"] = float(lf / hf)
    return out


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
    # Accelerometry family: the pelvis-derived scalars analyse_data stashes,
    # plus myogait's own harmonic ratio.
    accel = (run.stats or {}).get("accelerometric") or {}
    for key, value in accel.items():
        if isinstance(value, (int, float)) and math.isfinite(value):
            out[key] = float(value)
    hr = (run.stats or {}).get("harmonic_ratio") or {}
    for key in ("hr_ap", "hr_vertical"):
        value = hr.get(key)
        if isinstance(value, (int, float)) and math.isfinite(value):
            out[key] = float(value)
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
            diff = group_difference(va, vb)
            if diff:
                entry.update(
                    test=diff["test"], p=diff["p"],
                    effect=diff["effect"], effect_name=diff["effect_name"],
                    normal=diff["normal"],
                )
            else:
                entry.update(test=None, p=None, effect=None, effect_name=None, normal=None)
        else:
            entry.update(
                delta=None, hedges_g=None, p_welch=None,
                test=None, p=None, effect=None, effect_name=None, normal=None,
            )
        rows.append(entry)
    return rows


def compare_two_groups(
    runs_a: list[RunResult],
    runs_b: list[RunResult],
    joints: tuple[str, ...] = SAGITTAL_JOINTS,
) -> list[dict]:
    """Every parameter present in *both* run lists, with descriptives + test.

    Unlike :func:`group_comparison_biomarkers` (which splits one run list on a
    ``group``/``condition`` field), the two groups here are two independently
    imported sets -- Advanced's Two groups screen, where group membership is
    the import zone, not a tag inside the pivot. One row per shared parameter:
    n / mean / SD / min / max per group, the difference, and the adaptive test
    (:func:`group_difference`).
    """
    table_a = biomarker_table(runs_a, joints)
    table_b = biomarker_table(runs_b, joints)
    params_a = {row["parameter"] for row in table_a}
    params_b = {row["parameter"] for row in table_b}
    shared = [p for p in _stable_params(table_a + table_b) if p in params_a and p in params_b]

    rows: list[dict] = []
    for parameter in shared:
        va = [r["value"] for r in table_a if r["parameter"] == parameter]
        vb = [r["value"] for r in table_b if r["parameter"] == parameter]
        entry: dict = {
            "parameter": parameter,
            "n_a": len(va), "n_b": len(vb),
            "mean_a": float(np.mean(va)), "mean_b": float(np.mean(vb)),
            "sd_a": float(np.std(va, ddof=1)) if len(va) > 1 else None,
            "sd_b": float(np.std(vb, ddof=1)) if len(vb) > 1 else None,
            "min_a": float(np.min(va)), "max_a": float(np.max(va)),
            "min_b": float(np.min(vb)), "max_b": float(np.max(vb)),
            "delta": float(np.mean(va)) - float(np.mean(vb)),
        }
        diff = group_difference(va, vb)
        if diff:
            entry.update(
                test=diff["test"], p=diff["p"],
                effect=diff["effect"], effect_name=diff["effect_name"],
                normal=diff["normal"],
            )
        else:
            entry.update(test=None, p=None, effect=None, effect_name=None, normal=None)
        rows.append(entry)
    return rows


def _stable_params(table: list[dict]) -> list[str]:
    seen: list[str] = []
    for row in table:
        if row["parameter"] not in seen:
            seen.append(row["parameter"])
    return seen


def group_difference(a: list[float], b: list[float], alpha: float = 0.05) -> dict | None:
    """One adaptive two-group difference test, chosen from the data.

    Welch's t-test when a Shapiro-Wilk check does not reject normality in both
    groups (and both have n >= 3); Mann-Whitney U otherwise. The effect size
    follows: Hedges g for the parametric branch, rank-biserial correlation for
    the non-parametric one. Returns ``None`` when either group has fewer than
    two finite values -- no test is meaningful there.

    ``normal`` reports which branch ran (True = parametric), so the caller can
    show the reader why a given parameter used the test it used.
    """
    a = [float(v) for v in a if isinstance(v, (int, float)) and math.isfinite(v)]
    b = [float(v) for v in b if isinstance(v, (int, float)) and math.isfinite(v)]
    if len(a) < 2 or len(b) < 2:
        return None

    parametric = _shapiro_normal(a, alpha) and _shapiro_normal(b, alpha)
    if parametric:
        return {
            "test": "Welch t", "p": _welch_p(a, b),
            "effect": _hedges_g(a, b), "effect_name": "Hedges g", "normal": True,
        }
    return {
        "test": "Mann-Whitney U", "p": _mann_whitney_p(a, b),
        "effect": _rank_biserial(a, b), "effect_name": "rank-biserial r", "normal": False,
    }


def significant_count(rows: list[dict], alpha: float = 0.05) -> tuple[int, int]:
    """(# parameters with p < alpha, # parameters actually tested) over *rows*.

    Drives the Two-groups multiple-comparison warning: the plan's choice is to
    report the uncorrected tally and let the reader decide on a correction,
    not to silently apply one.
    """
    tested = [r for r in rows if isinstance(r.get("p"), (int, float)) and math.isfinite(r["p"])]
    hits = sum(1 for r in tested if r["p"] < alpha)
    return hits, len(tested)


def _shapiro_normal(sample: list[float], alpha: float = 0.05) -> bool:
    """True when Shapiro-Wilk does not reject normality. n < 3 -> False (cannot
    assess -> the non-parametric branch is the safe default)."""
    if len(sample) < 3 or len(set(sample)) < 2:
        return False
    try:
        from scipy.stats import shapiro

        return float(shapiro(sample).pvalue) > alpha
    except Exception:  # pragma: no cover - scipy ships with myogait
        return False


def _mann_whitney_p(a: list[float], b: list[float]) -> float | None:
    try:
        from scipy.stats import mannwhitneyu

        return float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except Exception:  # pragma: no cover
        return None


def _rank_biserial(a: list[float], b: list[float]) -> float | None:
    """Rank-biserial correlation from the Mann-Whitney U of group *a*:
    ``r = 1 - 2U / (n_a * n_b)`` -- +1 when every a exceeds every b, -1 the
    reverse, 0 at full overlap."""
    try:
        from scipy.stats import mannwhitneyu

        u = float(mannwhitneyu(a, b, alternative="two-sided").statistic)
        return 1.0 - (2.0 * u) / (len(a) * len(b))
    except Exception:  # pragma: no cover
        return None


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
