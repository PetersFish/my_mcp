from __future__ import annotations

from pathlib import Path

import pytest

from python_refactor_mcp.adapters.pyright.runtime import PyrightRuntime
from python_refactor_mcp.adapters.pyright.runtime_resolver import PyrightRuntimeResolver
from python_refactor_mcp.models.errors import RefactorError


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
    _touch_executable(project / ".venv" / "bin" / "pyright-langserver")
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
    ls = _touch_executable(project / ".venv" / "bin" / "pyright-langserver")
    cli = _touch_executable(project / ".venv" / "bin" / "pyright")
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
    ls = _touch_executable(project / "node_modules" / ".bin" / "pyright-langserver")
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
