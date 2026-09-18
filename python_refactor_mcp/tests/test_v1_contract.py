"""Freeze V1 python_refactor MCP behavior before the V3 layout migration."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastmcp import Client

from python_refactor_mcp.orchestration.refactor_orchestrator import run_refactor
from python_refactor_mcp.models import RefactorRequest, RefactorResult
from python_refactor_mcp.server import mcp

REQUIRED_RESULT_KEYS = frozenset(
    {
        "status",
        "operation",
        "dry_run",
        "source",
        "target",
        "files_changed",
        "files_created",
        "files_deleted",
        "changed_files",
        "changed_files_truncated",
        "remaining_old_references",
        "leftover_samples",
        "leftover_replace_from",
        "leftover_replace_to",
        "next_action",
        "empty_packages",
        "conflicts",
        "git_dirty_before",
        "verification",
        "error",
    }
)

BANNED_RESULT_KEYS = frozenset({"diff", "content", "description", "source_text"})
OPERATIONS = ("move_module", "rename_module", "rename_symbol", "move_symbol")


def _tool_json(arguments: dict) -> str:
    async def _call() -> str:
        async with Client(mcp) as client:
            result = await client.call_tool("python_refactor", arguments)
            if getattr(result, "data", None):
                data = result.data
                return data if isinstance(data, str) else json.dumps(data)
            texts = []
            for item in getattr(result, "content", []) or []:
                text = getattr(item, "text", None)
                if text:
                    texts.append(text)
            return "\n".join(texts)

    return asyncio.run(_call())


async def _list_tools() -> list[str]:
    async with Client(mcp) as client:
        listed = await client.list_tools()
        return [tool.name for tool in listed]


def test_python_refactor_tool_is_present() -> None:
    tools = asyncio.run(_list_tools())
    assert "python_refactor" in tools


def test_refactor_result_schema_keys_are_stable() -> None:
    assert set(RefactorResult.model_fields) == REQUIRED_RESULT_KEYS
    for banned in BANNED_RESULT_KEYS:
        assert banned not in RefactorResult.model_fields


def test_four_operations_are_accepted(tmp_path: Path) -> None:
    for operation, extra in (
        ("move_module", {"source": "a.b", "target": "a.c"}),
        ("rename_module", {"source": "a.b", "new_name": "c"}),
        ("rename_symbol", {"module": "a.b", "symbol": "Foo", "new_name": "Bar"}),
        ("move_symbol", {"module": "a.b", "symbol": "Foo", "target": "a.c"}),
    ):
        req = RefactorRequest(
            operation=operation,
            project_root=str(tmp_path),
            dry_run=True,
            **extra,
        )
        assert req.operation == operation


def test_mcp_dry_run_does_not_write_and_omits_diff(mini_pkg: Path) -> None:
    original = (mini_pkg / "app" / "services" / "report.py").read_text(encoding="utf-8")
    raw = _tool_json(
        {
            "operation": "rename_symbol",
            "project_root": str(mini_pkg),
            "module": "app.services.report",
            "symbol": "ReportDAO",
            "new_name": "ReportRepository",
            "dry_run": True,
        }
    )
    payload = json.loads(raw)
    result = RefactorResult.model_validate(payload)
    assert result.status == "success"
    assert result.dry_run is True
    assert result.leftover_replace_from == "ReportDAO"
    assert result.leftover_replace_to == "ReportRepository"
    assert result.next_action
    assert set(payload) == REQUIRED_RESULT_KEYS
    for banned in ("--- a/", "+++ b/", "\ndiff "):
        assert banned not in raw
    assert (mini_pkg / "app" / "services" / "report.py").read_text(encoding="utf-8") == original


def test_executor_covers_all_operations_without_source_dump(mini_pkg: Path) -> None:
    dest = mini_pkg / "app" / "services" / "report_ops.py"
    dest.write_text("", encoding="utf-8")
    cases = [
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(mini_pkg),
            module="app.services.report",
            symbol="ReportDAO",
            new_name="ReportRepository",
            dry_run=True,
        ),
        RefactorRequest(
            operation="move_symbol",
            project_root=str(mini_pkg),
            module="app.services.report",
            symbol="build_report",
            target="app.services.report_ops",
            dry_run=True,
        ),
        RefactorRequest(
            operation="rename_module",
            project_root=str(mini_pkg),
            source="app.services.report",
            new_name="report_service",
            dry_run=True,
        ),
        RefactorRequest(
            operation="move_module",
            project_root=str(mini_pkg),
            source="app.services.report",
            target="app.reporting.application.report_service",
            dry_run=True,
        ),
    ]
    seen: set[str] = set()
    for request in cases:
        result = run_refactor(request)
        seen.add(request.operation)
        dumped = result.model_dump()
        assert set(dumped) == REQUIRED_RESULT_KEYS
        assert result.status == "success"
        assert result.dry_run is True
        assert result.leftover_replace_from is not None
        assert "diff" not in dumped
    assert seen == set(OPERATIONS)
    assert (mini_pkg / "app" / "services" / "report.py").exists()
