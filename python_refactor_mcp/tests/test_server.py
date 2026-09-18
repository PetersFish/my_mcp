import asyncio
import json
from pathlib import Path

from fastmcp import Client

from python_refactor_mcp.models import RefactorResult
from python_refactor_mcp.server import mcp


def test_python_refactor_tool_returns_json_summary(mini_pkg: Path) -> None:
    async def _call() -> str:
        async with Client(mcp) as client:
            result = await client.call_tool(
                "python_refactor",
                {
                    "operation": "rename_module",
                    "project_root": str(mini_pkg),
                    "source": "app.services.report",
                    "new_name": "report_service",
                    "dry_run": True,
                },
            )
            if getattr(result, "data", None):
                data = result.data
                return data if isinstance(data, str) else json.dumps(data)
            texts = []
            for item in getattr(result, "content", []) or []:
                text = getattr(item, "text", None)
                if text:
                    texts.append(text)
            return "\n".join(texts)

    raw = asyncio.run(_call())
    payload = json.loads(raw)
    result = RefactorResult.model_validate(payload)
    assert result.status == "success"
    assert result.dry_run is True
    for banned in ("--- a/", "+++ b/", "diff"):
        assert banned not in raw
    tools = asyncio.run(_list_tools())
    assert "python_refactor" in tools


async def _list_tools() -> list[str]:
    async with Client(mcp) as client:
        listed = await client.list_tools()
        return [tool.name for tool in listed]
