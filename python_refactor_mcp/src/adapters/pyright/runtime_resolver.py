from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from python_refactor_mcp.adapters.pyright.runtime import PyrightRuntime
from python_refactor_mcp.config import load_project_config
from python_refactor_mcp.models.errors import RefactorError


class PyrightRuntimeResolver:
    def resolve(self, project_root: str | Path) -> PyrightRuntime:
        root = Path(project_root).resolve()
        explicit = self._explicit(root)
        if explicit is not None:
            return explicit
        project = self._project(root)
        if project is not None:
            return project
        fallback = self._mcp_fallback()
        if fallback is not None:
            return fallback
        raise RefactorError("PYRIGHT_NOT_FOUND", "No pyright-langserver executable was found")

    def _explicit(self, root: Path) -> PyrightRuntime | None:
        config = load_project_config(root).pyright
        if config.language_server is None:
            return None
        language_server = config.language_server.expanduser().resolve()
        if not language_server.exists():
            raise RefactorError(
                "PYRIGHT_NOT_FOUND",
                f"configured language_server does not exist: {language_server}",
            )
        cli = config.cli.expanduser().resolve() if config.cli else None
        type_server = config.type_server.expanduser().resolve() if config.type_server else None
        return PyrightRuntime(
            cli=cli if cli and cli.exists() else None,
            language_server=language_server,
            type_server=type_server if type_server and type_server.exists() else None,
            version=_version(cli or language_server),
            source="explicit",
        )

    def _project(self, root: Path) -> PyrightRuntime | None:
        candidates: list[tuple[Path, Path | None]] = []
        if os.name == "nt":
            venv_bin = root / ".venv" / "Scripts"
            candidates.append(
                (venv_bin / "pyright-langserver.exe", venv_bin / "pyright.exe")
            )
        else:
            venv_bin = root / ".venv" / "bin"
            candidates.append((venv_bin / "pyright-langserver", venv_bin / "pyright"))
        node_bin = root / "node_modules" / ".bin"
        candidates.append((node_bin / "pyright-langserver", node_bin / "pyright"))
        if os.name == "nt":
            candidates.append(
                (node_bin / "pyright-langserver.cmd", node_bin / "pyright.cmd")
            )
        for language_server, cli in candidates:
            if language_server.is_file():
                return PyrightRuntime(
                    cli=cli if cli.is_file() else None,
                    language_server=language_server.resolve(),
                    type_server=None,
                    version=_version(cli if cli.is_file() else language_server),
                    source="project",
                )
        return None

    def _mcp_fallback(self) -> PyrightRuntime | None:
        language_server = _which("pyright-langserver") or _prefix_bin("pyright-langserver")
        if language_server is None:
            return None
        cli = _which("pyright") or _prefix_bin("pyright")
        return PyrightRuntime(
            cli=cli,
            language_server=language_server,
            type_server=None,
            version=_version(cli or language_server),
            source="mcp_fallback",
        )


def _which(name: str) -> Path | None:
    found = shutil.which(name)
    return Path(found).resolve() if found else None


def _prefix_bin(name: str) -> Path | None:
    if os.name == "nt":
        path = Path(sys.prefix) / "Scripts" / f"{name}.exe"
    else:
        path = Path(sys.prefix) / "bin" / name
    return path.resolve() if path.is_file() else None


def _version(executable: Path) -> str:
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    text = (result.stdout or result.stderr).strip()
    return text.splitlines()[0] if text else "unknown"
