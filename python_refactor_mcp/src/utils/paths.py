from __future__ import annotations

from pathlib import Path


def resolve_project_root(project_root: str | Path) -> Path:
    path = Path(project_root).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"project_root not found: {project_root}")
    if not path.is_dir():
        raise NotADirectoryError(f"project_root is not a directory: {project_root}")
    return path


def ensure_inside_project(project_root: Path, path: str | Path) -> Path:
    root = project_root.resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes project_root: {path}") from exc
    return resolved
