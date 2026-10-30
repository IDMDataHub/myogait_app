from __future__ import annotations

from myogait_app import cli


def test_entry_script_finds_the_source_checkout(monkeypatch, tmp_path):
    package = tmp_path / "myogait_app"
    package.mkdir()
    (tmp_path / "app.py").write_text("# entry", encoding="utf-8")
    monkeypatch.setattr(cli, "__file__", str(package / "cli.py"))

    assert cli._entry_script() == str(tmp_path / "app.py")


def test_entry_script_reports_a_missing_entry(monkeypatch, tmp_path):
    package = tmp_path / "myogait_app"
    package.mkdir()
    monkeypatch.setattr(cli, "__file__", str(package / "cli.py"))

    try:
        cli._entry_script()
    except FileNotFoundError as exc:
        assert "Could not find" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("missing entry script should fail")


def test_default_flags_carry_theme_and_respect_overrides():
    from myogait_app.cli import _with_default_flags

    out = _with_default_flags(["--server.port", "9000", "--theme.base=dark"])
    assert "--theme.backgroundColor=#edeae3" in out
    assert "--server.maxUploadSize=2048" in out
    assert not any(a.startswith("--theme.base=light") for a in out)
    assert out[-3:] == ["--server.port", "9000", "--theme.base=dark"]
