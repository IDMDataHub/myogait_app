from pathlib import Path

from myogait_app.windows_paths import needs_long_path_warning


def test_long_path_preflight_warns_only_for_deep_windows_venvs_without_support(tmp_path):
    deep = tmp_path / ("nested" * 20)
    assert needs_long_path_warning(deep, False, "win32")
    assert not needs_long_path_warning(Path("C:/mg/venv"), False, "win32")
    assert not needs_long_path_warning(deep, True, "win32")
    assert not needs_long_path_warning(deep, False, "linux")
