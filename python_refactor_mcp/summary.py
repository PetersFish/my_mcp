from __future__ import annotations

from python_refactor_mcp.models import Operation, RefactorResult, ResultStatus

CHANGED_FILES_LIMIT = 80
LEFTOVER_SAMPLES_LIMIT = 20


def compact_result(
    *,
    operation: Operation,
    dry_run: bool,
    source: str | None = None,
    target: str | None = None,
    status: ResultStatus = "success",
    changed_files: list[str] | None = None,
    created_files: list[str] | None = None,
    deleted_files: list[str] | None = None,
    leftover_samples: list[str] | None = None,
    remaining_old_references: int | None = None,
    conflicts: list[str] | None = None,
    git_dirty_before: bool = False,
    verification: dict[str, str] | None = None,
    error: str | None = None,
) -> RefactorResult:
    changed = list(changed_files or [])
    created = list(created_files or [])
    deleted = list(deleted_files or [])
    leftovers = list(leftover_samples or [])
    truncated = len(changed) > CHANGED_FILES_LIMIT
    listed = changed[:CHANGED_FILES_LIMIT]
    leftover_listed = leftovers[:LEFTOVER_SAMPLES_LIMIT]
    remaining = (
        remaining_old_references
        if remaining_old_references is not None
        else len(leftovers)
    )
    return RefactorResult(
        status=status,
        operation=operation,
        dry_run=dry_run,
        source=source,
        target=target,
        files_changed=len(changed),
        files_created=len(created),
        files_deleted=len(deleted),
        changed_files=listed,
        changed_files_truncated=truncated,
        remaining_old_references=remaining,
        leftover_samples=leftover_listed,
        conflicts=list(conflicts or []),
        git_dirty_before=git_dirty_before,
        verification=dict(verification or {}),
        error=error,
    )
