from __future__ import annotations

import asyncio
from pathlib import Path

from python_refactor_mcp.adapters.pyright.process_manager import PyrightProcessManager
from python_refactor_mcp.adapters.pyright.semantic_provider import PyrightSemanticProvider
from python_refactor_mcp.models.common import SourcePosition
from python_refactor_mcp.services.semantic_service import SemanticService
from python_refactor_mcp.utils.paths import ensure_inside_project


def _pos(project: Path, rel: str, line: int, character: int) -> SourcePosition:
    return SourcePosition(path=project / rel, line=line, character=character)


def test_definition_from_import_usage(sample_project: Path) -> None:
    async def _run() -> None:
        manager = PyrightProcessManager()
        service = SemanticService(PyrightSemanticProvider(manager))
        try:
            result = await service.definition(
                sample_project,
                _pos(sample_project, "src/app/api/report.py", 0, 32),
            )
            assert result is not None
            path = ensure_inside_project(sample_project, result.path)
            assert path.as_posix().endswith("src/app/services/report.py")
            assert result.line == 0
        finally:
            await manager.shutdown()

    asyncio.run(_run())


def test_references_span_api_service_and_tests(sample_project: Path) -> None:
    async def _run() -> None:
        manager = PyrightProcessManager()
        service = SemanticService(PyrightSemanticProvider(manager))
        try:
            result = await service.references(
                sample_project,
                _pos(sample_project, "src/app/services/report.py", 0, 6),
            )
            joined = "\n".join(item.path.resolve().as_posix() for item in result.locations)
            assert "services/report.py" in joined
            assert "api/report.py" in joined
            assert "test_report.py" in joined
            assert result.count >= 3
        finally:
            await manager.shutdown()

    asyncio.run(_run())


def test_same_name_symbols_are_not_mixed(sample_project: Path) -> None:
    async def _run() -> None:
        manager = PyrightProcessManager()
        service = SemanticService(PyrightSemanticProvider(manager))
        try:
            domain_refs = await service.references(
                sample_project,
                _pos(sample_project, "src/app/domain/user.py", 0, 6),
            )
            api_refs = await service.references(
                sample_project,
                _pos(sample_project, "src/app/api/user.py", 0, 6),
            )
            domain_paths = [loc.path.resolve().as_posix() for loc in domain_refs.locations]
            api_paths = [loc.path.resolve().as_posix() for loc in api_refs.locations]
            assert any(path.endswith("src/app/domain/user.py") for path in domain_paths)
            assert any(path.endswith("src/app/api/users.py") for path in domain_paths)
            assert not any(path.endswith("src/app/api/user.py") for path in domain_paths)
            assert any(path.endswith("src/app/api/user.py") for path in api_paths)
            assert not any(path.endswith("src/app/domain/user.py") for path in api_paths)
        finally:
            await manager.shutdown()

    asyncio.run(_run())


def test_refresh_method_exists(sample_project: Path) -> None:
    async def _run() -> None:
        manager = PyrightProcessManager()
        provider = PyrightSemanticProvider(manager)
        try:
            await provider.refresh(sample_project, [sample_project / "src/app/services/report.py"])
        finally:
            await manager.shutdown()

    asyncio.run(_run())
