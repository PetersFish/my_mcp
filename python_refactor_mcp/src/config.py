from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PyrightConfig:
    language_server: Path | None = None
    cli: Path | None = None
    type_server: Path | None = None


@dataclass(frozen=True)
class PythonConfig:
    executable: Path | None = None


@dataclass(frozen=True)
class RefactorMcpConfig:
    pyright: PyrightConfig
    python: PythonConfig


def load_project_config(project_root: Path) -> RefactorMcpConfig:
    pyproject = project_root / "pyproject.toml"
    if not pyproject.is_file():
        return RefactorMcpConfig(pyright=PyrightConfig(), python=PythonConfig())
    with pyproject.open("rb") as handle:
        data = tomllib.load(handle)
    tool = data.get("tool", {}).get("refactor_mcp", {})
    pyright_raw = tool.get("pyright", {})
    python_raw = tool.get("python", {})
    return RefactorMcpConfig(
        pyright=PyrightConfig(
            language_server=_optional_path(pyright_raw.get("language_server")),
            cli=_optional_path(pyright_raw.get("cli")),
            type_server=_optional_path(pyright_raw.get("type_server")),
        ),
        python=PythonConfig(executable=_optional_path(python_raw.get("executable"))),
    )


def _optional_path(value: object) -> Path | None:
    if not value:
        return None
    return Path(str(value))
