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


#: The repository's ``.streamlit/config.toml`` is only read when Streamlit is
#: started from the repository root; a pip-installed ``myogait-app`` launched
#: from anywhere else lost the Bauhaus theme (white page) and fell back to
#: Streamlit's 200 MB upload cap. Mirror that file here as default flags;
#: any flag given on the command line wins. Keep in sync with
#: ``.streamlit/config.toml``.
_DEFAULT_FLAGS: dict[str, str] = {
    "server.maxUploadSize": "2048",
    "server.maxMessageSize": "2048",
    "server.enableXsrfProtection": "true",
    "browser.gatherUsageStats": "false",
    "theme.base": "light",
    "theme.primaryColor": "#c21b16",
    "theme.backgroundColor": "#edeae3",
    "theme.secondaryBackgroundColor": "#e3dfd6",
    "theme.textColor": "#111213",
    "theme.linkColor": "#7f4c00",
    "theme.borderColor": "#b9b6ac",
    "theme.showWidgetBorder": "true",
    "theme.baseRadius": "none",
    "theme.buttonRadius": "none",
    "theme.font": "Helvetica Neue, Helvetica, Arial, sans-serif",
    "theme.headingFont": "Helvetica Neue, Helvetica, Arial, sans-serif",
    "theme.codeFont": "JetBrains Mono, ui-monospace, monospace",
    "runner.fastReruns": "true",
}


def _with_default_flags(args: list[str]) -> list[str]:
    """Prepend ``--key=value`` for every default the user did not pass."""
    given = {a[2:].split("=", 1)[0] for a in args if a.startswith("--")}
    return [f"--{k}={v}" for k, v in _DEFAULT_FLAGS.items() if k not in given] + args


def main() -> None:
    """Run Streamlit, or print a local diagnostic when explicitly requested."""
    if sys.argv[1:] == ["--diagnose"]:
        from .diagnostics import build_diagnostic

        print(json.dumps(build_diagnostic(), indent=2, ensure_ascii=False))
        return

    from streamlit.web import cli as stcli

    sys.argv = ["streamlit", "run", _entry_script(), *_with_default_flags(sys.argv[1:])]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
