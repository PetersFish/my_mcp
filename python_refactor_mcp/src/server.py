from __future__ import annotations

import atexit
import asyncio
import logging
from contextlib import suppress
from typing import Literal

from fastmcp import FastMCP

from python_refactor_mcp.adapters.pyright.process_manager import default_manager
from python_refactor_mcp.models import RefactorRequest, VerifyStep
from python_refactor_mcp.models.errors import RefactorError
from python_refactor_mcp.orchestration.refactor_orchestrator import run_refactor
from python_refactor_mcp.services.semantic_service import SemanticService
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
        verify=verify or ["residual"],
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


def _shutdown_sessions() -> None:
    manager = default_manager()
    with suppress(Exception):
        manager.runner.run(manager.shutdown(), timeout=15)


atexit.register(_shutdown_sessions)


def run() -> None:
    mcp.run()
