"""Windows path-length preflight for local GPU environments."""

from __future__ import annotations

from pathlib import Path

# Leave headroom for nested wheel paths below site-packages and Scripts.
RISKY_VENV_PATH_LENGTH = 100


def needs_long_path_warning(
    venv_path: Path,
    long_paths_enabled: bool,
    platform_name: str,
) -> bool:
    """Whether an XPU install should be redirected to a shorter venv path."""
    return (
        platform_name == "win32"
        and not long_paths_enabled
        and len(str(Path(venv_path).resolve())) >= RISKY_VENV_PATH_LENGTH
    )


def long_paths_enabled_on_windows() -> bool:
    """Read the machine setting without failing on non-Windows systems."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\FileSystem",
        ) as key:
            return bool(winreg.QueryValueEx(key, "LongPathsEnabled")[0])
    except (ImportError, OSError):
        return False
