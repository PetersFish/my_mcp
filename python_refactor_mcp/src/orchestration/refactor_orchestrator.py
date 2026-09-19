from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Protocol

from python_refactor_mcp.adapters.pyright.process_manager import default_manager
from python_refactor_mcp.adapters.rope_adapter import RopeAdapterError, RopeConflictError
from python_refactor_mcp.config import load_project_config
from python_refactor_mcp.models import RefactorRequest, RefactorResult
from python_refactor_mcp.models.common import SemanticMode, SourcePosition
from python_refactor_mcp.models.errors import RefactorError
from python_refactor_mcp.orchestration.operation_context import OperationContext
from python_refactor_mcp.services.refactor_service import run_rope_refactor
from python_refactor_mcp.services.semantic_service import SemanticService
from python_refactor_mcp.services.verification_service import run_verification
from python_refactor_mcp.utils.gitutil import snapshot_porcelain
from python_refactor_mcp.utils.packages import find_empty_packages, resolve_source_root
from python_refactor_mcp.utils.summaries import compact_result, leftover_replace_pair

_SYMBOL_OPS = frozenset({"rename_symbol", "move_symbol"})
_MODULE_OPS = frozenset({"rename_module", "move_module"})
_PYRIGHT_DOWN = frozenset(
    {
        "PYRIGHT_UNAVAILABLE",
        "PYRIGHT_NOT_FOUND",
        "PYRIGHT_TIMEOUT",
        "LSP_PROTOCOL_ERROR",
    }
)
_HARD_PREFLIGHT = frozenset(
    {
        "SOURCE_NOT_FOUND",
        "SYMBOL_NOT_FOUND",
        "AMBIGUOUS_SYMBOL",
        "TARGET_CONFLICT",
    }
)
_MAX_DIAGNOSTIC_WARNINGS = 50


class _SemanticServiceLike(Protocol):
    async def resolve_symbol(self, *args: Any, **kwargs: Any) -> SourcePosition: ...

    async def references(self, *args: Any, **kwargs: Any) -> Any: ...

    async def module_defines_symbol(self, *args: Any, **kwargs: Any) -> bool: ...

    async def refresh(self, *args: Any, **kwargs: Any) -> None: ...

    async def diagnostics(self, *args: Any, **kwargs: Any) -> Any: ...


def run_refactor(
    request: RefactorRequest,
    *,
    semantic_service: _SemanticServiceLike | None = None,
) -> RefactorResult:
    started = time.perf_counter()
    dirty = snapshot_porcelain(request.project_root)
    git_dirty_before = bool(dirty)
    target = _result_target(request)
    replace_from, replace_to = leftover_replace_pair(
        request.operation,
        source=request.source,
        target=request.target,
        module=request.module,
        symbol=request.symbol,
        new_name=request.new_name,
    )
    source_root = resolve_source_root(
        request.project_root,
        request.source_root,
        dotted_module=_lookup_module(request),
    )
    root = Path(request.project_root).resolve()
    semantic_mode = _resolve_semantic_mode(request, root)
    service = semantic_service or SemanticService()
    manager = default_manager()
    ctx = OperationContext(
        operation_id=f"{request.operation}:{replace_from}->{replace_to}",
        project_root=root,
        operation_type=request.operation,
    )
    metrics: dict[str, int] = {}
    warnings: list[str] = []
    details: dict[str, object] = {}
    semantic_status: str | None = None

    def _finalize(result: RefactorResult) -> RefactorResult:
        duration_ms = int((time.perf_counter() - started) * 1000)
        merged = dict(result.metrics)
        merged.setdefault("duration_ms", duration_ms)
        payload = result.model_dump_json()
        merged["result_chars"] = len(payload)
        result.metrics = merged
        # Recompute after embedding result_chars would recurse; approximate once.
        result.metrics["result_chars"] = len(result.model_dump_json())
        return result

    if request.operation in _SYMBOL_OPS:
        preflight = _run_symbol_preflight(
            request,
            service=service,
            manager=manager,
            semantic_mode=semantic_mode,
            metrics=metrics,
            details=details,
        )
        if preflight is not None:
            return _finalize(preflight)
        semantic_status = str(details.pop("_preflight_status", "ok"))
        ctx.semantic_status = semantic_status
    else:
        semantic_status = None

    try:
        planned = run_rope_refactor(request)
    except RopeConflictError as exc:
        return _finalize(
            compact_result(
                operation=request.operation,
                dry_run=request.dry_run,
                source=_result_source(request),
                target=target,
                status="conflict",
                leftover_replace_from=replace_from,
                leftover_replace_to=replace_to,
                conflicts=exc.conflicts,
                git_dirty_before=git_dirty_before,
                error="; ".join(exc.conflicts),
                metrics=metrics,
                warnings=warnings,
                details=details,
                semantic_status=semantic_status,
            )
        )
    except RopeAdapterError as exc:
        after = snapshot_porcelain(request.project_root)
        changed = _new_porcelain_paths(dirty, after)
        return _finalize(
            compact_result(
                operation=request.operation,
                dry_run=request.dry_run,
                source=_result_source(request),
                target=target,
                status="error",
                changed_files=changed,
                leftover_replace_from=replace_from,
                leftover_replace_to=replace_to,
                git_dirty_before=git_dirty_before,
                error=_short_error(str(exc)),
                metrics=metrics,
                warnings=warnings,
                details=details,
                semantic_status=semantic_status,
            )
        )
    except Exception as exc:  # pragma: no cover - unexpected engine failure
        after = snapshot_porcelain(request.project_root)
        changed = _new_porcelain_paths(dirty, after)
        return _finalize(
            compact_result(
                operation=request.operation,
                dry_run=request.dry_run,
                source=_result_source(request),
                target=target,
                status="error",
                changed_files=changed,
                leftover_replace_from=replace_from,
                leftover_replace_to=replace_to,
                git_dirty_before=git_dirty_before,
                error=_short_error(str(exc)),
                metrics=metrics,
                warnings=warnings,
                details=details,
                semantic_status=semantic_status,
            )
        )

    ctx.changed_files = [root / path for path in planned.changed_files]
    ctx.created_files = [root / path for path in planned.created_files]
    ctx.deleted_files = [root / path for path in planned.deleted_files]
    metrics["files_changed"] = len(planned.changed_files)

    if not request.dry_run:
        refresh_error = _refresh_and_validate(
            request,
            service=service,
            manager=manager,
            semantic_mode=semantic_mode,
            created=ctx.created_files,
            changed=ctx.changed_files,
            deleted=ctx.deleted_files,
            warnings=warnings,
            details=details,
            ctx=ctx,
        )
        if refresh_error is not None:
            return _finalize(
                compact_result(
                    operation=request.operation,
                    dry_run=request.dry_run,
                    source=_result_source(request),
                    target=target,
                    status="error",
                    changed_files=planned.changed_files,
                    created_files=planned.created_files,
                    deleted_files=planned.deleted_files,
                    leftover_replace_from=replace_from,
                    leftover_replace_to=replace_to,
                    git_dirty_before=git_dirty_before,
                    error=refresh_error.message,
                    metrics=metrics,
                    warnings=warnings,
                    details={**details, "code": refresh_error.code},
                    semantic_status=ctx.semantic_status if ctx.semantic_status != "uninitialized" else semantic_status,
                    summary=_summary(request),
                )
            )
        if ctx.semantic_status not in {"uninitialized", "unavailable"}:
            semantic_status = ctx.semantic_status
        elif ctx.semantic_status == "unavailable":
            semantic_status = "unavailable"
        elif semantic_status is None and details.get("semantic_backend"):
            semantic_status = "ok"

    def _diagnostics_runner(diag_root: Path, changed: list[str]) -> str:
        try:
            for rel in changed:
                if not rel.endswith(".py"):
                    continue
                path = diag_root / rel
                if not path.is_file():
                    continue
                diags = manager.runner.run(service.diagnostics(diag_root, path))
                items = diags if isinstance(diags, list) else []
                for item in items:
                    severity = item.get("severity") if isinstance(item, dict) else getattr(item, "severity", None)
                    if severity in (1, "error", "Error"):
                        return "failed"
            return "ok"
        except Exception:
            return "skipped"

    verification, remaining, samples = run_verification(
        request.project_root,
        changed_files=planned.changed_files,
        needles=planned.old_needles,
        verify=request.verify,
        verification_mode=request.verification_mode,
        pytest_args=request.pytest_args,
        dry_run=request.dry_run,
        diagnostics_runner=_diagnostics_runner,
    )
    empty: list[str] = []
    if (
        not request.dry_run
        and request.operation in _MODULE_OPS
        and request.source
    ):
        empty = find_empty_packages(
            request.project_root,
            request.source,
            source_root,
        )
    return _finalize(
        compact_result(
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
            leftover_replace_from=replace_from,
            leftover_replace_to=replace_to,
            empty_packages=empty,
            git_dirty_before=git_dirty_before,
            verification=verification,
            summary=_summary(request),
            metrics=metrics,
            warnings=warnings,
            details=details,
            semantic_status=semantic_status,
        )
    )


def _resolve_semantic_mode(request: RefactorRequest, root: Path) -> SemanticMode:
    if request.semantic_mode is not None:
        return request.semantic_mode
    return load_project_config(root).semantic.mode


def _run_symbol_preflight(
    request: RefactorRequest,
    *,
    service: _SemanticServiceLike,
    manager: Any,
    semantic_mode: SemanticMode,
    metrics: dict[str, int],
    details: dict[str, object],
) -> RefactorResult | None:
    assert request.module and request.symbol
    try:
        position = manager.runner.run(
            service.resolve_symbol(
                request.project_root,
                module=request.module,
                symbol=request.symbol,
                source_root=request.source_root,
            )
        )
        refs = manager.runner.run(service.references(Path(request.project_root), position))
        metrics["semantic_references_before"] = int(getattr(refs, "count", 0) or 0)
        if request.operation == "move_symbol" and request.target:
            leaf = request.symbol.split(".")[-1]
            exists = manager.runner.run(
                service.module_defines_symbol(
                    request.project_root,
                    module=request.target,
                    symbol=leaf,
                    source_root=request.source_root,
                )
            )
            if exists:
                raise RefactorError(
                    "TARGET_CONFLICT",
                    f"target module already defines {leaf}",
                )
        _attach_runtime_details(manager, Path(request.project_root), details)
        details["_preflight_status"] = "ok"
        return None
    except RefactorError as exc:
        if exc.code == "TARGET_CONFLICT":
            replace_from, replace_to = leftover_replace_pair(
                request.operation,
                source=request.source,
                target=request.target,
                module=request.module,
                symbol=request.symbol,
                new_name=request.new_name,
            )
            return compact_result(
                operation=request.operation,
                dry_run=request.dry_run,
                source=_result_source(request),
                target=_result_target(request),
                status="conflict",
                leftover_replace_from=replace_from,
                leftover_replace_to=replace_to,
                conflicts=[exc.message],
                error=exc.message,
                details={"code": exc.code, **details},
                semantic_status="ok",
                metrics=metrics,
            )
        if exc.code in _HARD_PREFLIGHT:
            return _semantic_error_result(request, exc, metrics, details, semantic_status=None)
        if exc.code in _PYRIGHT_DOWN:
            if semantic_mode == "required":
                return _semantic_error_result(
                    request, exc, metrics, details, semantic_status="unavailable"
                )
            details["_preflight_status"] = "unavailable"
            details["code"] = exc.code
            return None
        if semantic_mode == "required":
            return _semantic_error_result(
                request, exc, metrics, details, semantic_status="unavailable"
            )
        details["_preflight_status"] = "unavailable"
        details["code"] = exc.code
        return None
    except Exception as exc:
        wrapped = RefactorError("PYRIGHT_UNAVAILABLE", _short_error(str(exc)))
        if semantic_mode == "required":
            return _semantic_error_result(
                request, wrapped, metrics, details, semantic_status="unavailable"
            )
        details["_preflight_status"] = "unavailable"
        details["code"] = wrapped.code
        return None


def _semantic_error_result(
    request: RefactorRequest,
    exc: RefactorError,
    metrics: dict[str, int],
    details: dict[str, object],
    *,
    semantic_status: str | None,
) -> RefactorResult:
    replace_from, replace_to = leftover_replace_pair(
        request.operation,
        source=request.source,
        target=request.target,
        module=request.module,
        symbol=request.symbol,
        new_name=request.new_name,
    )
    return compact_result(
        operation=request.operation,
        dry_run=request.dry_run,
        source=_result_source(request),
        target=_result_target(request),
        status="error",
        leftover_replace_from=replace_from,
        leftover_replace_to=replace_to,
        error=exc.message,
        metrics=metrics,
        details={"code": exc.code, **details},
        semantic_status=semantic_status,
    )


def _refresh_and_validate(
    request: RefactorRequest,
    *,
    service: _SemanticServiceLike,
    manager: Any,
    semantic_mode: SemanticMode,
    created: list[Path],
    changed: list[Path],
    deleted: list[Path],
    warnings: list[str],
    details: dict[str, object],
    ctx: OperationContext,
) -> RefactorError | None:
    root = Path(request.project_root).resolve()
    try:
        manager.runner.run(
            service.refresh(
                root,
                created=created,
                changed=changed,
                deleted=deleted,
            )
        )
        _attach_runtime_details(manager, root, details)
        if ctx.semantic_status == "uninitialized":
            ctx.semantic_status = "ok"
        elif ctx.semantic_status != "unavailable":
            ctx.semantic_status = "ok"
    except RefactorError as exc:
        if exc.code in _PYRIGHT_DOWN:
            ctx.semantic_status = "unavailable"
            details["code"] = exc.code
            if semantic_mode == "required":
                return exc
            warnings.append(f"semantic refresh unavailable: {exc.message}")
            return None
        if semantic_mode == "required":
            return exc
        warnings.append(f"semantic refresh failed: {exc.message}")
        return None
    except Exception as exc:
        ctx.semantic_status = "unavailable"
        if semantic_mode == "required":
            return RefactorError("PYRIGHT_UNAVAILABLE", _short_error(str(exc)))
        warnings.append(f"semantic refresh unavailable: {_short_error(str(exc))}")
        return None

    targets = [path for path in [*created, *changed] if path.suffix == ".py" and path.is_file()]
    diagnostic_warnings: list[str] = []
    for path in targets:
        try:
            items = manager.runner.run(service.diagnostics(root, path))
        except Exception:
            continue
        if not isinstance(items, list):
            continue
        for diag in items:
            if not isinstance(diag, dict):
                continue
            if not _is_blocking_diagnostic(diag):
                continue
            message = str(diag.get("message", "diagnostic")).strip()
            diagnostic_warnings.append(f"{path.relative_to(root).as_posix()}: {message}")
            if len(diagnostic_warnings) >= _MAX_DIAGNOSTIC_WARNINGS:
                break
        if len(diagnostic_warnings) >= _MAX_DIAGNOSTIC_WARNINGS:
            break

    if not diagnostic_warnings:
        return None
    if semantic_mode == "required":
        return RefactorError(
            "VERIFICATION_FAILED",
            diagnostic_warnings[0][:300],
        )
    warnings.extend(diagnostic_warnings)
    return None


def _attach_runtime_details(manager: Any, root: Path, details: dict[str, object]) -> None:
    try:
        session = manager.runner.run(manager.get_or_start(root))
    except Exception:
        return
    details.setdefault("semantic_backend", "pyright")
    source = getattr(getattr(session, "runtime", None), "source", None)
    if source:
        details.setdefault("pyright_runtime", source)


def _is_blocking_diagnostic(diag: dict[str, object]) -> bool:
    severity = diag.get("severity", 1)
    if severity not in (1, None):
        try:
            if int(severity) > 1:  # type: ignore[arg-type]
                return False
        except (TypeError, ValueError):
            return False
    message = str(diag.get("message", "")).lower()
    needles = (
        "import",
        "could not be resolved",
        "not defined",
        "unknown import",
        "reportmissingimports",
        "cannot be resolved",
    )
    return any(needle in message for needle in needles)


def _summary(request: RefactorRequest) -> str:
    if request.operation == "rename_symbol":
        return f"Renamed {request.symbol} and updated references"
    if request.operation == "move_symbol":
        return f"Moved {request.symbol} to {request.target}"
    if request.operation == "rename_module":
        return f"Renamed module {request.source} to {request.new_name}"
    if request.operation == "move_module":
        return f"Moved module {request.source} to {request.target}"
    return "Refactor completed"


def _lookup_module(request: RefactorRequest) -> str | None:
    if request.operation in _MODULE_OPS:
        return request.source
    return request.module


def _result_source(request: RefactorRequest) -> str | None:
    if request.operation in _MODULE_OPS:
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
