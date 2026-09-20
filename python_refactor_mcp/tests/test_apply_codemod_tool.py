from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastmcp import Client

from python_refactor_mcp.server import mcp


def _call_tool(name: str, arguments: dict) -> object:
    async def _run() -> object:
        async with Client(mcp) as client:
            result = await client.call_tool(name, arguments)
            if getattr(result, "data", None) is not None:
                return result.data
            texts = []
            for item in getattr(result, "content", []) or []:
                text = getattr(item, "text", None)
                if text:
                    texts.append(text)
            raw = "\n".join(texts)
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return raw

    return asyncio.run(_run())


async def _list_tools() -> list[str]:
    async with Client(mcp) as client:
        listed = await client.list_tools()
        return [tool.name for tool in listed]


def test_apply_codemod_tool_defaults_to_dry_run(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("from old.mod import Foo\n", encoding="utf-8")
    tools = asyncio.run(_list_tools())
    assert "apply_codemod" in tools
    payload = _call_tool(
        "apply_codemod",
        {
            "project_root": str(tmp_path),
            "codemod": "replace_qualified_name",
            "params": {"old": "old.mod.Foo", "new": "new.mod.Foo"},
        },
    )
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert payload["status"] == "success"
    assert payload["dry_run"] is True
    assert payload["files_changed"] == 0
    assert target.read_text(encoding="utf-8") == "from old.mod import Foo\n"
    for banned in ("--- a/", "+++ b/", "diff"):
        assert banned not in json.dumps(payload)


def test_apply_codemod_tool_writes_when_not_dry_run(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("from old.mod import Foo\n", encoding="utf-8")
    payload = _call_tool(
        "apply_codemod",
        {
            "project_root": str(tmp_path),
            "codemod": "replace_qualified_name",
            "params": {"old": "old.mod.Foo", "new": "new.mod.Foo"},
            "dry_run": False,
        },
    )
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert payload["status"] == "success"
    assert payload["dry_run"] is False
    assert "from new.mod import Foo" in target.read_text(encoding="utf-8")


def test_apply_codemod_tool_normalizes_safe_import(tmp_path: Path) -> None:
    target = tmp_path / "consumer.py"
    target.write_text(
        "import app.services.report_ops\n\n"
        "def run() -> int:\n"
        "    return app.services.report_ops.build_report()\n",
        encoding="utf-8",
    )

    payload = _call_tool(
        "apply_codemod",
        {
            "project_root": str(tmp_path),
            "codemod": "normalize_imports",
            "dry_run": False,
        },
    )
    if isinstance(payload, str):
        payload = json.loads(payload)

    assert payload["status"] == "success"
    assert payload["files_changed"] == 1
    assert "from app.services.report_ops import build_report" in target.read_text(
        encoding="utf-8"
    )
