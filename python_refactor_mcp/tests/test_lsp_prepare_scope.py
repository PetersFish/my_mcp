from __future__ import annotations

import asyncio
import time
from pathlib import Path

from python_refactor_mcp.adapters.pyright.lsp_client import PyrightLspClient
from python_refactor_mcp.adapters.pyright.process_manager import PyrightProcessManager
from python_refactor_mcp.adapters.pyright.runtime import PyrightRuntime
from python_refactor_mcp.adapters.pyright.semantic_provider import PyrightSemanticProvider


class RecordingLspClient(PyrightLspClient):
    def __init__(self) -> None:
        super().__init__()
        self.did_open_uris: list[str] = []

    async def start(self, runtime: PyrightRuntime, project_root: Path, python_path: Path | None) -> None:
        return None

    async def health_check(self) -> bool:
        return True

    async def notify(self, method: str, params: dict) -> None:
        if method == "textDocument/didOpen":
            uri = (params.get("textDocument") or {}).get("uri")
            if isinstance(uri, str):
                self.did_open_uris.append(uri)
                self._opened.add(uri)

    async def request(self, method: str, params: dict, timeout: float = 20) -> object:
        return None

    async def refresh(self, **_kwargs) -> None:
        return None

    async def shutdown(self) -> None:
        return None


def _manager(tmp_path: Path, client: RecordingLspClient) -> PyrightProcessManager:
    ls = tmp_path / "fake-ls"
    ls.write_text("#!/bin/sh\n", encoding="utf-8")
    runtime = PyrightRuntime(
        cli=None,
        language_server=ls,
        type_server=None,
        version="test",
        source="mcp_fallback",
    )
    return PyrightProcessManager(
        runtime_factory=lambda _root: runtime,
        client_factory=lambda: client,
    )


def test_prepare_opens_only_target_file_not_whole_workspace(tmp_path: Path) -> None:
    for i in range(20):
        (tmp_path / f"mod_{i}.py").write_text(f"x = {i}\n", encoding="utf-8")
    target = tmp_path / "mod_0.py"
    client = RecordingLspClient()
    provider = PyrightSemanticProvider(_manager(tmp_path, client))

    async def _run() -> None:
        await provider._prepare(tmp_path, target, open_workspace=False)

    asyncio.run(_run())
    assert len(client.did_open_uris) == 1
    assert client.did_open_uris[0] == target.resolve().as_uri()


def test_diagnostics_can_skip_empty_wait(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    client = RecordingLspClient()
    provider = PyrightSemanticProvider(_manager(tmp_path, client))

    async def _run() -> list[dict]:
        return await provider.diagnostics(tmp_path, target, wait_timeout=0.0)

    t0 = time.perf_counter()
    items = asyncio.run(_run())
    elapsed = time.perf_counter() - t0
    assert items == []
    assert elapsed < 0.5
