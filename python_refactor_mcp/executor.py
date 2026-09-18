from __future__ import annotations

from python_refactor_mcp.gitutil import snapshot_porcelain
from python_refactor_mcp.models import RefactorRequest, RefactorResult
from python_refactor_mcp.rope_adapter import RopeAdapterError, RopeConflictError, run_rope
from python_refactor_mcp.summary import compact_result
from python_refactor_mcp.verifier import run_verification


def run_refactor(request: RefactorRequest) -> RefactorResult:
    dirty = snapshot_porcelain(request.project_root)
    git_dirty_before = bool(dirty)
    target = _result_target(request)
    try:
        planned = run_rope(request)
    except RopeConflictError as exc:
        return compact_result(
            operation=request.operation,
            dry_run=request.dry_run,
            source=_result_source(request),
            target=target,
            status="conflict",
            conflicts=exc.conflicts,
            git_dirty_before=git_dirty_before,
            error="; ".join(exc.conflicts),
        )
    except RopeAdapterError as exc:
        after = snapshot_porcelain(request.project_root)
        changed = _new_porcelain_paths(dirty, after)
        return compact_result(
            operation=request.operation,
            dry_run=request.dry_run,
            source=_result_source(request),
            target=target,
            status="error",
            changed_files=changed,
            git_dirty_before=git_dirty_before,
            error=_short_error(str(exc)),
        )
    except Exception as exc:  # pragma: no cover - unexpected engine failure
        after = snapshot_porcelain(request.project_root)
        changed = _new_porcelain_paths(dirty, after)
        return compact_result(
            operation=request.operation,
            dry_run=request.dry_run,
            source=_result_source(request),
            target=target,
            status="error",
            changed_files=changed,
            git_dirty_before=git_dirty_before,
            error=_short_error(str(exc)),
        )

    verification, remaining, samples = run_verification(
        request.project_root,
        changed_files=planned.changed_files,
        needles=planned.old_needles,
        verify=request.verify,
        pytest_args=request.pytest_args,
        dry_run=request.dry_run,
    )
    return compact_result(
        operation=request.operation,
        dry_run=request.dry_run,
        source=_result_source(request),
        target=target,
        status="success",
        changed_files=planned.changed_files,
        created_files=planned.created_files,
        deleted_files=planned.deleted_files,
        leftover_samples=samples,
        remaining_old_references=remaining,
        git_dirty_before=git_dirty_before,
        verification=verification,
    )


def _result_source(request: RefactorRequest) -> str | None:
    if request.operation in {"move_module", "rename_module"}:
        return request.source
    if request.module and request.symbol:
        return f"{request.module}:{request.symbol}"
    return request.module


def _result_target(request: RefactorRequest) -> str | None:
    if request.operation == "rename_module":
        return request.new_name
    if request.operation == "rename_symbol":
        return request.new_name
    return request.target


def _short_error(message: str) -> str:
    first = message.strip().splitlines()[0] if message.strip() else "refactor failed"
    return first[:300]


def _new_porcelain_paths(before: list[str], after: list[str]) -> list[str]:
    before_set = set(before)
    added = []
    for line in after:
        if line not in before_set:
            path = line[3:] if len(line) > 3 else line
            added.append(path.strip())
    return added
