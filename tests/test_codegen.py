from __future__ import annotations

import pytest

from myogait_app.codegen import cli_command, python_snippet, yaml_config
from myogait_app.pipeline import PipelineConfig


def test_generated_python_compiles():
    source = python_snippet(PipelineConfig(), from_json=True)
    compile(source, "<generated>", "exec")


def test_generated_yaml_is_parseable():
    yaml = pytest.importorskip("yaml")
    assert isinstance(yaml.safe_load(yaml_config(PipelineConfig())), dict)


def test_generated_cli_is_a_nonempty_shell_command():
    command = cli_command(PipelineConfig(), "walk.mp4", "mediapipe")
    assert command.startswith("myogait ")
    # The presentation may wrap a single shell command with continuations.
    assert all(line.strip() for line in command.splitlines())
