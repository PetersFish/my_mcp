from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from rope.base.exceptions import RefactoringError
from rope.base.project import Project
from rope.refactor.move import create_move
from rope.refactor.rename import Rename

from python_refactor_mcp.models import RefactorRequest
from python_refactor_mcp.packages import ensure_package, module_file, resolve_source_root

IGNORED_RESOURCES = [
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
]


class RopeConflictError(Exception):
    def __init__(self, conflicts: list[str]):
        super().__init__("; ".join(conflicts))
        self.conflicts = conflicts


class RopeAdapterError(Exception):
    pass


@dataclass
class PlannedChanges:
    changed_files: list[str] = field(default_factory=list)
    created_files: list[str] = field(default_factory=list)
    deleted_files: list[str] = field(default_factory=list)
    old_needles: list[str] = field(default_factory=list)
    estimated: bool = False


def run_rope(request: RefactorRequest) -> PlannedChanges:
    dotted = _lookup_module(request)
    source_root = resolve_source_root(
        request.project_root,
        request.source_root,
        dotted_module=dotted,
    )
    project_root = Path(request.project_root).resolve()
    project = Project(
        str(project_root),
        ropefolder=None,
        ignored_resources=IGNORED_RESOURCES,
    )
    try:
        project.validate()
        return _dispatch(project, project_root, source_root, request)
    except RopeConflictError:
        raise
    except RefactoringError as exc:
        raise RopeAdapterError(str(exc)) from exc
    finally:
        project.close()


def _lookup_module(request: RefactorRequest) -> str | None:
    if request.operation in {"move_module", "rename_module"}:
        return request.source
    return request.module


def _dispatch(
    project: Project,
    project_root: Path,
    source_root: Path,
    request: RefactorRequest,
) -> PlannedChanges:
    if request.operation == "rename_symbol":
        return _rename_symbol(project, project_root, source_root, request)
    if request.operation == "rename_module":
        return _rename_module(project, project_root, source_root, request)
    if request.operation == "move_symbol":
        return _move_symbol(project, project_root, source_root, request)
    if request.operation == "move_module":
        return _move_module(project, project_root, source_root, request)
    raise RopeAdapterError(f"unsupported operation: {request.operation}")


def _rename_symbol(
    project: Project,
    project_root: Path,
    source_root: Path,
    request: RefactorRequest,
) -> PlannedChanges:
    resource = _module_resource(project, project_root, source_root, request.module or "")
    offset = _unique_symbol_offset(resource.read(), request.symbol or "")
    changes = Rename(project, resource, offset).get_changes(request.new_name or "")
    return _apply_or_preview(
        project,
        changes,
        request.dry_run,
        old_needles=[request.symbol.split(".")[-1] if request.symbol else ""],
    )


def _rename_module(
    project: Project,
    project_root: Path,
    source_root: Path,
    request: RefactorRequest,
) -> PlannedChanges:
    source = request.source or ""
    resource = _module_resource(project, project_root, source_root, source)
    parent, _name = _split_dotted(source)
    target = f"{parent}.{request.new_name}" if parent else (request.new_name or "")
    if module_file(source_root, target) is not None:
        raise RopeConflictError([f"target already exists: {target}"])
    changes = Rename(project, resource, None).get_changes(request.new_name or "")
    needles = [source]
    if "/" not in source:
        needles.append(source.replace(".", "/"))
    return _apply_or_preview(project, changes, request.dry_run, old_needles=needles)


def _move_symbol(
    project: Project,
    project_root: Path,
    source_root: Path,
    request: RefactorRequest,
) -> PlannedChanges:
    resource = _module_resource(project, project_root, source_root, request.module or "")
    offset = _unique_symbol_offset(resource.read(), request.symbol or "")
    dest_path = _ensure_module_file(source_root, request.target or "")
    project.validate()
    dest_resource = _path_resource(project, project_root, dest_path)
    mover = create_move(project, resource, offset)
    changes = mover.get_changes(dest=dest_resource)
    needle = request.symbol.split(".")[-1] if request.symbol else ""
    return _apply_or_preview(project, changes, request.dry_run, old_needles=[needle])


def _move_module(
    project: Project,
    project_root: Path,
    source_root: Path,
    request: RefactorRequest,
) -> PlannedChanges:
    source = request.source or ""
    target = request.target or ""
    if module_file(source_root, target) is not None:
        raise RopeConflictError([f"target already exists: {target}"])
    src_parent, src_name = _split_dotted(source)
    dst_parent, dst_name = _split_dotted(target)
    if dst_parent:
        ensure_package(source_root, dst_parent)
        project.validate()
    source_resource = _module_resource(project, project_root, source_root, source)
    needles = [source, source.replace(".", "/")]

    if src_parent == dst_parent:
        changes = Rename(project, source_resource, None).get_changes(dst_name)
        return _apply_or_preview(project, changes, request.dry_run, old_needles=needles)

    dest_folder = source_root if not dst_parent else ensure_package(source_root, dst_parent)
    dest_resource = _path_resource(project, project_root, dest_folder)
    mover = create_move(project, source_resource)
    move_changes = mover.get_changes(dest=dest_resource)

    if src_name == dst_name:
        return _apply_or_preview(project, move_changes, request.dry_run, old_needles=needles)

    if request.dry_run:
        planned = _summarize_changeset(move_changes)
        final_rel = _rel(project_root, source_root.joinpath(*target.split(".")).with_suffix(".py"))
        old_rel = _rel(project_root, module_file(source_root, source) or source_root)
        planned.created_files = sorted(set(planned.created_files + [final_rel]))
        planned.deleted_files = sorted(set(planned.deleted_files + [old_rel]))
        planned.changed_files = sorted(set(planned.changed_files + [final_rel, old_rel]))
        planned.old_needles = needles
        planned.estimated = True
        return planned

    project.do(move_changes)
    project.validate()
    moved_dotted = f"{dst_parent}.{src_name}" if dst_parent else src_name
    moved_resource = _module_resource(project, project_root, source_root, moved_dotted)
    rename_changes = Rename(project, moved_resource, None).get_changes(dst_name)
    project.do(rename_changes)
    planned = _merge_planned(
        _summarize_changeset(move_changes),
        _summarize_changeset(rename_changes),
    )
    planned.old_needles = needles
    return planned


def _apply_or_preview(project: Project, changes, dry_run: bool, old_needles: list[str]) -> PlannedChanges:
    planned = _summarize_changeset(changes)
    planned.old_needles = [n for n in old_needles if n]
    if not dry_run:
        project.do(changes)
    return planned


def _summarize_changeset(changes) -> PlannedChanges:
    changed: list[str] = []
    created: list[str] = []
    deleted: list[str] = []
    for change in getattr(changes, "changes", []):
        kind = type(change).__name__
        if kind == "ChangeContents" and getattr(change, "resource", None) is not None:
            changed.append(change.resource.path)
        elif kind == "CreateResource" and getattr(change, "resource", None) is not None:
            created.append(change.resource.path)
        elif kind == "RemoveResource" and getattr(change, "resource", None) is not None:
            deleted.append(change.resource.path)
        elif kind == "MoveResource":
            old = change.resource.path if getattr(change, "resource", None) is not None else ""
            new = getattr(change, "new_resource", None)
            if new is not None:
                created.append(new.path)
            else:
                new_loc = getattr(change, "new_name", None) or getattr(change, "new_location", None)
                if new_loc:
                    created.append(str(new_loc))
            if old:
                deleted.append(old)
    if hasattr(changes, "get_changed_resources"):
        for resource in changes.get_changed_resources() or []:
            changed.append(resource.path)
    return PlannedChanges(
        changed_files=_unique(changed + created + deleted),
        created_files=_unique(created),
        deleted_files=_unique(deleted),
    )


def _merge_planned(first: PlannedChanges, second: PlannedChanges) -> PlannedChanges:
    return PlannedChanges(
        changed_files=_unique(first.changed_files + second.changed_files),
        created_files=_unique(first.created_files + second.created_files),
        deleted_files=_unique(first.deleted_files + second.deleted_files),
        old_needles=_unique(first.old_needles + second.old_needles),
    )


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _split_dotted(dotted: str) -> tuple[str, str]:
    if "." not in dotted:
        return "", dotted
    parent, name = dotted.rsplit(".", 1)
    return parent, name


def _module_resource(project: Project, project_root: Path, source_root: Path, dotted: str):
    path = module_file(source_root, dotted)
    if path is None:
        raise RopeAdapterError(f"module not found: {dotted}")
    return _path_resource(project, project_root, path)


def _ensure_module_file(source_root: Path, dotted: str) -> Path:
    existing = module_file(source_root, dotted)
    if existing is not None:
        return existing
    parent, name = _split_dotted(dotted)
    if parent:
        ensure_package(source_root, parent)
        path = source_root / Path(*parent.split(".")) / f"{name}.py"
    else:
        path = source_root / f"{name}.py"
    if not path.exists():
        path.write_text("", encoding="utf-8")
    return path


def _path_resource(project: Project, project_root: Path, path: Path):
    rel = path.resolve().relative_to(project_root).as_posix()
    if rel == ".":
        return project.root
    return project.get_resource(rel)


def _rel(project_root: Path, path: Path) -> str:
    return path.resolve().relative_to(project_root).as_posix()


def _unique_symbol_offset(source: str, symbol: str) -> int:
    offsets = definition_offsets(source, symbol)
    if not offsets:
        raise RopeConflictError([f"symbol not found: {symbol}"])
    if len(offsets) > 1:
        raise RopeConflictError([f"symbol is not unique: {symbol}"])
    return offsets[0]


def definition_offsets(source: str, symbol: str) -> list[int]:
    tree = ast.parse(source)
    if "." in symbol:
        class_name, method_name = symbol.split(".", 1)
        offsets: list[int] = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if (
                        isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and item.name == method_name
                    ):
                        offsets.append(_ident_offset(source, item.lineno, item.col_offset, item.name))
        return offsets

    offsets = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == symbol:
            offsets.append(_ident_offset(source, node.lineno, node.col_offset, node.name))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
            offsets.append(_ident_offset(source, node.lineno, node.col_offset, node.name))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == symbol:
                    offsets.append(_line_col_offset(source, target.lineno, target.col_offset))
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == symbol
        ):
            offsets.append(_line_col_offset(source, node.target.lineno, node.target.col_offset))
    return offsets


def _line_col_offset(source: str, lineno: int, col: int) -> int:
    lines = source.splitlines(keepends=True)
    return sum(len(line) for line in lines[: lineno - 1]) + col


def _ident_offset(source: str, lineno: int, col: int, name: str) -> int:
    lines = source.splitlines(keepends=True)
    line = lines[lineno - 1]
    idx = line.find(name, col)
    if idx < 0:
        raise RopeAdapterError(f"could not locate identifier {name}")
    return sum(len(item) for item in lines[: lineno - 1]) + idx
