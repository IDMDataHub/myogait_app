#!/usr/bin/env python3
"""Preflight the local Python environment before installing GPU/XPU extras."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from myogait_app.windows_paths import (
    long_paths_enabled_on_windows,
    needs_long_path_warning,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venv", type=Path, default=Path(sys.prefix))
    args = parser.parse_args()

    enabled = long_paths_enabled_on_windows()
    if needs_long_path_warning(args.venv, enabled, sys.platform):
        print(
            "WARNING: Windows long paths are disabled and this virtual environment "
            f"is deep ({args.venv}). Create it at a short path such as C:\\mg\\venv "
            "before installing Intel XPU packages, or enable LongPathsEnabled."
        )
        return 1
    print(f"GPU/XPU environment preflight passed for {args.venv}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
