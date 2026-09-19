from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from python_refactor_mcp.adapters.pyright.environment_resolver import (
    PythonEnvironment,
    PythonEnvironmentResolver,
)


def _venv_python_path(project: Path) -> Path:
    if os.name == "nt":
        return project / ".venv" / "Scripts" / "python.exe"
    return project / ".venv" / "bin" / "python"


def _touch_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_explicit_python_wins(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    python = _touch_executable(tmp_path / "custom" / "python")
    (project / "pyproject.toml").write_text(
        f"""
[tool.refactor_mcp.python]
executable = "{python}"
""",
        encoding="utf-8",
    )
    _touch_executable(_venv_python_path(project))
    env = PythonEnvironmentResolver().resolve(project)
    assert isinstance(env, PythonEnvironment)
    assert env.executable == python.resolve()
    assert env.source == "explicit"


def test_project_venv(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    python = _touch_executable(_venv_python_path(project))
    env = PythonEnvironmentResolver().resolve(project)
    assert env.executable == python.resolve()
    assert env.source == "project_venv"
    assert env.executable != Path(sys.executable).resolve()


def test_windows_venv_python_layout(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    python = _touch_executable(project / ".venv" / "Scripts" / "python.exe")
    env = PythonEnvironmentResolver().resolve(project)
    assert env.executable == python.resolve()
    assert env.source == "project_venv"


def test_does_not_use_mcp_sys_executable_when_venv_exists(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    python = _touch_executable(_venv_python_path(project))
    env = PythonEnvironmentResolver().resolve(project)
    assert env.executable == python.resolve()
    assert Path(sys.executable).resolve() != python.resolve()


def test_skips_mcp_prefix_as_last_resort(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "mcp-venv"))
    if os.name == "nt":
        monkeypatch.setattr(
            sys, "executable", str(tmp_path / "mcp-venv" / "Scripts" / "python.exe")
        )
    else:
        monkeypatch.setattr(sys, "executable", str(tmp_path / "mcp-venv" / "bin" / "python"))
    env = PythonEnvironmentResolver().resolve(project)
    assert env.executable is None
    assert env.source == "unresolved"
