from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from python_refactor_mcp.adapters.pyright.process_manager import PyrightProcessManager
from python_refactor_mcp.adapters.pyright.runtime import PyrightRuntime
from python_refactor_mcp.adapters.pyright.semantic_provider import PyrightSemanticProvider
from python_refactor_mcp.adapters.rope_adapter import run_rope
from python_refactor_mcp.models import RefactorRequest
from python_refactor_mcp.models.common import SourcePosition
from python_refactor_mcp.models.errors import RefactorError
from python_refactor_mcp.services.semantic_service import SemanticService
from python_refactor_mcp.utils.paths import ensure_inside_project


class RecordingClient:
    def __init__(self) -> None:
        self.started = 0
        self.shutdowns = 0
        self.healthy = True
        self.refresh_calls: list[dict[str, list[Path]]] = []
        self.fail_refresh = False

    async def start(self, runtime: PyrightRuntime, project_root: Path, python_path: Path | None) -> None:
        self.started += 1

    async def health_check(self) -> bool:
        return self.healthy

    async def refresh(
        self,
        *,
        created: list[Path] | None = None,
        changed: list[Path] | None = None,
        deleted: list[Path] | None = None,
    ) -> None:
        self.refresh_calls.append(
            {
                "created": list(created or []),
                "changed": list(changed or []),
                "deleted": list(deleted or []),
            }
        )
        if self.fail_refresh:
            self.fail_refresh = False
            raise RefactorError("PYRIGHT_TIMEOUT", "timed out")

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


def test_refresh_timeout_restarts_once(tmp_path: Path, runtime: PyrightRuntime) -> None:
    client = RecordingClient()
    client.fail_refresh = True
    manager = PyrightProcessManager(
        runtime_factory=lambda _root: runtime,
        client_factory=lambda: client,
    )
    created = [tmp_path / "new.py"]
    changed = [tmp_path / "mod.py"]
    deleted = [tmp_path / "old.py"]

    async def _run() -> None:
        await manager.get_or_start(tmp_path)
        await manager.refresh(tmp_path, created=created, changed=changed, deleted=deleted)

    asyncio.run(_run())
    assert client.shutdowns == 1
    assert client.started == 2
    assert len(client.refresh_calls) == 2
    assert client.refresh_calls[0]["created"] == created
    assert client.refresh_calls[0]["changed"] == changed
    assert client.refresh_calls[0]["deleted"] == deleted
    assert client.refresh_calls[1] == client.refresh_calls[0]


def test_refresh_after_rename_updates_references(sample_project: Path) -> None:
    async def _run() -> None:
        manager = PyrightProcessManager()
        service = SemanticService(PyrightSemanticProvider(manager))
        try:
            old_pos = SourcePosition(
                path=sample_project / "src/app/services/report.py",
                line=0,
                character=6,
            )
            before = await service.references(sample_project, old_pos)
            assert before.count >= 3

            planned = run_rope(
                RefactorRequest(
                    operation="rename_symbol",
                    project_root=str(sample_project),
                    module="app.services.report",
                    symbol="ReportDAO",
                    new_name="ReportRepository",
                    source_root="src",
                )
            )
            await service.refresh(
                sample_project,
                created=[sample_project / path for path in planned.created_files],
                changed=[sample_project / path for path in planned.changed_files],
                deleted=[sample_project / path for path in planned.deleted_files],
            )

            new_pos = SourcePosition(
                path=sample_project / "src/app/services/report.py",
                line=0,
                character=6,
            )
            after_new = await service.references(sample_project, new_pos)
            assert after_new.count > 0
            joined = "\n".join(
                loc.path.read_text(encoding="utf-8").splitlines()[loc.line]
                for loc in after_new.locations
            )
            assert "ReportRepository" in joined
            assert "class ReportDAO" not in (sample_project / "src/app/services/report.py").read_text(
                encoding="utf-8"
            )

            old_symbols = await service._provider.workspace_symbols(sample_project, "ReportDAO")
            names = _symbol_names(old_symbols)
            assert "ReportDAO" not in names

            session = await manager.get_or_start(sample_project)
            assert session.start_count == 1
        finally:
            await manager.shutdown()

    asyncio.run(_run())


def test_diagnostics_are_cached_from_publish(tmp_path: Path) -> None:
    source = tmp_path / "broken.py"
    source.write_text("import definitely_missing_module_xyz\n", encoding="utf-8")

    async def _run() -> list[dict]:
        manager = PyrightProcessManager()
        provider = PyrightSemanticProvider(manager)
        try:
            await provider.definition(
                tmp_path,
                SourcePosition(path=source, line=0, character=7),
            )
            await asyncio.sleep(0.6)
            return await provider.diagnostics(tmp_path, source)
        finally:
            await manager.shutdown()

    diagnostics = asyncio.run(_run())
    assert diagnostics
    dumped = str(diagnostics).lower()
    assert "definitely_missing_module_xyz" in dumped or "import" in dumped


def _symbol_names(symbols: list[dict]) -> set[str]:
    names: set[str] = set()
    for item in symbols:
        name = item.get("name")
        if isinstance(name, str):
            names.add(name)
    return names
