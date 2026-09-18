from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastmcp import Client

from python_refactor_mcp.adapters.pyright.process_manager import default_manager
from python_refactor_mcp.server import mcp


def _call_inspect(**arguments: object) -> dict:
    async def _run() -> str:
        async with Client(mcp) as client:
            result = await client.call_tool("inspect_symbol", arguments)
            if getattr(result, "data", None):
                data = result.data
                return data if isinstance(data, str) else json.dumps(data)
            texts = []
            for item in getattr(result, "content", []) or []:
                text = getattr(item, "text", None)
                if text:
                    texts.append(text)
            return "\n".join(texts)

    return json.loads(asyncio.run(_run()))


def test_inspect_symbol_tool_is_listed() -> None:
    async def _list() -> list[str]:
        async with Client(mcp) as client:
            return [tool.name for tool in await client.list_tools()]

    tools = asyncio.run(_list())
    assert "python_refactor" in tools
    assert "inspect_symbol" in tools


def test_inspect_symbol_returns_compact_summary(sample_project: Path) -> None:
    payload = _call_inspect(
        project_root=str(sample_project),
        file="src/app/api/report.py",
        line=1,
        character=33,
        include_definition=True,
        include_references=True,
        include_type=True,
        max_references=2,
    )
    assert payload["status"] == "success"
    assert payload["definition"].endswith("src/app/services/report.py:1:7")
    assert payload["reference_count"] >= 3
    assert payload["references_returned"] == 2
    assert payload["references_truncated"] is True
    dumped = json.dumps(payload)
    assert "def handle" not in dumped
    assert "--- a/" not in dumped
    assert payload["pyright_runtime"] in {"explicit", "project", "mcp_fallback"}


def test_inspect_symbol_rejects_path_escape(sample_project: Path, tmp_path: Path) -> None:
    outside = tmp_path / "other.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    payload = _call_inspect(
        project_root=str(sample_project),
        file=str(outside),
        line=1,
        character=1,
    )
    assert payload["status"] == "error"
    assert payload["code"] in {"SOURCE_NOT_FOUND", "PROJECT_NOT_FOUND"}
    assert "Traceback" not in json.dumps(payload)


def test_inspect_symbol_reuses_pyright_session(sample_project: Path) -> None:
    manager = default_manager()
    for _ in range(10):
        payload = _call_inspect(
            project_root=str(sample_project),
            file="src/app/services/report.py",
            line=1,
            character=7,
            include_references=False,
            include_type=False,
        )
        assert payload["status"] == "success", payload
    session = manager.runner.run(manager.get_or_start(sample_project.resolve()))
    assert session.start_count == 1
