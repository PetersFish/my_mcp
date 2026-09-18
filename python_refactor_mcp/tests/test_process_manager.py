from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from python_refactor_mcp.adapters.pyright.process_manager import PyrightProcessManager
from python_refactor_mcp.adapters.pyright.runtime import PyrightRuntime


class FakeClient:
    def __init__(self) -> None:
        self.started = 0
        self.shutdowns = 0
        self.healthy = True
        self.refreshes: list[list[Path]] = []

    async def start(self, runtime: PyrightRuntime, project_root: Path, python_path: Path | None) -> None:
        self.started += 1

    async def health_check(self) -> bool:
        return self.healthy

    async def refresh(self, changed_files: list[Path]) -> None:
        self.refreshes.append(list(changed_files))

    async def shutdown(self) -> None:
        self.shutdowns += 1


@pytest.fixture
def runtime(tmp_path: Path) -> PyrightRuntime:
    ls = tmp_path / "pyright-langserver"
    ls.write_text("#!/bin/sh\n", encoding="utf-8")
    return PyrightRuntime(
        cli=None,
        language_server=ls,
        type_server=None,
        version="test",
        source="mcp_fallback",
    )


def test_get_or_start_reuses_session(tmp_path: Path, runtime: PyrightRuntime) -> None:
    client = FakeClient()
    manager = PyrightProcessManager(
        runtime_factory=lambda _root: runtime,
        client_factory=lambda: client,
    )
    first = asyncio.run(manager.get_or_start(tmp_path))
    second = asyncio.run(manager.get_or_start(tmp_path))
    assert first is second
    assert client.started == 1


def test_shutdown_stops_session(tmp_path: Path, runtime: PyrightRuntime) -> None:
    client = FakeClient()
    manager = PyrightProcessManager(
        runtime_factory=lambda _root: runtime,
        client_factory=lambda: client,
    )
    asyncio.run(manager.get_or_start(tmp_path))
    asyncio.run(manager.shutdown(tmp_path))
    assert client.shutdowns == 1
    asyncio.run(manager.get_or_start(tmp_path))
    assert client.started == 2


def test_unhealthy_session_is_restarted(tmp_path: Path, runtime: PyrightRuntime) -> None:
    client = FakeClient()
    manager = PyrightProcessManager(
        runtime_factory=lambda _root: runtime,
        client_factory=lambda: client,
    )
    asyncio.run(manager.get_or_start(tmp_path))
    client.healthy = False
    asyncio.run(manager.get_or_start(tmp_path))
    assert client.shutdowns == 1
    assert client.started == 2
