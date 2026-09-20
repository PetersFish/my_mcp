from __future__ import annotations

from pathlib import Path

from python_refactor_mcp.models.common import Operation, ResultStatus
from python_refactor_mcp.models.results import RefactorResult

CHANGED_FILES_LIMIT = 80
LEFTOVER_SAMPLES_LIMIT = 20


def leftover_replace_pair(
    operation: Operation,
    *,
    source: str | None = None,
    target: str | None = None,
    module: str | None = None,
    symbol: str | None = None,
    new_name: str | None = None,
) -> tuple[str | None, str | None]:
    if operation == "move_module":
        return source, target
    if operation == "rename_module":
        if not source:
            return source, new_name
        if "." in source:
            parent, _name = source.rsplit(".", 1)
            replacement = f"{parent}.{new_name}" if new_name else parent
        else:
            replacement = new_name
        return source, replacement
    if operation == "rename_symbol":
        if not symbol:
            return None, new_name
        if "." in symbol:
            owner, _leaf = symbol.split(".", 1)
            return symbol, (f"{owner}.{new_name}" if new_name else owner)
        return symbol, new_name
    if operation == "move_symbol":
        leaf = (symbol or "").split(".")[-1]
        from_ref = f"{module}:{symbol}" if module and symbol else module
        to_ref = f"{target}:{leaf}" if target and leaf else target
        return from_ref, to_ref
    return None, None


def needle_is_dotted_path(operation: Operation) -> bool:
    """Whether leftover_replace_from is a dotted module path safe to search for.

    Symbol operations reduce to a bare identifier such as ``save``, which is far
    too common to search for across a repository.
    """
    return operation in {"move_module", "rename_module"}


def next_action_for(
    *,
    operation: Operation,
    status: ResultStatus,
    dry_run: bool,
    residual_checked: bool,
    leftover_samples: list[str],
    remaining_old_references: int,
    empty_packages: list[str],
    import_issues: list[str],
    leftover_replace_from: str | None,
    leftover_replace_to: str | None,
) -> str:
    if status != "success":
        return "Refactor did not succeed. Do not grep or glob for leftovers."

    empty_note = ""
    if empty_packages:
        empty_note = " empty_packages are local keep-or-delete decisions, not a search task."

    pair = ""
    if leftover_replace_from and leftover_replace_to:
        pair = f" ({leftover_replace_from} -> {leftover_replace_to})"

    if dry_run:
        return (
            "Dry run: nothing was written and residual was not scanned, so leftovers "
            "are unknown. Re-run without dry_run to get leftover_samples. "
            f"Do not grep or glob.{empty_note}"
        ).strip()

    if import_issues:
        return (
            f"Rope left {len(import_issues)} import issue(s). Fix each file:line, "
            "then run pyright/ruff."
        )

    if not residual_checked:
        return (
            "residual was not scanned, so leftovers are unknown. Re-run with "
            'verify=["residual"] instead of searching the repo yourself.'
            f"{empty_note}"
        ).strip()

    if remaining_old_references > LEFTOVER_SAMPLES_LIMIT:
        if needle_is_dotted_path(operation):
            return (
                "leftover_samples is truncated; rg leftover_replace_from exactly. "
                f"Do not glob. Edit those hits{pair}.{empty_note}"
            ).strip()
        return (
            "leftover_samples is truncated and leftover_replace_from is a bare "
            "identifier, so do not grep it repo-wide. Edit the listed hits"
            f"{pair}, then let Ruff/Pyright find the rest.{empty_note}"
        ).strip()

    if leftover_samples or remaining_old_references:
        return (
            f"Edit only leftover_samples in place{pair}. Do not grep or glob.{empty_note}"
        ).strip()

    verify = " Run verification if not already ok."
    return f"No leftovers. Do not search.{empty_note}{verify}".strip()


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
    leftover_replace_from: str | None = None,
    leftover_replace_to: str | None = None,
    empty_packages: list[str] | None = None,
    import_issues: list[str] | None = None,
    conflicts: list[str] | None = None,
    git_dirty_before: bool = False,
    verification: dict[str, str] | None = None,
    error: str | None = None,
    summary: str | None = None,
    metrics: dict[str, int] | None = None,
    warnings: list[str] | None = None,
    details: dict[str, object] | None = None,
    semantic_status: str | None = None,
) -> RefactorResult:
    changed = list(changed_files or [])
    created = list(created_files or [])
    deleted = list(deleted_files or [])
    leftovers = list(leftover_samples or [])
    empty = list(empty_packages or [])
    truncated = len(changed) > CHANGED_FILES_LIMIT
    listed = changed[:CHANGED_FILES_LIMIT]
    leftover_listed = leftovers[:LEFTOVER_SAMPLES_LIMIT]
    remaining = (
        remaining_old_references
        if remaining_old_references is not None
        else len(leftovers)
    )
    checks = dict(verification or {})
    next_action = next_action_for(
        operation=operation,
        status=status,
        dry_run=dry_run,
        residual_checked=checks.get("residual") in {"ok", "failed"},
        leftover_samples=leftover_listed,
        remaining_old_references=remaining,
        empty_packages=empty,
        import_issues=list(import_issues or []),
        leftover_replace_from=leftover_replace_from,
        leftover_replace_to=leftover_replace_to,
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
        leftover_replace_from=leftover_replace_from,
        leftover_replace_to=leftover_replace_to,
        next_action=next_action,
        empty_packages=empty,
        conflicts=list(conflicts or []),
        git_dirty_before=git_dirty_before,
        verification=checks,
        error=error,
        summary=summary,
        metrics=dict(metrics or {}),
        warnings=list(warnings or []),
        import_issues=list(import_issues or []),
        details=dict(details or {}),
        semantic_status=semantic_status,
    )


MAX_REFERENCES_DEFAULT = 50


def format_location(project_root: Path, path: Path, line: int, character: int) -> str:
    try:
        rel = path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        rel = path.as_posix()
    return f"{rel}:{line + 1}:{character + 1}"


def truncate_items(items: list[str], limit: int) -> tuple[list[str], bool]:
    if len(items) <= limit:
        return items, False
    return items[:limit], True
