from __future__ import annotations

import asyncio
from pathlib import Path

from python_refactor_mcp.adapters.pyright.lsp_client import PyrightLspClient
from python_refactor_mcp.adapters.pyright.runtime_resolver import PyrightRuntimeResolver


def test_lsp_client_initialize_and_definition(tmp_path: Path) -> None:
    source = tmp_path / "mod.py"
    source.write_text("class ReportDAO:\n    pass\n\nvalue = ReportDAO()\n", encoding="utf-8")
    runtime = PyrightRuntimeResolver().resolve(tmp_path)

    async def _run() -> dict:
        client = PyrightLspClient()
        await client.start(runtime, tmp_path, python_path=None)
        try:
            await client.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": source.resolve().as_uri(),
                        "languageId": "python",
                        "version": 1,
                        "text": source.read_text(encoding="utf-8"),
                    }
                },
            )
            result = await client.request(
                "textDocument/definition",
                {
                    "textDocument": {"uri": source.resolve().as_uri()},
                    "position": {"line": 3, "character": 8},
                },
            )
            assert await client.health_check()
            return result
        finally:
            await client.shutdown()

    result = asyncio.run(_run())
    locations = result if isinstance(result, list) else [result]
    assert locations
    uri = locations[0]["uri"] if isinstance(locations[0], dict) else locations[0].get("uri")
    assert source.name in uri
    assert locations[0]["range"]["start"]["line"] == 0
