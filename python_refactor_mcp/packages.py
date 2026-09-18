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


def ensure_package(source_root: str | Path, dotted_package: str) -> Path:
    root = Path(source_root)
    current = root
    if dotted_package:
        for part in dotted_package.split("."):
            current = current / part
            current.mkdir(parents=True, exist_ok=True)
            init_file = current / "__init__.py"
            if not init_file.exists():
                init_file.write_text("", encoding="utf-8")
    return current
