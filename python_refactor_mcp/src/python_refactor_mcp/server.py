from __future__ import annotations

import atexit
import asyncio
import logging
from contextlib import suppress
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP

from python_refactor_mcp.adapters.pyright.process_manager import default_manager
from python_refactor_mcp.models import RefactorRequest, VerificationMode, VerifyStep
from python_refactor_mcp.models.errors import RefactorError
from python_refactor_mcp.orchestration.refactor_orchestrator import run_refactor
from python_refactor_mcp.services.codemod_service import CodemodService
from python_refactor_mcp.services.semantic_service import SemanticService
from python_refactor_mcp.services.verification_service import run_verification
from python_refactor_mcp.utils.summaries import MAX_REFERENCES_DEFAULT

logger = logging.getLogger(__name__)

mcp = FastMCP("python-refactor")

TOOL_DESCRIPTION = (
    "Deterministic Python structural refactor via Rope. "
    "Use for module/symbol move and rename instead of multi-file import edits. "
    "project_root must be the target project's absolute path. "
    "Returns a compact JSON summary with file lists, leftover_samples, "
    "leftover_replace_from/to, next_action, and empty_packages; never diffs. "
    "After success, edit only leftover_samples in place using leftover_replace_from -> "
    "leftover_replace_to. Follow next_action. Do not grep or glob the repo."
)

INSPECT_DESCRIPTION = (
    "Inspect a Python symbol at a 1-based file position. Returns a compact "
    "definition/reference/type summary. Use instead of grep/read loops before refactoring. "
    "project_root must be the target project's absolute path. Never returns source or diffs."
)

APPLY_CODEMOD_DESCRIPTION = (
    "Apply a registered LibCST codemod (preview-first; dry_run defaults to true). "
    "Only built-in codemod ids are accepted — never arbitrary transformer source. "
    "Returns compact counts (files_scanned/matched/changed, transform_count); never diffs."
)

VERIFY_DESCRIPTION = (
    "Run verification only (no mutations). Supports verification_mode "
    "fast/standard/full or an explicit verify step list. Never returns source or diffs."
)


@mcp.tool(name="python_refactor", description=TOOL_DESCRIPTION)
def python_refactor(
    operation: Literal["move_module", "rename_module", "rename_symbol", "move_symbol"],
    project_root: str,
    source: str | None = None,
    target: str | None = None,
    module: str | None = None,
    symbol: str | None = None,
    new_name: str | None = None,
    dry_run: bool = False,
    verify: list[VerifyStep] | None = None,
    verification_mode: VerificationMode | None = None,
    pytest_args: list[str] | None = None,
    source_root: str | None = None,
    semantic_mode: Literal["best_effort", "required"] | None = None,
) -> str:
    request = RefactorRequest(
        operation=operation,
        project_root=project_root,
        source=source,
        target=target,
        module=module,
        symbol=symbol,
        new_name=new_name,
        dry_run=dry_run,
        verify=verify,
        verification_mode=verification_mode,
        pytest_args=pytest_args,
        source_root=source_root,
        semantic_mode=semantic_mode,
    )
    return run_refactor(request).model_dump_json()


@mcp.tool(name="inspect_symbol", description=INSPECT_DESCRIPTION)
async def inspect_symbol(
    project_root: str,
    file: str,
    line: int,
    character: int,
    include_definition: bool = True,
    include_references: bool = True,
    include_type: bool = True,
    max_references: int = MAX_REFERENCES_DEFAULT,
) -> dict[str, object]:
    try:
        manager = default_manager()
        future = manager.runner.submit(
            SemanticService().inspect(
                project_root=project_root,
                file=file,
                line=line,
                character=character,
                include_definition=include_definition,
                include_references=include_references,
                include_type=include_type,
                max_references=max_references,
            )
        )
        return await asyncio.wrap_future(future)
    except RefactorError as exc:
        logger.exception("inspect_symbol failed")
        return exc.to_payload()
    except FileNotFoundError as exc:
        logger.exception("inspect_symbol project missing")
        return RefactorError("PROJECT_NOT_FOUND", str(exc)).to_payload()
    except ValueError as exc:
        logger.exception("inspect_symbol invalid path")
        return RefactorError("SOURCE_NOT_FOUND", str(exc)).to_payload()
    except Exception as exc:
        logger.exception("inspect_symbol unexpected error")
        return RefactorError("PYRIGHT_UNAVAILABLE", str(exc)[:300]).to_payload()


@mcp.tool(name="apply_codemod", description=APPLY_CODEMOD_DESCRIPTION)
def apply_codemod(
    project_root: str,
    codemod: str,
    params: dict[str, object] | None = None,
    paths: list[str] | None = None,
    dry_run: bool = True,
) -> str:
    try:
        result = CodemodService().apply(
            project_root,
            codemod=codemod,
            params=params,
            paths=paths or ["."],
            dry_run=dry_run,
        )
        return result.model_dump_json()
    except RefactorError as exc:
        return _error_json(exc)
    except FileNotFoundError as exc:
        return _error_json(RefactorError("PROJECT_NOT_FOUND", str(exc)))
    except ValueError as exc:
        return _error_json(RefactorError("SOURCE_NOT_FOUND", str(exc)))
    except Exception as exc:
        logger.exception("apply_codemod unexpected error")
        return _error_json(RefactorError("CODEMOD_PARSE_ERROR", str(exc)[:300]))


@mcp.tool(name="verify_refactor", description=VERIFY_DESCRIPTION)
def verify_refactor(
    project_root: str,
    changed_files: list[str] | None = None,
    needles: list[str] | None = None,
    verification_mode: VerificationMode = "standard",
    verify: list[VerifyStep] | None = None,
    pytest_args: list[str] | None = None,
) -> dict[str, object]:
    root = Path(project_root)
    manager = default_manager()
    service = SemanticService()

    def diagnostics_runner(diag_root: Path, changed: list[str]) -> str:
        try:
            for rel in changed:
                if not rel.endswith(".py"):
                    continue
                path = diag_root / rel
                if not path.is_file():
                    continue
                diags = manager.runner.run(
                    service.diagnostics(diag_root, path, wait_timeout=0.4)
                )
                items = diags if isinstance(diags, list) else []
                for item in items:
                    severity = (
                        item.get("severity")
                        if isinstance(item, dict)
                        else getattr(item, "severity", None)
                    )
                    if severity in (1, "error", "Error"):
                        return "failed"
            return "ok"
        except Exception:
            return "skipped"

    try:
        verification, remaining, samples = run_verification(
            root,
            changed_files=changed_files or [],
            needles=needles or [],
            verify=verify,
            verification_mode=verification_mode if verify is None else None,
            pytest_args=pytest_args,
            dry_run=False,
            diagnostics_runner=diagnostics_runner,
        )
    except RefactorError as exc:
        return exc.to_payload()
    except Exception as exc:
        logger.exception("verify_refactor unexpected error")
        return RefactorError("VERIFICATION_FAILED", str(exc)[:300]).to_payload()

    failed = any(value == "failed" for value in verification.values())
    return {
        "status": "error" if failed else "success",
        "summary": "Verification failed" if failed else "Verification ok",
        "verification": verification,
        "remaining_old_references": remaining,
        "leftover_samples": samples,
        "metrics": {"residual_references": remaining},
        "warnings": [],
        "details": {"verification_mode": verification_mode if verify is None else None},
        "code": "VERIFICATION_FAILED" if failed else None,
        "error": "one or more verification steps failed" if failed else None,
    }


def _error_json(exc: RefactorError) -> str:
    import json

    return json.dumps(exc.to_payload())


def _shutdown_sessions() -> None:
    manager = default_manager()
    with suppress(Exception):
        manager.runner.run(manager.shutdown(), timeout=15)


atexit.register(_shutdown_sessions)


def run() -> None:
    mcp.run()
