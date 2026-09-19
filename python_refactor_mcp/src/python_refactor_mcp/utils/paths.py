from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname


def uri_to_path(uri: str) -> Path:
    """Convert an LSP ``file://`` URI to a local ``Path`` (Windows-safe)."""
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        # url2pathname turns "/C:/Users/..." into "C:\\Users\\..." on Windows.
        # On POSIX it may leave a leading slash before the drive letter; strip it.
        raw = url2pathname(unquote(parsed.path))
        if len(raw) >= 3 and raw[0] in "/\\" and raw[2] == ":":
            raw = raw[1:]
        return Path(raw)
    if parsed.path:
        return Path(unquote(parsed.path))
    raise ValueError(f"unsupported URI: {uri}")


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
