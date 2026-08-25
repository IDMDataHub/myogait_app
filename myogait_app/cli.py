"""Console entry point: launch the Streamlit workbench.

Installed as the ``myogait-app`` command (see ``pyproject.toml``) and also
reachable as ``python -m myogait_app``. Both resolve the Streamlit entry
script and hand off to Streamlit's own CLI, so every ``streamlit run``
flag still works: ``myogait-app --server.address 127.0.0.1``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _entry_script() -> str:
    """Locate the Streamlit entry script in both install and source layouts.

    A wheel ships ``app.py`` inside the package as ``streamlit_app.py``
    (see the hatch ``force-include`` in ``pyproject.toml``); a source
    checkout keeps it at the repository root next to the package.
    """
    here = Path(__file__).resolve().parent
    for candidate in (here / "streamlit_app.py", here.parent / "app.py"):
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError(
        "Could not find the Streamlit entry script (streamlit_app.py or app.py)."
    )


def main() -> None:
    """Run Streamlit, or print a local diagnostic when explicitly requested."""
    if sys.argv[1:] == ["--diagnose"]:
        from .diagnostics import build_diagnostic

        print(json.dumps(build_diagnostic(), indent=2, ensure_ascii=False))
        return

    from streamlit.web import cli as stcli

    sys.argv = ["streamlit", "run", _entry_script(), *sys.argv[1:]]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
