from __future__ import annotations

import os
from pathlib import Path


def unix_bin(root: Path, name: str) -> Path:
    return root / "bin" / name


def windows_bin(root: Path, name: str, *, suffix: str = ".exe") -> Path:
    return root / "Scripts" / f"{name}{suffix}"


def language_server_argv(
    language_server: Path,
    *extra: str,
    os_name: str | None = None,
    comspec: str | None = None,
) -> list[str]:
    """Build argv for spawning pyright-langserver (Windows-safe for ``.cmd``)."""
    extras = list(extra) if extra else ["--stdio"]
    path = Path(language_server)
    platform = os_name if os_name is not None else os.name
    if platform == "nt" and path.suffix.lower() == ".cmd":
        shell = comspec or os.environ.get("ComSpec") or "cmd.exe"
        return [shell, "/c", str(path), *extras]
    return [str(path), *extras]
