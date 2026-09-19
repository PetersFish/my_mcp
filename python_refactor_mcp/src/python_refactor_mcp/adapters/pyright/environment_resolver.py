from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from python_refactor_mcp.config import load_project_config


@dataclass(frozen=True)
class PythonEnvironment:
    executable: Path | None
    source: Literal["explicit", "project_venv", "active", "current", "unresolved"]


class PythonEnvironmentResolver:
    def resolve(self, project_root: str | Path) -> PythonEnvironment:
        root = Path(project_root).resolve()
        explicit = load_project_config(root).python.executable
        if explicit is not None:
            path = explicit.expanduser().resolve()
            if path.exists():
                return PythonEnvironment(executable=path, source="explicit")
        venv_python = _venv_python(root)
        if venv_python is not None:
            return PythonEnvironment(executable=venv_python, source="project_venv")
        current = Path(sys.executable).resolve()
        if _is_mcp_interpreter(current):
            return PythonEnvironment(executable=None, source="unresolved")
        return PythonEnvironment(executable=current, source="current")


def _venv_python(root: Path) -> Path | None:
    if os.name == "nt":
        candidates = [
            root / ".venv" / "Scripts" / "python.exe",
            root / ".venv" / "Scripts" / "python",
        ]
    else:
        candidates = [
            root / ".venv" / "bin" / "python",
            root / ".venv" / "Scripts" / "python.exe",
        ]
    for path in candidates:
        if path.is_file():
            return path.resolve()
    return None


def _is_mcp_interpreter(executable: Path) -> bool:
    try:
        return executable.resolve().is_relative_to(Path(sys.prefix).resolve())
    except (ValueError, OSError):
        return str(executable).startswith(sys.prefix)
