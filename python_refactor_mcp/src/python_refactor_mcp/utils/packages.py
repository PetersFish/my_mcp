from __future__ import annotations

from pathlib import Path


def resolve_source_root(
    project_root: str | Path,
    source_root: str | None,
    dotted_module: str | None = None,
) -> Path:
    root = Path(project_root).resolve()
    if source_root:
        return (root / source_root).resolve()

    candidates = [root, root / "src"]
    if dotted_module:
        for candidate in candidates:
            if module_file(candidate, dotted_module) is not None:
                return candidate.resolve()
    return root


def module_file(source_root: str | Path, dotted: str) -> Path | None:
    root = Path(source_root)
    rel = Path(*dotted.split("."))
    py_file = root / f"{rel}.py"
    if py_file.is_file():
        return py_file
    init_file = root / rel / "__init__.py"
    if init_file.is_file():
        return init_file
    return None


def occupied_path(source_root: str | Path, dotted: str) -> Path | None:
    """Return any filesystem path occupying ``dotted``, importable or not.

    ``module_file`` only recognises importable modules. A directory left behind
    without ``__init__.py`` still collides on move: ``git restore`` keeps such a
    directory alive whenever ``__pycache__`` survives inside it, and moving into
    it nests the source one level deeper instead of replacing it.
    """
    root = Path(source_root)
    rel = Path(*dotted.split("."))
    py_file = root / f"{rel}.py"
    if py_file.is_file():
        return py_file
    directory = root / rel
    if directory.is_dir():
        return directory
    return None


def ensure_package(
    source_root: str | Path,
    dotted_package: str,
    created: list[Path] | None = None,
) -> Path:
    """Create ``dotted_package`` as a package, recording new paths in ``created``.

    Callers pass ``created`` so a dry run can undo what it had to materialise for
    Rope to resolve destination resources.
    """
    root = Path(source_root)
    current = root
    if dotted_package:
        for part in dotted_package.split("."):
            current = current / part
            if not current.exists():
                current.mkdir(parents=True, exist_ok=True)
                if created is not None:
                    created.append(current)
            init_file = current / "__init__.py"
            if not init_file.exists():
                init_file.write_text("", encoding="utf-8")
                if created is not None:
                    created.append(init_file)
    return current


def remove_created_paths(created: list[Path]) -> None:
    for path in reversed(created):
        try:
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        except OSError:
            continue


_EMPTY_PACKAGE_IGNORE = {"__pycache__", ".DS_Store"}


def find_empty_packages(
    project_root: str | Path,
    source_dotted: str,
    source_root: str | Path,
) -> list[str]:
    """List source-side packages left holding only an empty ``__init__.py``.

    Checks the moved/renamed module's own directory (it survives when the source
    was itself a package), then walks its parents up toward ``source_root``,
    stopping at the first parent that still has content. Reports only; never
    deletes. Packages created on the destination side are not included.
    """
    project = Path(project_root).resolve()
    src_root = Path(source_root).resolve()
    parts = [part for part in source_dotted.split(".") if part]
    if not parts:
        return []

    found: list[str] = []
    own_dir = src_root.joinpath(*parts)
    if _is_empty_package(own_dir):
        found.append(_relative_to(own_dir, project))

    for depth in range(len(parts) - 1, 0, -1):
        pkg_dir = src_root.joinpath(*parts[:depth])
        if not _is_empty_package(pkg_dir):
            break
        found.append(_relative_to(pkg_dir, project))
    return found


def _relative_to(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_empty_package(pkg_dir: Path) -> bool:
    if not pkg_dir.is_dir():
        return False
    entries = [path for path in pkg_dir.iterdir() if path.name not in _EMPTY_PACKAGE_IGNORE]
    if len(entries) != 1:
        return False
    init = entries[0]
    if init.name != "__init__.py" or not init.is_file():
        return False
    try:
        return init.read_text(encoding="utf-8").strip() == ""
    except (OSError, UnicodeDecodeError):
        return False
