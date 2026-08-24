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
        return all(_has(module) for module in self.requires)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(module for module in self.requires if not _has(module))


_SETUP_HINT = "Needs: myogait setup-sapiens2"

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
    BackendInfo("hrnet", "HRNet-W48", ("mmpose",), "17 COCO", "", "heavy"),
    BackendInfo("mmpose", "RTMPose-m", ("mmpose",), "17 COCO", "", "medium"),
    BackendInfo("alphapose", "AlphaPose FastPose", ("torch", "torchvision", "ultralytics"), "17 COCO", "", "medium"),
    BackendInfo("detectron2", "Keypoint R-CNN", ("detectron2",), "17 COCO", "", "heavy"),
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
    "opensim": ("myogait.opensim", "export_opensim_scale_setup"),
    "report": ("myogait.report", "generate_report"),
    "longitudinal": ("myogait.plotting", "plot_longitudinal"),
    "skeleton_video": ("myogait.video", "render_skeleton_video"),
    "stickfigure": ("myogait.video", "render_stickfigure_animation"),
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
    def available_backends(self) -> tuple[BackendInfo, ...]:
        return tuple(b for b in BACKENDS if b.available)

    @property
    def unavailable_backends(self) -> tuple[BackendInfo, ...]:
        return tuple(b for b in BACKENDS if not b.available)

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
