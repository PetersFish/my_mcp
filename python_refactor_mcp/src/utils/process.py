from __future__ import annotations

from pathlib import Path


def unix_bin(root: Path, name: str) -> Path:
    return root / "bin" / name


def windows_bin(root: Path, name: str, *, suffix: str = ".exe") -> Path:
    return root / "Scripts" / f"{name}{suffix}"
