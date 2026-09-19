from __future__ import annotations

import asyncio
from pathlib import Path

from python_refactor_mcp.adapters.pyright.lsp_client import PyrightLspClient
from python_refactor_mcp.adapters.pyright.process_manager import PyrightProcessManager
from python_refactor_mcp.adapters.pyright.runtime import PyrightRuntime
from python_refactor_mcp.adapters.pyright.semantic_provider import (
    PyrightSemanticProvider,
    _find_import_dependents,
)
from python_refactor_mcp.models.common import SourcePosition


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
                if uri in self._opened:
                    return
                self.did_open_uris.append(uri)
                self._opened.add(uri)

    async def request(self, method: str, params: dict, timeout: float = 20) -> object:
        if method == "textDocument/references":
            return []
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


def test_definition_does_not_open_workspace(tmp_path: Path) -> None:
    for i in range(15):
        (tmp_path / f"mod_{i}.py").write_text(f"x = {i}\n", encoding="utf-8")
    target = tmp_path / "mod_0.py"
    client = RecordingLspClient()
    provider = PyrightSemanticProvider(_manager(tmp_path, client))

    async def _run() -> None:
        await provider.definition(
            tmp_path, SourcePosition(path=target, line=0, character=0)
        )

    asyncio.run(_run())
    assert len(client.did_open_uris) == 1
    assert client.did_open_uris[0] == target.resolve().as_uri()


def test_document_symbols_does_not_open_workspace(tmp_path: Path) -> None:
    for i in range(10):
        (tmp_path / f"m{i}.py").write_text("x = 1\n", encoding="utf-8")
    target = tmp_path / "m0.py"
    client = RecordingLspClient()
    provider = PyrightSemanticProvider(_manager(tmp_path, client))

    async def _run() -> None:
        await provider.document_symbols(tmp_path, target)

    asyncio.run(_run())
    assert len(client.did_open_uris) == 1


def test_prepare_default_skips_workspace(tmp_path: Path) -> None:
    for i in range(12):
        (tmp_path / f"f{i}.py").write_text("x = 1\n", encoding="utf-8")
    target = tmp_path / "f0.py"
    client = RecordingLspClient()
    provider = PyrightSemanticProvider(_manager(tmp_path, client))

    async def _run() -> None:
        await provider._prepare(tmp_path, target)

    asyncio.run(_run())
    assert len(client.did_open_uris) == 1


def test_prepare_skips_redundant_did_open(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    client = RecordingLspClient()
    provider = PyrightSemanticProvider(_manager(tmp_path, client))

    async def _run() -> None:
        await provider._prepare(tmp_path, target)
        await provider._prepare(tmp_path, target)

    asyncio.run(_run())
    assert len(client.did_open_uris) == 1


def test_find_import_dependents(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "app"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    target = pkg / "report.py"
    target.write_text("class Report:\n    pass\n", encoding="utf-8")
    consumer = pkg / "api.py"
    consumer.write_text("from app.report import Report\n", encoding="utf-8")
    other = pkg / "misc.py"
    other.write_text("x = 1\n", encoding="utf-8")

    deps = _find_import_dependents(tmp_path, target)
    assert consumer in deps
    assert other not in deps
    assert target not in deps


def test_references_opens_dependents_not_whole_workspace(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "app"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    target = pkg / "report.py"
    target.write_text("class Report:\n    pass\n", encoding="utf-8")
    consumer = pkg / "api.py"
    consumer.write_text("from app.report import Report\n", encoding="utf-8")
    for i in range(20):
        (tmp_path / f"noise_{i}.py").write_text(f"n = {i}\n", encoding="utf-8")

    client = RecordingLspClient()
    provider = PyrightSemanticProvider(_manager(tmp_path, client))

    async def _run() -> None:
        await provider.references(
            tmp_path, SourcePosition(path=target, line=0, character=6)
        )

    asyncio.run(_run())
    opened = set(client.did_open_uris)
    assert target.resolve().as_uri() in opened
    assert consumer.resolve().as_uri() in opened
    # Must not flood all noise files
    assert len(client.did_open_uris) < 10
