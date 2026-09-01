"""A virtual accelerometer, and the biomarkers computed from it, from a
pivot's own landmark trajectories -- no IMU worn on the subject.

Every video pivot already carries a 2-D pixel trajectory for the hip and
shoulder landmarks; a torso-normalised second derivative of an anatomical
site's position is, dimensionally, the same signal a waist-worn inertial
sensor would report (Moe-Nilssen & Helbostad 2004 pioneered exactly this
substitution for trunk accelerometry). This module turns that signal into
the same family of gait biomarkers the accelerometry literature uses to
describe smoothness, regularity and variability of walking, so a markerless
recording can be read the same way a worn sensor's data would be.

Streamlit-free and unit-tested, following the pattern of ``calibration.py``/
``step_length.py``/``quality.py``: pure computation driven by a pivot
``data`` dict, returning ``None`` (not raising) when the landmarks needed
are missing or too sparse, so a caller falls back to not offering this
capability rather than crashing.

**Provenance, deliberately narrow.** This module started as a port of a
research script (``gait_biomarkers.py``, "Pipeline Equimetrix enrichi",
2024) built for an M2 project analysing this exact virtual-accelerometer
idea. Two things from that script were intentionally left out of the port:
the ``_locolike``/"RDM" regularity and symmetry indices, which that script's
own comments mark as a proprietary method (Fisher-Z-transformed variants of
the standard Moe-Nilssen coefficients) -- publishing them here was never
confirmed, so they are simply absent, not disabled; and the private 8-subject
video-vs-IMU validation cohort that script's own correlation figures were
built from -- no data or numeric result derived from it ships in this
module or this repository. Every formula that *is* here cites a published
source below and is computed fresh from whatever recording is loaded, never
from a bundled dataset.

References
----------
- Moe-Nilssen & Helbostad (2004) -- trunk-accelerometry autocorrelation
  (the C1/C2 regularity and symmetry coefficients).
- Gage et al. (2004), Bellanca et al. (2013) -- Harmonic Ratio, a measure
  of movement smoothness.
- Costa et al. (2003), Richman & Moorman (2000) -- Sample/Approximate
  Entropy, a measure of signal complexity.
- Hollman et al. (2011), Winter (2009) -- normal-adult temporal gait
  parameters used as the published reference ranges below.
- Bruijn et al. (2013) -- entropy reference ranges for gait signals.

**A known sibling, not reconciled here.** ``reliability.
accelerometric_scalars`` already computes a smaller family of the same
idea (RMS, an index of harmonicity, an LF/HF power ratio) from the pelvis
centre, by a simpler method (plain double-``np.gradient`` plus linear
detrend, no torso-length normalisation, no resampling, pelvis only) --
built independently for the cohort ICC/group-comparison tables
(`CHANGELOG.md`'s 0.8.0 entry). This module was written without touching
that one: its numbers already feed shipped, tested cohort statistics, and
swapping its computation for this module's (a real behaviour change, not
a refactor) needs its own dedicated validation pass -- the same caution
this project's own ISB-reconstruction reconciliation needed, not
something to fold into an unrelated feature session.

**Decision (Romain Feigean, 2026-09-01): kept in `main` as-is.** An
earlier draft of this note asked Frédéric Fer to arbitrate whether to
unify the two, with a stated leaning toward keeping his simpler
`reliability.accelerometric_scalars` instead; that request was withdrawn
before it reached him -- this module stays, unreconciled, on its own
authority. Unifying the two remains open and undecided, not blocking.
Until it happens, the two keep computing slightly different numbers for a
similar-sounding quantity; know which module a given number came from.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict

import numpy as np
from scipy.fft import fft, fftfreq
from scipy.signal import butter, filtfilt, find_peaks, resample_poly, savgol_filter, welch
from scipy.stats import kurtosis, skew

#: Anatomical sites this module can turn into a virtual accelerometer, each
#: needing a different subset of landmarks a lateral-view pivot may or may
#: not carry (a frontal-view or partially occluded recording can still
#: resolve "sacrum" even when "head" is missing, and vice versa).
SITES: tuple[str, ...] = ("sacrum", "lumbar", "sternum", "head")
SITE_LABEL: Dict[str, str] = {
    "sacrum": "Sacrum (pelvis)",
    "lumbar": "Lumbar (L3, blended)",
    "sternum": "Sternum (chest)",
    "head": "Head",
}
SITE_LANDMARKS: Dict[str, tuple[str, ...]] = {
    "sacrum": ("LEFT_HIP", "RIGHT_HIP"),
    "lumbar": ("LEFT_HIP", "RIGHT_HIP", "LEFT_SHOULDER", "RIGHT_SHOULDER"),
    "sternum": ("LEFT_SHOULDER", "RIGHT_SHOULDER"),
    "head": ("NOSE",),
}
#: Every site's normalisation needs the torso length (shoulder-to-hip).
_TORSO_LANDMARKS = ("LEFT_SHOULDER", "RIGHT_SHOULDER", "LEFT_HIP", "RIGHT_HIP")

#: Minimum recording length for a stable low-pass/autocorrelation estimate.
_MIN_FRAMES = 30
#: Minimum fraction of frames where the required landmarks were both
#: present, below which the site's own trajectory is too sparse to trust.
_MIN_COVERAGE = 0.5


def site_available(data: dict, site: str) -> bool:
    """Whether *site* has enough landmark coverage to be worth trying.

    Cheap pre-check for the UI (grey out a site picker entry) -- does not
    run the actual signal-processing pipeline.
    """
    frames = data.get("frames") or []
    if len(frames) < _MIN_FRAMES or site not in SITE_LANDMARKS:
        return False
    needed = set(SITE_LANDMARKS[site]) | set(_TORSO_LANDMARKS)
    hits = 0
    for f in frames:
        lms = f.get("landmarks") or {}
        if all(name in lms for name in needed):
            hits += 1
    return (hits / len(frames)) >= _MIN_COVERAGE


# ── Virtual accelerometer ────────────────────────────────────────────

@dataclass
class VirtualSignal:
    """A torso-normalised acceleration signal, resampled to a fixed rate."""

    ap: np.ndarray  # antero-posterior axis, resampled to `fs`
    v: np.ndarray   # vertical axis, resampled to `fs`
    fs: float
    site: str

    @property
    def t(self) -> np.ndarray:
        return np.arange(len(self.v)) / self.fs

    @property
    def duration_s(self) -> float:
        return len(self.v) / self.fs if self.fs else 0.0


def _interp_nan(x: np.ndarray) -> np.ndarray:
    n = len(x)
    idx = np.arange(n)
    ok = np.isfinite(x)
    if ok.sum() < 2:
        return np.zeros(n)
    return np.interp(idx, idx[ok], x[ok])


def _lowpass(x: np.ndarray, fps: float, cutoff_hz: float) -> np.ndarray:
    nyq = 0.5 * fps
    wc = min(cutoff_hz, 0.95 * nyq) / nyq
    b, a = butter(2, wc, btype="low")
    return filtfilt(b, a, x)


def _sg_accel(x: np.ndarray, fps: float, win_s: float = 0.20) -> np.ndarray:
    win = int(round(win_s * fps))
    win += win % 2 == 0
    win = max(win, 5)
    return savgol_filter(x, win, 3, deriv=2, delta=1.0 / fps, mode="interp")


def _mean_position(frames: list, names: tuple[str, ...], width: float, height: float):
    """Visibility-weighted mean pixel position of *names* per frame."""
    n = len(frames)
    acc = np.zeros((n, 2))
    weight = np.zeros(n)
    for name in names:
        xy = np.full((n, 2), np.nan)
        vis = np.zeros(n)
        for i, f in enumerate(frames):
            lm = (f.get("landmarks") or {}).get(name)
            if lm is not None:
                xy[i] = (lm["x"] * width, lm["y"] * height)
                vis[i] = lm.get("visibility", 1.0)
        wi = np.where(np.isfinite(xy[:, 0]), vis, 0.0)
        acc += np.nan_to_num(xy) * wi[:, None]
        weight += wi
    pos = np.divide(acc, weight[:, None], out=np.full_like(acc, np.nan), where=weight[:, None] > 0)
    return pos, weight > 0


def compute_virtual_signal(data: dict, site: str = "sacrum", fs_out: float = 100.0) -> VirtualSignal | None:
    """Torso-normalised acceleration at *site*, resampled to *fs_out* Hz.

    Method: mean pixel position of the site's landmark(s) each frame,
    divided by the (low-pass-filtered) shoulder-to-hip pixel distance --
    the same "torso-length" normalisation a worn sensor's calibration
    would achieve physically -- then a Savitzky-Golay second derivative
    (fewer high-frequency artefacts than a finite-difference double diff)
    and a rational resample to a fixed output rate so recordings at
    different frame rates produce comparable biomarkers.

    Only the antero-posterior (AP, horizontal in a lateral view) and
    vertical (V) axes are available: a single 2-D camera has no
    medio-lateral depth information, unlike a worn 3-axis IMU. Every
    biomarker below is computed on these two axes only.

    Returns ``None`` when *site* is unknown, the recording is too short,
    or landmark coverage is too sparse to trust -- callers should fall
    back to "not available" rather than show a signal built mostly from
    interpolation.
    """
    if site not in SITE_LANDMARKS:
        return None
    frames = data.get("frames") or []
    if len(frames) < _MIN_FRAMES:
        return None
    meta = data.get("meta") or {}
    fps = float(meta.get("fps") or 30.0)
    width = float(meta.get("width") or 1.0)
    height = float(meta.get("height") or 1.0)
    if fps <= 0:
        return None

    shoulders, good_sh = _mean_position(frames, ("LEFT_SHOULDER", "RIGHT_SHOULDER"), width, height)
    hips, good_hip = _mean_position(frames, ("LEFT_HIP", "RIGHT_HIP"), width, height)
    torso = np.linalg.norm(shoulders - hips, axis=1)
    good_torso = np.isfinite(torso) & good_sh & good_hip
    if good_torso.sum() / len(frames) < _MIN_COVERAGE:
        return None
    t_med = float(np.median(torso[good_torso]))
    if t_med <= 0:
        return None
    torso_s = _lowpass(_interp_nan(np.where(good_torso, torso, np.nan)), fps, 0.6)
    torso_s = np.clip(torso_s, 0.3 * t_med, 3 * t_med)

    if site == "sacrum":
        site_pos, site_good = hips, good_hip
    elif site == "sternum":
        site_pos, site_good = shoulders, good_sh
    elif site == "lumbar":
        site_pos, site_good = 0.67 * hips + 0.33 * shoulders, good_hip & good_sh
    else:  # head
        site_pos, site_good = _mean_position(frames, SITE_LANDMARKS[site], width, height)
    if site_good.sum() / len(frames) < _MIN_COVERAGE:
        return None

    pos_n = site_pos / torso_s[:, None]
    x_f = _interp_nan(np.where(site_good, pos_n[:, 0], np.nan))
    y_f = _interp_nan(np.where(site_good, pos_n[:, 1], np.nan))

    a_h = _sg_accel(x_f, fps)
    a_v = -_sg_accel(y_f, fps)  # image y grows downward; "up" is positive

    ratio = Fraction(fs_out / fps).limit_denominator(1000)
    up, down = ratio.numerator, ratio.denominator
    ap = resample_poly(a_h, up, down)
    v = resample_poly(a_v, up, down)
    if len(v) < _MIN_FRAMES:
        return None
    return VirtualSignal(ap=ap, v=v, fs=fs_out, site=site)


# ── Biomarker structures ─────────────────────────────────────────────

@dataclass
class TemporalParameters:
    cadence: float = 0.0
    stride_frequency: float = 0.0
    step_time_mean: float = 0.0
    step_time_std: float = 0.0
    step_time_cv: float = 0.0
    stride_time_mean: float = 0.0
    stride_time_std: float = 0.0
    stride_time_cv: float = 0.0
    total_steps: int = 0
    total_strides: int = 0
    walking_duration: float = 0.0


@dataclass
class RegularitySymmetry:
    """Moe-Nilssen & Helbostad (2004) autocorrelation coefficients."""

    C1_AP: float = 0.0
    C2_AP: float = 0.0
    C1_V: float = 0.0
    C2_V: float = 0.0
    regularity: float = 0.0  # = C2_V
    symmetry: float = 0.0    # = C1_V / C2_V * 100
    stability: float = 0.0   # = C1_V + C2_V (Barrey index)


@dataclass
class HarmonicRatio:
    """Gage et al. (2004) / Bellanca et al. (2013) smoothness measures."""

    HR_AP: float = 0.0
    HR_V: float = 0.0
    IH_AP: float = 0.0  # Index of Harmonicity: fundamental / total power
    IH_V: float = 0.0


@dataclass
class SpectralParameters:
    freq_dominant_AP: float = 0.0
    freq_dominant_V: float = 0.0
    power_total_AP: float = 0.0
    power_total_V: float = 0.0
    ratio_HF_BF_AP: float = 0.0
    ratio_HF_BF_V: float = 0.0
    FMD_AP: float = 0.0
    FMD_V: float = 0.0
    bandwidth_AP: float = 0.0
    bandwidth_V: float = 0.0


@dataclass
class EntropyMeasures:
    """Richman & Moorman (2000) / Costa et al. (2003)."""

    sample_entropy_AP: float = 0.0
    sample_entropy_V: float = 0.0
    approx_entropy_AP: float = 0.0
    approx_entropy_V: float = 0.0


@dataclass
class VariabilityIndices:
    rms_AP: float = 0.0
    rms_V: float = 0.0
    rms_total: float = 0.0
    cv_rms_V: float = 0.0


@dataclass
class StatisticalMoments:
    skewness_AP: float = 0.0
    skewness_V: float = 0.0
    kurtosis_AP: float = 0.0
    kurtosis_V: float = 0.0
    range_AP: float = 0.0
    range_V: float = 0.0


@dataclass
class GaitBiomarkers:
    temporal: TemporalParameters = field(default_factory=TemporalParameters)
    regularity: RegularitySymmetry = field(default_factory=RegularitySymmetry)
    harmonic: HarmonicRatio = field(default_factory=HarmonicRatio)
    spectral: SpectralParameters = field(default_factory=SpectralParameters)
    entropy: EntropyMeasures = field(default_factory=EntropyMeasures)
    variability: VariabilityIndices = field(default_factory=VariabilityIndices)
    statistics: StatisticalMoments = field(default_factory=StatisticalMoments)
    site: str = "sacrum"
    sampling_rate: float = 100.0
    segment_length: int = 0

    def to_dict(self) -> Dict[str, float]:
        """Flatten to ``{"temporal_cadence": ..., "reg_C1_AP": ...}`` --

        the same flat, prefixed shape a table or a CSV export wants.
        """
        out: Dict[str, float] = {}
        for prefix, group in (
            ("temporal", self.temporal), ("reg", self.regularity),
            ("harmonic", self.harmonic), ("spectral", self.spectral),
            ("entropy", self.entropy), ("var", self.variability),
            ("stat", self.statistics),
        ):
            for k, v in group.__dict__.items():
                out[f"{prefix}_{k}"] = v
        out["site"] = self.site
        out["sampling_rate"] = self.sampling_rate
        out["segment_length"] = self.segment_length
        return out


# ── Formulas ──────────────────────────────────────────────────────────

def _unbiased_autocorrelation(x: np.ndarray) -> np.ndarray:
    n = len(x)
    xc = x - np.mean(x)
    acf = np.correlate(xc, xc, mode="full")[n - 1:]
    for k in range(n):
        if n - k > 0:
            acf[k] /= n - k
    if acf[0] > 0:
        acf = acf / acf[0]
    return acf


def _autocorr_peaks(acf: np.ndarray, fs: float) -> tuple[float, float]:
    """C1 (half-stride/step) and C2 (full stride) autocorrelation peaks."""
    min_c1, max_c1 = int(0.35 * fs), int(0.75 * fs)
    min_c2, max_c2 = int(0.70 * fs), int(1.50 * fs)
    c1 = float(acf[min_c1 + np.argmax(acf[min_c1:max_c1])]) if max_c1 <= len(acf) else 0.0
    c2 = float(acf[min_c2 + np.argmax(acf[min_c2:max_c2])]) if max_c2 <= len(acf) else 0.0
    return c1, c2


def _harmonic_ratio(sig: np.ndarray, fs: float, stride_freq: float, n_harmonics: int = 20) -> tuple[float, float]:
    if stride_freq <= 0 or len(sig) < fs:
        return 0.0, 0.0
    n = len(sig)
    centered = sig - np.mean(sig)
    amp = np.abs(fft(centered))[: n // 2]
    freqs = fftfreq(n, 1 / fs)[: n // 2]
    even_sum = odd_sum = 0.0
    for h in range(1, n_harmonics + 1):
        target = h * stride_freq
        if target > fs / 2:
            break
        idx = int(np.argmin(np.abs(freqs - target)))
        a = amp[idx]
        if h % 2 == 0:
            even_sum += a
        else:
            odd_sum += a
    hr = even_sum / odd_sum if odd_sum > 0 else 0.0
    fundamental_idx = int(np.argmin(np.abs(freqs - stride_freq)))
    fundamental_power = amp[fundamental_idx] ** 2
    total_power = float(np.sum(amp ** 2))
    ih = fundamental_power / total_power if total_power > 0 else 0.0
    return float(hr), float(ih)


def _spectral_parameters(sig: np.ndarray, fs: float) -> dict:
    nperseg = min(256, len(sig) // 4)
    if nperseg < 8:
        return {"freq_dominant": 0.0, "power_total": 0.0, "ratio_hf_bf": 0.0, "fmd": 0.0, "bandwidth": 0.0}
    freqs, psd = welch(sig, fs=fs, nperseg=nperseg)
    freq_dominant = float(freqs[np.argmax(psd)])
    power_total = float(np.trapezoid(psd, freqs))
    bf_mask, hf_mask = freqs < 3.0, freqs >= 3.0
    power_bf = float(np.trapezoid(psd[bf_mask], freqs[bf_mask])) if np.any(bf_mask) else 0.0
    power_hf = float(np.trapezoid(psd[hf_mask], freqs[hf_mask])) if np.any(hf_mask) else 0.0
    ratio_hf_bf = power_hf / power_bf if power_bf > 0 else 0.0
    cumsum = np.cumsum(psd)
    fmd = float(freqs[min(int(np.searchsorted(cumsum, cumsum[-1] / 2)), len(freqs) - 1)]) if cumsum[-1] > 0 else 0.0
    peak = np.max(psd)
    above = psd >= peak / 2
    bandwidth = float(freqs[np.where(above)[0][-1]] - freqs[np.where(above)[0][0]]) if np.any(above) else 0.0
    return {"freq_dominant": freq_dominant, "power_total": power_total, "ratio_hf_bf": ratio_hf_bf,
            "fmd": fmd, "bandwidth": bandwidth}


def _sample_entropy(sig: np.ndarray, m: int = 2, max_samples: int = 200) -> float:
    if len(sig) > max_samples:
        step = len(sig) // max_samples
        sig = sig[::step][:max_samples]
    n = len(sig)
    if n < m + 2:
        return 0.0
    std = np.std(sig)
    if std == 0:
        return 0.0
    norm = (sig - np.mean(sig)) / std
    r = 0.2

    def count(length: int) -> int:
        total = 0
        templates = n - length
        for i in range(templates):
            ti = norm[i:i + length]
            for j in range(i + 1, templates):
                if np.max(np.abs(ti - norm[j:j + length])) < r:
                    total += 1
        return total

    a, b = count(m + 1), count(m)
    return float(-np.log(a / b)) if a and b else 0.0


def _approx_entropy(sig: np.ndarray, m: int = 2, max_samples: int = 200) -> float:
    if len(sig) > max_samples:
        step = len(sig) // max_samples
        sig = sig[::step][:max_samples]
    n = len(sig)
    if n < m + 2:
        return 0.0
    r = 0.2 * np.std(sig)
    if r == 0:
        return 0.0

    def phi(width: int) -> float:
        templates = n - width + 1
        counts = np.zeros(templates)
        for i in range(templates):
            ti = sig[i:i + width]
            hits = sum(1 for j in range(templates) if np.max(np.abs(ti - sig[j:j + width])) <= r)
            counts[i] = hits / templates
        return float(np.mean(np.log(counts + 1e-10)))

    return phi(m) - phi(m + 1)


def _detect_steps(signal_v: np.ndarray, fs: float) -> np.ndarray:
    b, a = butter(4, [0.5, 3], btype="band", fs=fs)
    filtered = filtfilt(b, a, signal_v)
    peaks, _ = find_peaks(filtered, distance=int(0.3 * fs), height=0)
    return peaks


def _temporal_parameters(signal_v: np.ndarray, fs: float) -> TemporalParameters:
    params = TemporalParameters(walking_duration=len(signal_v) / fs)
    peaks = _detect_steps(signal_v, fs)
    params.total_steps = len(peaks)
    if len(peaks) < 3:
        return params
    step_intervals = np.diff(peaks) / fs
    step_intervals = step_intervals[(step_intervals > 0.3) & (step_intervals < 1.5)]
    if len(step_intervals) < 2:
        return params
    params.step_time_mean = float(np.mean(step_intervals))
    params.step_time_std = float(np.std(step_intervals))
    params.step_time_cv = (params.step_time_std / params.step_time_mean) * 100 if params.step_time_mean else 0.0
    n_pairs = min(len(step_intervals[::2]), len(step_intervals[1::2]))
    if n_pairs > 0:
        stride_intervals = step_intervals[:n_pairs * 2:2] + step_intervals[1:n_pairs * 2:2]
        params.total_strides = n_pairs
    else:
        stride_intervals = np.array([])
    if len(stride_intervals):
        params.stride_time_mean = float(np.mean(stride_intervals))
        params.stride_time_std = float(np.std(stride_intervals))
        params.stride_time_cv = (
            (params.stride_time_std / params.stride_time_mean) * 100 if params.stride_time_mean else 0.0
        )
    params.cadence = 60 / params.step_time_mean if params.step_time_mean else 0.0
    params.stride_frequency = 1 / params.stride_time_mean if params.stride_time_mean else 0.0
    return params


def compute_all_biomarkers(ap: np.ndarray, v: np.ndarray, fs: float, site: str = "sacrum") -> GaitBiomarkers:
    """All biomarkers from a 2-axis (AP, V) virtual-accelerometer signal.

    Mirrors ``VirtualSignal.ap``/``.v`` -- pass those two arrays and its
    ``fs`` directly. No medio-lateral (ML) axis: see this module's
    docstring for why a single camera cannot supply one.
    """
    bio = GaitBiomarkers(site=site, sampling_rate=fs, segment_length=len(v))
    bio.temporal = _temporal_parameters(v, fs)
    stride_freq = bio.temporal.stride_frequency

    for axis, sig, name in (("AP", ap, "AP"), ("V", v, "V")):
        acf = _unbiased_autocorrelation(sig)
        c1, c2 = _autocorr_peaks(acf, fs)
        setattr(bio.regularity, f"C1_{name}", c1)
        setattr(bio.regularity, f"C2_{name}", c2)
    bio.regularity.regularity = bio.regularity.C2_V
    if bio.regularity.C2_V > 0:
        bio.regularity.symmetry = (bio.regularity.C1_V / bio.regularity.C2_V) * 100
    bio.regularity.stability = bio.regularity.C1_V + bio.regularity.C2_V

    if stride_freq > 0:
        bio.harmonic.HR_AP, bio.harmonic.IH_AP = _harmonic_ratio(ap, fs, stride_freq)
        bio.harmonic.HR_V, bio.harmonic.IH_V = _harmonic_ratio(v, fs, stride_freq)

    for axis, sig in (("AP", ap), ("V", v)):
        spec = _spectral_parameters(sig, fs)
        setattr(bio.spectral, f"freq_dominant_{axis}", spec["freq_dominant"])
        setattr(bio.spectral, f"power_total_{axis}", spec["power_total"])
        setattr(bio.spectral, f"ratio_HF_BF_{axis}", spec["ratio_hf_bf"])
        setattr(bio.spectral, f"FMD_{axis}", spec["fmd"])
        setattr(bio.spectral, f"bandwidth_{axis}", spec["bandwidth"])

    subsample = max(1, len(ap) // 1000)
    bio.entropy.sample_entropy_AP = _sample_entropy(ap[::subsample])
    bio.entropy.sample_entropy_V = _sample_entropy(v[::subsample])
    bio.entropy.approx_entropy_AP = _approx_entropy(ap[::subsample])
    bio.entropy.approx_entropy_V = _approx_entropy(v[::subsample])

    bio.variability.rms_AP = float(np.sqrt(np.mean(ap ** 2)))
    bio.variability.rms_V = float(np.sqrt(np.mean(v ** 2)))
    bio.variability.rms_total = float(math.hypot(bio.variability.rms_AP, bio.variability.rms_V))
    window = int(5 * fs)
    if len(v) > window * 2:
        windows = [
            float(np.sqrt(np.mean(v[i:i + window] ** 2)))
            for i in range(0, len(v) - window, max(window // 2, 1))
        ]
        if len(windows) > 1 and np.mean(windows):
            bio.variability.cv_rms_V = (np.std(windows) / np.mean(windows)) * 100

    bio.statistics.skewness_AP = float(skew(ap))
    bio.statistics.skewness_V = float(skew(v))
    bio.statistics.kurtosis_AP = float(kurtosis(ap))
    bio.statistics.kurtosis_V = float(kurtosis(v))
    bio.statistics.range_AP = float(np.max(ap) - np.min(ap))
    bio.statistics.range_V = float(np.max(v) - np.min(v))
    return bio


def analyze_recording(data: dict, site: str = "sacrum", fs_out: float = 100.0) -> GaitBiomarkers | None:
    """Convenience entry point: virtual signal + biomarkers, or ``None``."""
    sig = compute_virtual_signal(data, site=site, fs_out=fs_out)
    if sig is None:
        return None
    return compute_all_biomarkers(sig.ap, sig.v, sig.fs, site=site)


# ── Clinical reference ranges (published literature only) ──────────────
#
# Every range below cites a source in this module's own docstring; none is
# derived from the private validation cohort mentioned there.

BIOMARKER_CATEGORIES: Dict[str, list[tuple[str, str, str]]] = {
    "Regularity & symmetry": [
        ("reg_C1_V", "C1 vertical", "Step coefficient (L/R symmetry)"),
        ("reg_C2_V", "C2 vertical", "Stride coefficient (regularity)"),
        ("reg_symmetry", "Symmetry (%)", "C1/C2 ratio * 100"),
        ("reg_stability", "Stability", "Barrey index (C1+C2)"),
    ],
    "Temporal parameters": [
        ("temporal_cadence", "Cadence (steps/min)", "Steps per minute"),
        ("temporal_step_time_mean", "Step time (s)", "Mean step duration"),
        ("temporal_total_steps", "Total steps", "Detected steps"),
        ("temporal_step_time_cv", "Step time CV (%)", "Step-time variability"),
        ("temporal_stride_time_cv", "Stride time CV (%)", "Stride-time variability"),
    ],
    "Smoothness (Harmonic Ratio)": [
        ("harmonic_HR_V", "HR vertical", "Vertical movement smoothness"),
        ("harmonic_HR_AP", "HR antero-posterior", "Fore-aft smoothness"),
    ],
    "Activity (RMS)": [
        ("var_rms_V", "RMS vertical (a.u.)", "Vertical intensity"),
        ("var_rms_AP", "RMS AP (a.u.)", "Fore-aft intensity"),
        ("var_rms_total", "RMS total (a.u.)", "Overall intensity"),
    ],
    "Spectral analysis": [
        ("spectral_freq_dominant_V", "Dominant freq. V (Hz)", "Main vertical frequency"),
        ("spectral_FMD_V", "FMD V (Hz)", "Median vertical frequency"),
        ("spectral_ratio_HF_BF_V", "HF/BF ratio V", "Motor control (HF>3Hz / BF<3Hz)"),
    ],
    "Complexity (entropy)": [
        ("entropy_sample_entropy_V", "SampEn vertical", "Vertical signal complexity"),
        ("entropy_sample_entropy_AP", "SampEn AP", "Fore-aft complexity"),
    ],
    "Statistics": [
        ("stat_skewness_V", "Skewness V", "Distribution asymmetry"),
        ("stat_kurtosis_V", "Kurtosis V", "Distribution peakedness"),
        ("stat_range_V", "Range V (a.u.)", "Signal amplitude"),
    ],
}

REFERENCE_RANGES: Dict[str, dict] = {
    "reg_C1_V": {"min": 0.70, "max": 0.95, "unit": "", "low": "L/R asymmetry, possible limp",
                 "high": "Excellent step symmetry"},
    "reg_C2_V": {"min": 0.80, "max": 0.98, "unit": "", "low": "Irregular gait, fatigue or pathology",
                 "high": "Very regular, stable gait"},
    "reg_symmetry": {"min": 90, "max": 110, "unit": "%", "low": "Asymmetry, favours one side",
                      "high": "Asymmetry, favours the other side"},
    "reg_stability": {"min": 1.5, "max": 1.9, "unit": "", "low": "Reduced stability, fall risk",
                       "high": "Very good overall stability"},
    "temporal_cadence": {"min": 100, "max": 130, "unit": "steps/min", "low": "Slow, cautious gait or fatigue",
                          "high": "Fast gait, possible compensation"},
    "temporal_step_time_mean": {"min": 0.46, "max": 0.60, "unit": "s", "low": "Short, fast steps",
                                 "high": "Long or hesitant steps"},
    "temporal_step_time_cv": {"min": 1.0, "max": 4.0, "unit": "%", "low": "Very mechanical/rigid gait",
                               "high": "Temporal instability, elevated fall risk"},
    "temporal_stride_time_cv": {"min": 1.0, "max": 3.5, "unit": "%", "low": "Very regular pattern",
                                 "high": "Excessive variability, impaired control"},
    "harmonic_HR_V": {"min": 1.8, "max": 3.5, "unit": "", "low": "Jerky movement, impaired motor control",
                       "high": "Very smooth, controlled movement"},
    "harmonic_HR_AP": {"min": 2.0, "max": 4.0, "unit": "", "low": "Irregular propulsion",
                        "high": "Excellent propulsion"},
    "var_rms_V": {"min": 0.10, "max": 0.35, "unit": "a.u.", "low": "Low amplitude, shuffling gait",
                  "high": "High amplitude, elevated impacts"},
    "var_rms_AP": {"min": 0.08, "max": 0.25, "unit": "a.u.", "low": "Weak propulsion",
                   "high": "Strong propulsion or instability"},
    "spectral_freq_dominant_V": {"min": 1.6, "max": 2.2, "unit": "Hz", "low": "Low cadence",
                                  "high": "High cadence"},
    "spectral_ratio_HF_BF_V": {"min": 0.05, "max": 0.30, "unit": "", "low": "Low-frequency-dominated signal",
                                "high": "High HF content, noise or tremor"},
    "entropy_sample_entropy_V": {"min": 0.1, "max": 0.5, "unit": "", "low": "Very predictable/rigid signal",
                                  "high": "Complex/chaotic signal, reduced adaptability"},
}


def get_reference_range(code: str) -> str:
    ref = REFERENCE_RANGES.get(code)
    if not ref:
        return "-"
    return f"{ref['min']:.2f} - {ref['max']:.2f} {ref['unit']}".strip()


def get_reference_status(code: str, value: float) -> str:
    ref = REFERENCE_RANGES.get(code)
    if not ref:
        return "n/a"
    if value < ref["min"]:
        return "low"
    if value > ref["max"]:
        return "high"
    return "normal"


def get_clinical_interpretation(code: str, value: float) -> str:
    ref = REFERENCE_RANGES.get(code)
    if not ref:
        return "-"
    if value < ref["min"]:
        return ref.get("low", "Low")
    if value > ref["max"]:
        return ref.get("high", "High")
    return "Normal"
