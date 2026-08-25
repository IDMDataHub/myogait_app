from __future__ import annotations

from myogait_app.diagnostics import build_diagnostic
from myogait_app.runtime import Runtime
from myogait_app.settings import Settings


def test_diagnostic_reports_local_runtime_without_personal_data(tmp_path):
    runtime = Runtime("0.8.2", "1.4.9", "cpu", "test", (), (), (), warnings=("example",))
    settings = Settings(workspace_root=tmp_path / "workspace", retention_hours=12)

    diagnostic = build_diagnostic(settings, runtime)

    assert diagnostic["workspace"]["writable"]
    assert diagnostic["workspace"]["free_mb"] > 0
    assert diagnostic["runtime"]["myogait_version"] == "0.8.2"
    assert diagnostic["runtime"]["warnings"] == ["example"]
    assert diagnostic["settings"]["retention_hours"] == 12
