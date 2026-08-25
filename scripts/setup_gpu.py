"""One-time GPU setup: detect the hardware, install the matching torch build.

Run once, right after installing requirements and before starting the app:

    pip install -r requirements.txt
    python scripts/setup_gpu.py
    streamlit run app.py

PyPI's default ``torch`` wheel is CPU-only on Windows; an NVIDIA or Intel
Arc/Xe GPU needs a build from a different wheel index instead. Nobody
should have to read a runtime warning and hand-type that pip command
themselves -- this script does the detection and runs it for them.

Pins ``torch==2.6.0`` (+ matching ``torchvision==0.21.0``) for the XPU
path specifically, not "latest" -- confirmed on real Intel Arc hardware
that this is not cosmetic. torch's newer XPU wheels (2.13.0 tried and
failed here) ship deeper nested third-party license directories
(kineto/libkineto/dynolog/prometheus-cpp/civetweb, a profiler tracing
dependency) that overflow Windows' 260-char ``MAX_PATH`` the moment the
venv sits at any non-trivial path -- 2.6.0's wheel does not carry that
dependency chain and installs clean even without Windows' long-paths
setting enabled. A short-lived conda env on this same machine
(``sapiens_intel_env``, found via PowerShell command history) had been
running exactly this pinned combination already -- not a guess.

Safe to run unconditionally, on any machine, any number of times: it is a
no-op (with an explanation) when torch already has working acceleration or
when no GPU it recognises is present. Also safe in a way myogait's own
``ensure_xpu_torch(auto_upgrade=True)`` (``MYOGAIT_AUTO_XPU=1``) is not: that
function ends in ``os.execv``, replacing the calling process, which is fine
for a one-shot CLI but fatal if triggered inside a long-lived, multi-session
Streamlit server. This script runs before the server ever starts, so there
is no live process for that to kill.
"""

from __future__ import annotations

import argparse
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from myogait_app.windows_paths import (
    long_paths_enabled_on_windows,
    needs_long_path_warning,
)

# Newest-first candidates actually published under
# https://download.pytorch.org/whl/cuXXX -- checked live against the index
# below rather than assumed, since PyTorch retires old tags and adds new
# ones over time and a hardcoded "current" choice goes stale.
_CUDA_TAG_CANDIDATES = [
    (13, 0), (12, 9), (12, 8), (12, 6), (12, 4), (12, 1), (11, 8),
]


_LONG_PATH_HINT = """
This is Windows' MAX_PATH limit (260 chars). Two independent fixes exist --
this script already uses the first for the XPU path, so seeing this means
either you are on the CUDA path (not yet pinned to an older build) or both
have failed:

  1) Pin an older torch/torchvision (this script does this for XPU: 2.6.0 /
     0.21.0). Newer releases ship deeper nested third-party license
     directories (kineto/libkineto/dynolog/prometheus-cpp/civetweb) that
     overflow MAX_PATH regardless of the registry setting below; older ones
     do not carry that dependency chain.
  2) Enable Windows long paths system-wide (needs Administrator; fixes it
     for every path-length problem, not just this one):

    New-ItemProperty -Path "HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem" \\
      -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
""".strip()


def _run(cmd: list[str], dry_run: bool = False) -> None:
    print("  $", " ".join(cmd))
    if dry_run:
        return
    result = subprocess.run(cmd, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        if "WinError 206" in result.stderr or "WinError 206" in result.stdout:
            print(result.stderr)
            print()
            print(_LONG_PATH_HINT)
        else:
            print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)


def _torch_state() -> tuple[str, bool, bool]:
    """(version, cuda_available, xpu_available); version is "" if absent."""
    try:
        import torch
    except ImportError:
        return "", False, False
    cuda_ok = torch.cuda.is_available()
    xpu_ok = hasattr(torch, "xpu") and torch.xpu.is_available()
    return torch.__version__, cuda_ok, xpu_ok


def _nvidia_driver_cuda_version() -> tuple[int, int] | None:
    """Max CUDA version this machine's NVIDIA driver supports, via nvidia-smi.

    nvidia-smi ships with the driver itself, not with torch or CUDA
    toolkit -- its presence means a real NVIDIA GPU with a working driver
    is installed, independent of whatever Python environment is active.
    """
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return None
    match = re.search(r"CUDA Version:\s*(\d+)\.(\d+)", out)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _best_cuda_tag(max_version: tuple[int, int]) -> str | None:
    """Newest published torch CUDA wheel tag this driver can run, or None."""
    for major, minor in _CUDA_TAG_CANDIDATES:
        if (major, minor) > max_version:
            continue
        tag = f"cu{major}{minor}"
        check = subprocess.run(
            [
                sys.executable, "-m", "pip", "index", "versions", "torch",
                "--index-url", f"https://download.pytorch.org/whl/{tag}",
            ],
            capture_output=True, text=True, timeout=30,
        )
        if check.returncode == 0:
            return tag
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, default=Path(sys.prefix))
    parser.add_argument("--dry-run", action="store_true", help="Print planned pip commands without running them.")
    args = parser.parse_args(argv)

    if needs_long_path_warning(args.venv, long_paths_enabled_on_windows(), sys.platform):
        print(
            "WARNING: Windows long paths are disabled and this virtual environment "
            f"is deep ({args.venv}). Recreate it at a short path such as C:\\mg\\venv "
            "before installing GPU packages, or enable LongPathsEnabled."
        )
        return 1

    version, cuda_ok, xpu_ok = _torch_state()

    if not version:
        print("torch is not installed -- run `pip install -r requirements.txt` first.")
        return

    if cuda_ok:
        print(f"torch {version} already has working CUDA acceleration -- nothing to do.")
        return
    if xpu_ok:
        print(f"torch {version} already has working Intel XPU acceleration -- nothing to do.")
        return

    driver_cuda = _nvidia_driver_cuda_version()
    if driver_cuda is not None:
        tag = _best_cuda_tag(driver_cuda)
        if tag:
            print(
                f"NVIDIA GPU found (driver supports up to CUDA {driver_cuda[0]}."
                f"{driver_cuda[1]}). Installing the matching torch build ({tag})..."
            )
            # --ignore-installed --no-deps, not --force-reinstall: the
            # latter uninstalls before reinstalling, which fails outright
            # if anything already using torch (e.g. this app's own preview
            # server) has its .pyd files open -- confirmed on this exact
            # machine. Overlaying in place sidesteps that.
            _run([
                sys.executable, "-m", "pip", "install",
                "--ignore-installed", "--no-deps", "torch",
                "--index-url", f"https://download.pytorch.org/whl/{tag}",
            ], dry_run=args.dry_run)
            print("Done. CUDA acceleration is now available to the app.")
            print(
                "If this fails with WinError 206 on a Windows machine, the fix "
                "that worked for the XPU path below (pin an older torch) likely "
                "applies here too -- see _LONG_PATH_HINT in this script."
            )
            return
        print(
            f"NVIDIA GPU found (driver supports up to CUDA {driver_cuda[0]}."
            f"{driver_cuda[1]}), but no matching published torch build was found "
            "automatically. Pick one yourself: https://pytorch.org/get-started/locally/"
        )
        return

    if platform.system() == "Windows" and "GenuineIntel" in platform.processor():
        print(
            "Intel CPU on Windows, no NVIDIA GPU detected. Installing torch "
            "2.6.0+xpu and its matching torchvision 0.21.0 (pinned -- see this "
            "script's module docstring for why not \"latest\") -- a no-op if this "
            "machine turns out to have no Arc/Xe GPU, since torch.xpu.is_"
            "available() just stays False..."
        )
        _run([
            sys.executable, "-m", "pip", "install",
            "--ignore-installed", "--no-deps", "torch==2.6.0",
            "--index-url", "https://download.pytorch.org/whl/xpu",
        ], dry_run=args.dry_run)
        _run([
            sys.executable, "-m", "pip", "install",
            "--ignore-installed", "--no-deps", "torchvision==0.21.0",
            "--index-url", "https://download.pytorch.org/whl/xpu",
        ], dry_run=args.dry_run)
        print("Done. If this machine has an Arc/Xe GPU, it is now available to the app.")
        return

    print("No GPU this script recognises -- staying on CPU-only torch.")


if __name__ == "__main__":
    raise SystemExit(main())
