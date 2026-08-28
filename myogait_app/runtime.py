"""Environment probing.

The set of usable pose backends depends entirely on what is installed on
the machine, and that differs between a laptop and the lab server. Rather
than hardcode a list that will drift, the app asks the environment at
startup and only offers what can actually run.

Probing uses :func:`importlib.util.find_spec`, which resolves a module
without importing it -- importing torch or mediapipe just to grey out a
checkbox would cost seconds and a lot of memory.
"""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import importlib.util
from dataclasses import dataclass, field
from functools import lru_cache

#: Minimum myogait version this app is written against. Below it, the
#: clinical scores, Sapiens 2 backends, bias corrections and the VICON
#: block simply do not exist.
REQUIRED_MYOGAIT = (0, 6, 1)

#: Minimum gaitkit version exposing the gk_* event detectors that the
#: comparator puts in competition with the built-in ones.
REQUIRED_GAITKIT = (1, 4, 8)

#: Below this version, load_c3d normalised the antero-posterior and
#: vertical axes independently, silently distorting angles on any
#: non-square recording -- the bug myogait_app.c3d_utils compensates for.
#: 0.8.0 fixed it upstream (isotropic normalisation, both axes divided by
#: the same range), so from this version on the app's own correction must
#: NOT run, or it double-corrects and distorts the aspect ratio the other
#: way. See Runtime.c3d_isotropic_native.
C3D_ISOTROPIC_NATIVE_VERSION = (0, 8, 0)

#: Below this version, ``load_c3d`` used exactly one marker convention
#: (its own ``DEFAULT_C3D_MARKER_MAP``) and raised ``ValueError`` on
#: anything else. 0.7.0 added ``detect_c3d_convention`` -- autodetection
#: across several registered conventions, with per-convention scoring.
C3D_CONVENTION_AUTODETECT_VERSION = (0, 7, 0)

#: Below this version, ``compute_angles`` has no ``calibration_max_offset_
#: deg`` parameter and ``segment_cycles`` has no ``min_confidence``/
#: ``min_coherence`` parameters -- both new quality guards added in the
#: 0.8.x line. See Runtime.calibration_guard_supported and
#: Runtime.cycle_quality_gates_supported.
CALIBRATION_MAX_OFFSET_VERSION = (0, 8, 0)
CYCLE_QUALITY_GATES_VERSION = (0, 8, 1)

#: Below this version, ``analyze_gait``/``step_length``/``walking_speed``
#: only accept ``height_m`` -- a measured femur or foot length had to be
#: smuggled in by inverting myogait's own population femur-to-height
#: ratio (see ``pipeline.SubjectConfig.calibration_height_m``). 0.7.0
#: added native ``femur_mm``/``foot_mm``/``femur_ratio`` parameters.
NATIVE_ANTHROPOMETRIC_CALIBRATION_VERSION = (0, 7, 0)

#: Below this version, ``step_length``/``walking_speed`` applied the
#: (mostly vertical) femur scale directly to the normalised horizontal
#: antero-posterior displacement. Landmarks are normalised per axis
#: (x / width, y / height), so on a non-square frame that under-estimated
#: step and stride length by roughly the image aspect ratio (~1.78x on
#: 16:9). 0.8.2 de-normalises distances to source pixels first, making the
#: scale isotropic. The segment-based calibration cross-check
#: (myogait_app.calibration) mirrors this geometry, so it must apply the
#: same de-normalisation from this version on to stay comparable. See
#: Runtime.step_length_isotropic_native.
STEP_LENGTH_ISOTROPIC_VERSION = (0, 8, 2)


def _version_tuple(raw: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in str(raw).split("."):
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def _installed_version(package: str) -> str | None:
    try:
        return importlib_metadata.version(package)
    except importlib_metadata.PackageNotFoundError:
        return None


def _has(module: str) -> bool:
    """True when *module* can be resolved without importing it."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def _myogait_backend_availability() -> dict[str, bool] | None:
    """Ask myogait's own registry which pose backends are importable.

    ``myogait.models.available_models()`` exists specifically for this:
    its docstring calls it out as "suitable for a UI to grey out
    unavailable options". It is the ground truth for what each backend
    module actually imports -- a mapping only myogait's own author can
    keep correct, and this app's local ``BACKENDS.requires`` copy has
    already drifted from it once (``hrnet`` was gated on ``mmpose`` here;
    myogait needs only ``torch`` for it). Not cached: a Sapiens 2 setup
    job run from this app writes new files into the *same* process, and
    the next rerun should see it without a restart. Returns ``None`` on
    a myogait old enough to lack this API, so the caller falls back to
    ``BackendInfo.requires``.
    """
    try:
        from myogait.models import available_models
    except ImportError:
        return None
    try:
        return available_models()
    except Exception:
        return None


@dataclass(frozen=True)
class BackendInfo:
    """One entry of the pose-model registry, with its availability."""

    name: str
    label: str
    requires: tuple[str, ...]
    keypoints: str
    note: str = ""
    #: Rough cost hint, used to warn before launching a long extraction.
    weight: str = "light"  # light | medium | heavy

    @property
    def available(self) -> bool:
        return self.is_available()

    def is_available(self, live: dict[str, bool] | None = None) -> bool:
        """Return availability, optionally from one shared registry probe."""
        if live is None:
            live = _myogait_backend_availability()
        if live is not None and self.name in live:
            return live[self.name]
        return all(_has(module) for module in self.requires)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(module for module in self.requires if not _has(module))

    @property
    def install_hint(self) -> str:
        """Best-effort install command, mirroring myogait's own error text.

        ``myogait.models.get_extractor`` raises ``MissingDependencyError``
        with exactly ``pip install myogait[{name.split('-')[0]}]`` --
        matched here so the hint in this app's UI is the same command
        myogait itself would suggest at the point of failure. Verified
        against myogait's actual declared extras (Aug 2026) rather than
        assumed, since that generic formula is wrong for three backends:

        - ``openpose`` needs only ``cv2``, already a base dependency
          (``opencv-python-headless``) -- no extra exists or is needed.
        - ``hrnet`` needs only ``torch``, and no ``[hrnet]`` extra wraps
          it -- installing any extra that happens to include torch would
          pull unrelated packages along with it.
        - ``detectron2``'s extra is real but installs only its
          prerequisite (``torch``): the ``detectron2`` package itself is
          not on PyPI under any name, on any platform, and never will be
          -- the upstream project publishes no wheels at all.
        """
        if self.name == "openpose":
            return "Included with the base install (cv2) -- nothing extra to install."
        if self.name == "hrnet":
            return "pip install torch"
        if self.name == "detectron2":
            return (
                'pip install "myogait[detectron2]" (installs torch, the '
                "prerequisite), then separately: pip install "
                '"git+https://github.com/facebookresearch/detectron2.git" '
                "-- not on PyPI, needs a C++ build toolchain, and the "
                "upstream project is unmaintained and pinned to older "
                "PyTorch/Python, so a source build can fail even after "
                "the toolchain is set up."
            )
        extra = self.name.split("-")[0]
        return f'pip install "myogait[{extra}]"'


#: First extraction with this size fetches its weights automatically (see
#: jobs.py::_fetch_sapiens2_weights) -- no separate setup command needed.
_SETUP_HINT = "First use downloads weights automatically (several GB, one time)."

#: The registry mirrors myogait.models.EXTRACTORS. Kept explicit here
#: because the app needs the dependency and cost metadata that the
#: package registry does not carry.
BACKENDS: tuple[BackendInfo, ...] = (
    BackendInfo("mediapipe", "MediaPipe", ("mediapipe",), "33", "CPU, fast", "light"),
    BackendInfo("yolo", "YOLOv8-Pose", ("ultralytics",), "17 COCO", "Fast, robust", "light"),
    BackendInfo("openpose", "OpenPose", ("cv2",), "17 COCO", "Built-in via OpenCV DNN", "medium"),
    BackendInfo("vitpose", "ViTPose (base)", ("transformers", "torch"), "17 COCO", "", "medium"),
    BackendInfo("vitpose-large", "ViTPose+ (large)", ("transformers", "torch"), "17 COCO", "", "heavy"),
    BackendInfo("vitpose-huge", "ViTPose+ (huge)", ("transformers", "torch"), "17 COCO", "", "heavy"),
    BackendInfo("rtmw", "RTMW whole-body", ("rtmlib", "onnxruntime"), "133", "ONNX, real-time", "medium"),
    # myogait needs only torch for hrnet -- not mmpose. Confirmed against
    # myogait.models's own requirement map (Aug 2026), which this app's
    # copy had drifted from.
    BackendInfo("hrnet", "HRNet-W48", ("torch",), "17 COCO", "", "heavy"),
    BackendInfo("mmpose", "RTMPose-m", ("mmpose", "mmdet"), "17 COCO", "", "medium"),
    BackendInfo("alphapose", "AlphaPose FastPose", ("torch", "torchvision", "ultralytics"), "17 COCO", "", "medium"),
    BackendInfo("detectron2", "Keypoint R-CNN", ("detectron2", "torch"), "17 COCO", "", "heavy"),
    BackendInfo("sapiens-quick", "Sapiens 0.3B", ("torch", "huggingface_hub"), "17 + 308", "", "heavy"),
    BackendInfo("sapiens-mid", "Sapiens 0.6B", ("torch", "huggingface_hub"), "17 + 308", "", "heavy"),
    BackendInfo("sapiens-top", "Sapiens 1B", ("torch", "huggingface_hub"), "17 + 308", "", "heavy"),
    BackendInfo("sapiens2-quick", "Sapiens 2 0.4B", ("torch", "safetensors", "huggingface_hub"), "17 + 308", _SETUP_HINT, "heavy"),
    BackendInfo("sapiens2-mid", "Sapiens 2 0.8B", ("torch", "safetensors", "huggingface_hub"), "17 + 308", _SETUP_HINT, "heavy"),
    BackendInfo("sapiens2-top", "Sapiens 2 1B", ("torch", "safetensors", "huggingface_hub"), "17 + 308", _SETUP_HINT, "heavy"),
    BackendInfo("sapiens2-ultra", "Sapiens 2 5B", ("torch", "safetensors", "huggingface_hub"), "17 + 308", _SETUP_HINT, "heavy"),
)

#: Backends whose auxiliary depth / segmentation heads exist.
SAPIENS_BACKENDS = tuple(b.name for b in BACKENDS if b.name.startswith("sapiens"))

#: Sapiens 2 backend name -> the size key myogait's own registry uses
#: (myogait.models.sapiens2._MODELS), and the weight-file stem it
#: downloads under that key.
SAPIENS2_SIZES: dict[str, str] = {
    "sapiens2-quick": "0.4b",
    "sapiens2-mid": "0.8b",
    "sapiens2-top": "1b",
    "sapiens2-ultra": "5b",
}


def sapiens2_weights_ready(name: str) -> bool:
    """True once a Sapiens 2 size is immediately usable with no extra step.

    Only a traced ``.pt2`` qualifies -- it is self-contained and
    ``torch.jit.load``-able with no other dependency. A ``.safetensors``
    alone does **not**: loading it needs Meta's ``sapiens`` package to
    reconstruct the model architecture first (myogait's own
    ``ImportError`` message spells this out), so a size that has only
    been downloaded but never traced is functionally identical to one
    that has not been fetched at all -- both need
    ``_fetch_sapiens2_weights`` to run before ``get_extractor`` can load
    them. An earlier version of this check treated ``.safetensors``
    alone as "ready" and was wrong: confirmed live, ``sapiens2-ultra``
    (5B) has only a ``.safetensors`` cached (its trace was never run,
    likely because it is the one size with no ``.pt2`` produced yet) and
    picking it failed with exactly that ``ImportError`` before this fix.

    Checks the same locations myogait's own ``_find_model`` looks in
    (``~/.myogait/models/`` and ``./models/``) -- see
    myogait.models.sapiens2.
    """
    from pathlib import Path

    size = SAPIENS2_SIZES.get(name)
    if size is None:
        return True  # not a Sapiens 2 backend -- no separate weight step
    stem = f"sapiens2_{size}_pose"
    for directory in (Path.home() / ".myogait" / "models", Path.cwd() / "models"):
        if (directory / f"{stem}.pt2").exists():
            return True
    return False


def sapiens2_seg_weights_ready(name: str) -> bool:
    """Like ``sapiens2_weights_ready``, but for the *segmentation* model.

    Discovered live, not anticipated: myogait's ``with_seg=True`` option
    loads a completely separate cached file
    (``sapiens2_{size}_seg.*``) from the pose model
    (``sapiens2_{size}_pose.*``) that ``sapiens2_weights_ready`` checks --
    two independent downloads, independently traced. Checking only the
    pose file let a size whose segmentation weights existed solely as
    ``.safetensors`` (never traced) through as "ready", and picking it
    with the Sapiens segmentation checkbox on hit the exact same "needs
    Meta's sapiens package" ``ImportError`` the pose-only fetch exists to
    prevent.
    """
    from pathlib import Path

    size = SAPIENS2_SIZES.get(name)
    if size is None:
        return True
    stem = f"sapiens2_{size}_seg"
    for directory in (Path.home() / ".myogait" / "models", Path.cwd() / "models"):
        if (directory / f"{stem}.pt2").exists():
            return True
    return False


#: Env vars this app sets around an extraction call to steer myogait's
#: own device auto-detection (cuda > xpu > cpu, hardcoded inside every
#: backend module -- myogait exposes no device parameter or env var of
#: its own). Caveat that the UI must state plainly: PyTorch caches CUDA
#: availability after the first successful init in a process, so forcing
#: "cpu" *after* an earlier extraction already used the GPU in this same
#: long-lived Streamlit server process may not take effect until the app
#: is restarted -- a PyTorch limitation, not something settable here.
DEVICE_OVERRIDE_ENV: dict[str, dict[str, str]] = {
    "cpu": {"CUDA_VISIBLE_DEVICES": "", "ZE_AFFINITY_MASK": ""},
    "xpu": {"CUDA_VISIBLE_DEVICES": ""},
}
DEVICE_CHOICES: tuple[str, ...] = ("auto", "cpu", "cuda", "xpu")
DEVICE_LABELS: dict[str, str] = {
    "auto": "Auto-detect",
    "cpu": "Force CPU",
    "cuda": "Force GPU (CUDA)",
    # XPU is PyTorch's device type for Intel Arc/Xe *GPUs*, not the
    # separate NPU chip on Intel Core Ultra machines -- torch has no NPU
    # device API at all (confirmed: no torch.npu, only torch.cuda and
    # torch.xpu), and myogait has no NPU code path anywhere. Do not
    # relabel this "NPU" again; it was wrong the first time.
    "xpu": "Force GPU (Intel XPU/Arc)",
}


def xpu_upgrade_hint() -> str | None:
    """The pip command to get Intel Arc/Xe GPU acceleration, or None.

    PyPI's default ``torch`` wheel for Windows is CPU-only; Intel Arc/Xe
    needs the build from PyTorch's dedicated XPU index instead. myogait
    already detects this exact situation itself
    (``myogait.models.base.ensure_xpu_torch``), so this mirrors that
    function's own condition -- Windows, GenuineIntel CPU, no CUDA, no
    working XPU, a ``+cpu`` (or XPU-less) torch build -- rather than
    polling the GPU directly through WMI or a subprocess, which would be
    slower and platform-specific in a module that otherwise probes
    everything through cheap, import-free checks.

    Deliberately does NOT call ``ensure_xpu_torch()`` itself: its
    automatic-upgrade path runs ``pip install --force-reinstall`` and
    then ``os.execv``, which *replaces the current process* -- fatal to
    a long-lived, multi-session Streamlit server (every connected user's
    session dies with it). Detection only; installing stays a command
    the user runs themselves, same as every other backend's install hint.
    """
    import platform

    if platform.system() != "Windows":
        return None
    if "GenuineIntel" not in platform.processor():
        return None
    try:
        import torch
    except ImportError:
        return None
    if torch.cuda.is_available():
        return None
    if hasattr(torch, "xpu") and torch.xpu.is_available():
        return None
    is_cpu_build = "+cpu" in torch.__version__ or not hasattr(torch, "xpu")
    if not is_cpu_build:
        return None
    return "pip install torch --index-url https://download.pytorch.org/whl/xpu"


def _detect_device() -> tuple[str, str]:
    """Return (device, detail) describing the best compute device.

    Reported rather than assumed: the same code runs on a CPU-only
    laptop, a CUDA server, and an Intel Arc machine, and the user needs
    to know which one is about to run a heavy extraction.
    """
    if not _has("torch"):
        return "cpu", "torch not installed"

    try:
        import torch
    except Exception as exc:  # pragma: no cover - defensive
        return "cpu", f"torch import failed: {exc}"

    try:
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            return "cuda", f"{name} (torch {torch.__version__})"
    except Exception:
        pass

    try:
        if hasattr(torch, "xpu") and torch.xpu.is_available():
            return "xpu", f"Intel XPU (torch {torch.__version__})"
    except Exception:
        pass

    # An NPU is not visible through torch on Windows; it surfaces as an
    # onnxruntime execution provider instead. Only the RTMW backend can
    # use it today, so it is reported but not treated as the main device.
    return "cpu", f"CPU only (torch {torch.__version__})"


def _onnx_providers() -> tuple[str, ...]:
    if not _has("onnxruntime"):
        return ()
    try:
        import onnxruntime

        return tuple(onnxruntime.get_available_providers())
    except Exception:
        return ()


#: Optional myogait functions the app offers as toggles. They appeared at
#: different versions -- apply_linear_detrend, for instance, does not exist
#: at all before 0.6.1 -- so availability is probed rather than assumed,
#: and the interface disables what the installed version cannot do.
OPTIONAL_FEATURES: dict[str, tuple[str, str]] = {
    # feature key -> (module, attribute)
    "detrend": ("myogait.corrections", "apply_linear_detrend"),
    "ankle_bias": ("myogait.corrections", "apply_ankle_bias_correction"),
    "hip_bias": ("myogait.corrections", "apply_hip_bias_correction"),
    "knee_bias": ("myogait.corrections", "apply_knee_bias_correction"),
    "perspective": ("myogait.corrections", "apply_perspective_correction"),
    "frontal_angles": ("myogait.angles", "compute_frontal_angles"),
    "coherence": ("myogait.normalize", "frame_coherence_score"),
    "scores": ("myogait.scores", "gait_profile_score_2d"),
    "sdi": ("myogait.scores", "sagittal_deviation_index"),
    "normative": ("myogait.normative", "get_normative_band"),
    "vicon": ("myogait.experimental_vicon", "run_single_trial_vicon_benchmark"),
    "benchmark": ("myogait.experimental_benchmark", "run_single_pair_benchmark"),
    "degradation": ("myogait.experimental", "apply_video_degradation"),
    "c3d": ("myogait.export", "export_c3d"),
    "c3d_import": ("myogait.experimental_vicon", "load_c3d"),
    "c3d_convention": ("myogait.experimental_vicon", "detect_c3d_convention"),
    "c3d_reference_angles": ("myogait.experimental_vicon", "compute_c3d_reference_angles"),
    "canonicalize_signs": ("myogait.angles", "canonicalize_angle_signs"),
    "opensim": ("myogait.opensim", "export_opensim_scale_setup"),
    "report": ("myogait.report", "generate_report"),
    "longitudinal": ("myogait.plotting", "plot_longitudinal"),
    "skeleton_video": ("myogait.video", "render_skeleton_video"),
    "stickfigure": ("myogait.video", "render_stickfigure_animation"),
    # myogait >= 0.8.6 (merged from feat/isb-3d-angles-tier1). Presence-
    # checked like every other OPTIONAL_FEATURES entry rather than
    # version-gated, so an older install degrades cleanly instead of
    # failing an import at click time.
    "isb_reconstruction": ("myogait.isb", "reconstruct_isb_angles"),
    "isb_reconstruction_tier2": ("myogait.vicon_calibration", "reconstruct_isb_angles_tier2"),
    "isb_reconstruction_tier3": ("myogait.vicon_calibration", "reconstruct_isb_angles_tier3"),
}


#: Features whose myogait function exists but which fail at call time
#: without a third-party package. ``export_c3d`` is always importable and
#: raises only once invoked, so probing the attribute alone would offer a
#: button that cannot work.
FEATURE_EXTRA_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "c3d": ("c3d",),
    "c3d_import": ("ezc3d",),
}


def _probe_features() -> frozenset[str]:
    """Return the optional feature keys this myogait install can actually run.

    Each probe imports the owning module, which is unavoidable: the
    attribute cannot be seen otherwise. They are all small pure-Python
    modules already pulled in by the pipeline, so the cost is negligible
    compared to probing a pose backend.
    """
    import importlib

    found: set[str] = set()
    for key, (module_name, attribute) in OPTIONAL_FEATURES.items():
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        if not hasattr(module, attribute):
            continue
        if not all(_has(dep) for dep in FEATURE_EXTRA_REQUIREMENTS.get(key, ())):
            continue
        found.add(key)
    return frozenset(found)


@dataclass(frozen=True)
class Runtime:
    """A snapshot of what this machine can do."""

    myogait_version: str | None
    gaitkit_version: str | None
    device: str
    device_detail: str
    onnx_providers: tuple[str, ...]
    event_methods: tuple[str, ...]
    angle_methods: tuple[str, ...]
    features: frozenset[str] = field(default_factory=frozenset)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def has(self, feature: str) -> bool:
        """True when the installed myogait exposes *feature*."""
        return feature in self.features

    def missing_feature_hint(self, feature: str) -> str:
        module, attribute = OPTIONAL_FEATURES.get(feature, ("myogait", feature))
        return (
            f"{module}.{attribute} is not available in myogait "
            f"{self.myogait_version or 'unknown'}."
        )

    @property
    def myogait_ok(self) -> bool:
        if not self.myogait_version:
            return False
        return _version_tuple(self.myogait_version) >= REQUIRED_MYOGAIT

    @property
    def gaitkit_ok(self) -> bool:
        if not self.gaitkit_version:
            return False
        return _version_tuple(self.gaitkit_version) >= REQUIRED_GAITKIT

    @property
    def c3d_isotropic_native(self) -> bool:
        """True when load_c3d already normalises both axes isotropically.

        The C3D tab's own aspect-ratio recovery (myogait_app.c3d_utils)
        must be offered only when this is False -- on a fixed install it
        would re-apply a correction load_c3d already made, distorting the
        result a second time.
        """
        if not self.myogait_version:
            return False
        return _version_tuple(self.myogait_version) >= C3D_ISOTROPIC_NATIVE_VERSION

    @property
    def c3d_convention_autodetect(self) -> bool:
        """True when ``load_c3d`` can autodetect the marker convention itself."""
        if not self.myogait_version:
            return False
        return _version_tuple(self.myogait_version) >= C3D_CONVENTION_AUTODETECT_VERSION

    @property
    def calibration_guard_supported(self) -> bool:
        """True when ``compute_angles`` accepts ``calibration_max_offset_deg``."""
        if not self.myogait_version:
            return False
        return _version_tuple(self.myogait_version) >= CALIBRATION_MAX_OFFSET_VERSION

    @property
    def cycle_quality_gates_supported(self) -> bool:
        """True when ``segment_cycles`` accepts ``min_confidence``/``min_coherence``."""
        if not self.myogait_version:
            return False
        return _version_tuple(self.myogait_version) >= CYCLE_QUALITY_GATES_VERSION

    @property
    def native_anthropometric_calibration(self) -> bool:
        """True when ``analyze_gait`` accepts ``femur_mm``/``foot_mm`` directly."""
        if not self.myogait_version:
            return False
        return (
            _version_tuple(self.myogait_version)
            >= NATIVE_ANTHROPOMETRIC_CALIBRATION_VERSION
        )

    @property
    def step_length_isotropic_native(self) -> bool:
        """True when ``step_length``/``walking_speed`` de-normalise to source pixels.

        The calibration cross-check (myogait_app.calibration) must apply
        the same isotropic de-normalisation only when this is True -- on an
        older install myogait itself still uses the anisotropic geometry,
        so the cross-check has to match it to stay comparable.
        """
        if not self.myogait_version:
            return False
        return _version_tuple(self.myogait_version) >= STEP_LENGTH_ISOTROPIC_VERSION

    @property
    def available_backends(self) -> tuple[BackendInfo, ...]:
        availability = self.backend_availability()
        return tuple(b for b in BACKENDS if availability[b.name])

    @property
    def unavailable_backends(self) -> tuple[BackendInfo, ...]:
        availability = self.backend_availability()
        return tuple(b for b in BACKENDS if not availability[b.name])

    def backend_availability(self) -> dict[str, bool]:
        """Snapshot backend availability with one registry probe per rerun.

        The snapshot deliberately lives only for this call. A setup job can
        install a component while the Streamlit process remains alive, so the
        next rerun must probe again; caching this across reruns would leave the
        model picker stale.
        """
        live = _myogait_backend_availability()
        return {backend.name: backend.is_available(live) for backend in BACKENDS}

    @property
    def accelerated(self) -> bool:
        return self.device in ("cuda", "xpu")

    def backend(self, name: str) -> BackendInfo | None:
        for entry in BACKENDS:
            if entry.name == name:
                return entry
        return None


@lru_cache(maxsize=1)
def get_runtime() -> Runtime:
    """Probe the environment once per process."""
    myogait_version = _installed_version("myogait")
    gaitkit_version = _installed_version("gaitkit")
    device, detail = _detect_device()

    event_methods: tuple[str, ...] = ()
    angle_methods: tuple[str, ...] = ()
    warnings: list[str] = []

    try:
        from myogait import list_event_methods

        event_methods = tuple(list_event_methods())
    except Exception as exc:
        warnings.append(f"Could not list event methods: {exc}")

    try:
        from myogait.angles import list_angle_methods

        angle_methods = tuple(list_angle_methods())
    except Exception as exc:
        warnings.append(f"Could not list angle methods: {exc}")

    if not myogait_version:
        warnings.append("myogait is not installed in this environment.")
    elif _version_tuple(myogait_version) < REQUIRED_MYOGAIT:
        required = ".".join(str(part) for part in REQUIRED_MYOGAIT)
        warnings.append(
            f"myogait {myogait_version} is older than the {required} this app "
            "targets. Clinical scores, Sapiens 2, bias corrections and the "
            "VICON block will be missing or behave differently."
        )

    if not gaitkit_version:
        warnings.append(
            "gaitkit is not installed - the gk_* event detectors are unavailable."
        )
    elif _version_tuple(gaitkit_version) < REQUIRED_GAITKIT:
        required = ".".join(str(part) for part in REQUIRED_GAITKIT)
        warnings.append(
            f"gaitkit {gaitkit_version} is older than the {required} myogait "
            "requires - the gk_* detectors may be missing or unreliable."
        )

    features = _probe_features()

    return Runtime(
        myogait_version=myogait_version,
        gaitkit_version=gaitkit_version,
        device=device,
        device_detail=detail,
        onnx_providers=_onnx_providers(),
        event_methods=event_methods,
        angle_methods=angle_methods or ("sagittal_vertical_axis", "sagittal_classic"),
        features=features,
        warnings=tuple(warnings),
    )
