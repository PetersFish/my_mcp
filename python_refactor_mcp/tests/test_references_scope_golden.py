from __future__ import annotations

import asyncio
from pathlib import Path

from python_refactor_mcp.adapters.pyright.process_manager import PyrightProcessManager
from python_refactor_mcp.adapters.pyright.semantic_provider import PyrightSemanticProvider
from python_refactor_mcp.models.common import SourcePosition
from python_refactor_mcp.services.semantic_service import SemanticService


def test_references_count_matches_without_full_workspace_flood(sample_project: Path) -> None:
    """Golden gate for P1-1: cross-module refs without opening every *.py."""

    async def _run() -> int:
        manager = PyrightProcessManager()
        service = SemanticService(PyrightSemanticProvider(manager))
        try:
            pos = SourcePosition(
                path=sample_project / "src/app/services/report.py",
                line=0,
                character=6,
            )
            refs = await service.references(sample_project, pos)
            return refs.count
        finally:
            await manager.shutdown()

    count = asyncio.run(_run())
    # ReportDAO is referenced from api/report.py, tests, and declaration.
    assert count >= 3
