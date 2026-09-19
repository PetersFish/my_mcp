from __future__ import annotations

import os
from pathlib import Path

import pytest

from python_refactor_mcp.adapters.pyright.runtime import PyrightRuntime
from python_refactor_mcp.adapters.pyright.runtime_resolver import PyrightRuntimeResolver
from python_refactor_mcp.models.errors import RefactorError


def _venv_ls_cli(project: Path) -> tuple[Path, Path]:
    if os.name == "nt":
        base = project / ".venv" / "Scripts"
        return base / "pyright-langserver.exe", base / "pyright.exe"
    base = project / ".venv" / "bin"
    return base / "pyright-langserver", base / "pyright"


def _touch_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def test_explicit_runtime_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        """
[tool.refactor_mcp.pyright]
language_server = "{ls}"
cli = "{cli}"
""".format(
            ls=tmp_path / "explicit" / "pyright-langserver",
            cli=tmp_path / "explicit" / "pyright",
        ),
        encoding="utf-8",
    )
    ls = _touch_executable(tmp_path / "explicit" / "pyright-langserver")
    cli = _touch_executable(tmp_path / "explicit" / "pyright")
    venv_ls, _venv_cli = _venv_ls_cli(project)
    _touch_executable(venv_ls)
    monkeypatch.setattr(
        "python_refactor_mcp.adapters.pyright.runtime_resolver.shutil.which",
        lambda name: str(tmp_path / "mcp" / name),
    )
    runtime = PyrightRuntimeResolver().resolve(project)
    assert isinstance(runtime, PyrightRuntime)
    assert runtime.source == "explicit"
    assert runtime.language_server == ls.resolve()
    assert runtime.cli == cli.resolve()


def test_project_venv_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "proj"
    ls_path, cli_path = _venv_ls_cli(project)
    ls = _touch_executable(ls_path)
    cli = _touch_executable(cli_path)
    monkeypatch.setattr(
        "python_refactor_mcp.adapters.pyright.runtime_resolver.shutil.which",
        lambda name: None,
    )
    runtime = PyrightRuntimeResolver().resolve(project)
    assert runtime.source == "project"
    assert runtime.language_server == ls.resolve()
    assert runtime.cli == cli.resolve()


def test_project_node_modules_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "proj"
    if os.name == "nt":
        ls = _touch_executable(project / "node_modules" / ".bin" / "pyright-langserver.cmd")
    else:
        ls = _touch_executable(project / "node_modules" / ".bin" / "pyright-langserver")
    monkeypatch.setattr(
        "python_refactor_mcp.adapters.pyright.runtime_resolver.shutil.which",
        lambda name: None,
    )
    runtime = PyrightRuntimeResolver().resolve(project)
    assert runtime.source == "project"
    assert runtime.language_server == ls.resolve()


def test_project_prefers_venv_exe_over_node_cmd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "proj"
    ls_path, cli_path = _venv_ls_cli(project)
    ls = _touch_executable(ls_path)
    _touch_executable(cli_path)
    _touch_executable(project / "node_modules" / ".bin" / "pyright-langserver.cmd")
    monkeypatch.setattr(
        "python_refactor_mcp.adapters.pyright.runtime_resolver.shutil.which",
        lambda name: None,
    )
    runtime = PyrightRuntimeResolver().resolve(project)
    assert runtime.source == "project"
    assert runtime.language_server == ls.resolve()


def test_mcp_fallback_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    ls = _touch_executable(tmp_path / "mcp-bin" / "pyright-langserver")
    cli = _touch_executable(tmp_path / "mcp-bin" / "pyright")

    def which(name: str) -> str | None:
        if name == "pyright-langserver":
            return str(ls)
        if name == "pyright":
            return str(cli)
        return None

    monkeypatch.setattr(
        "python_refactor_mcp.adapters.pyright.runtime_resolver.shutil.which",
        which,
    )
    monkeypatch.setattr(
        "python_refactor_mcp.adapters.pyright.runtime_resolver.sys.prefix",
        str(tmp_path / "mcp-env"),
    )
    runtime = PyrightRuntimeResolver().resolve(project)
    assert runtime.source == "mcp_fallback"
    assert runtime.language_server == ls.resolve()
    assert runtime.cli == cli.resolve()


def test_no_runtime_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(
        "python_refactor_mcp.adapters.pyright.runtime_resolver.shutil.which",
        lambda name: None,
    )
    monkeypatch.setattr(
        "python_refactor_mcp.adapters.pyright.runtime_resolver.sys.prefix",
        str(tmp_path / "empty-prefix"),
    )
    with pytest.raises(RefactorError) as exc:
        PyrightRuntimeResolver().resolve(project)
    assert exc.value.code == "PYRIGHT_NOT_FOUND"
