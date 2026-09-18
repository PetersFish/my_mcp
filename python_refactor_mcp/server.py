from __future__ import annotations

from typing import Literal

from fastmcp import FastMCP

from python_refactor_mcp.executor import run_refactor
from python_refactor_mcp.models import RefactorRequest, VerifyStep

mcp = FastMCP("python-refactor")

TOOL_DESCRIPTION = (
    "Deterministic Python structural refactor via Rope. "
    "Use for module/symbol move and rename instead of multi-file import edits. "
    "project_root must be the target project's absolute path. "
    "Returns a compact JSON summary with file lists and leftover string refs; never diffs. "
    "Fix leftover_samples (dynamic imports/strings) yourself after success."
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
    )
    return run_refactor(request).model_dump_json()


def run() -> None:
    mcp.run()
