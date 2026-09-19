from __future__ import annotations

import asyncio
from pathlib import Path

from python_refactor_mcp.adapters.pyright.process_manager import PyrightProcessManager
from python_refactor_mcp.adapters.pyright.semantic_provider import PyrightSemanticProvider
from python_refactor_mcp.models import RefactorRequest
from python_refactor_mcp.models.errors import RefactorError
from python_refactor_mcp.orchestration.refactor_orchestrator import run_refactor
from python_refactor_mcp.services.semantic_service import SemanticService


class BoomSemanticService:
    async def resolve_symbol(self, *args, **kwargs):
        raise RefactorError("PYRIGHT_UNAVAILABLE", "pyright down")

    async def references(self, *args, **kwargs):
        raise RefactorError("PYRIGHT_UNAVAILABLE", "pyright down")

    async def module_defines_symbol(self, *args, **kwargs):
        raise RefactorError("PYRIGHT_UNAVAILABLE", "pyright down")

    async def refresh(self, *args, **kwargs):
        raise RefactorError("PYRIGHT_UNAVAILABLE", "pyright down")

    async def diagnostics(self, *args, **kwargs):
        return []


def test_rename_symbol_dry_run_reports_semantic_references(sample_project: Path) -> None:
    original = (sample_project / "src/app/services/report.py").read_text(encoding="utf-8")
    result = run_refactor(
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(sample_project),
            module="app.services.report",
            symbol="ReportDAO",
            new_name="ReportRepository",
            source_root="src",
            dry_run=True,
        )
    )
    assert result.status == "success"
    assert result.dry_run is True
    assert result.metrics["semantic_references_before"] >= 3
    assert result.semantic_status == "ok"
    assert result.details["semantic_backend"] == "pyright"
    assert result.details["pyright_runtime"] in {"explicit", "project", "mcp_fallback"}
    assert (sample_project / "src/app/services/report.py").read_text(encoding="utf-8") == original


def test_rename_missing_symbol_is_symbol_not_found(sample_project: Path) -> None:
    result = run_refactor(
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(sample_project),
            module="app.services.report",
            symbol="MissingType",
            new_name="Other",
            source_root="src",
            dry_run=True,
        )
    )
    assert result.status == "error"
    assert result.details.get("code") == "SYMBOL_NOT_FOUND"
    assert "MissingType" in (result.error or "")
    assert "Traceback" not in (result.error or "")
    assert "class ReportDAO" in (sample_project / "src/app/services/report.py").read_text(
        encoding="utf-8"
    )


def test_move_symbol_target_collision_is_conflict(sample_project: Path) -> None:
    result = run_refactor(
        RefactorRequest(
            operation="move_symbol",
            project_root=str(sample_project),
            module="app.domain.user",
            symbol="User",
            target="app.api.user",
            source_root="src",
            dry_run=True,
        )
    )
    assert result.status == "conflict"
    assert result.conflicts
    assert "User" in " ".join(result.conflicts)
    assert (sample_project / "src/app/domain/user.py").read_text(encoding="utf-8").count("class User") == 1


def test_required_mode_aborts_when_pyright_fails(sample_project: Path) -> None:
    original = (sample_project / "src/app/services/report.py").read_text(encoding="utf-8")
    result = run_refactor(
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(sample_project),
            module="app.services.report",
            symbol="ReportDAO",
            new_name="ReportRepository",
            source_root="src",
            semantic_mode="required",
        ),
        semantic_service=BoomSemanticService(),
    )
    assert result.status == "error"
    assert result.details.get("code") == "PYRIGHT_UNAVAILABLE"
    assert result.semantic_status == "unavailable"
    assert (sample_project / "src/app/services/report.py").read_text(encoding="utf-8") == original


def test_best_effort_continues_when_pyright_fails(sample_project: Path) -> None:
    result = run_refactor(
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(sample_project),
            module="app.services.report",
            symbol="ReportDAO",
            new_name="ReportRepository",
            source_root="src",
            semantic_mode="best_effort",
        ),
        semantic_service=BoomSemanticService(),
    )
    assert result.status == "success"
    assert result.semantic_status == "unavailable"
    assert "class ReportRepository" in (sample_project / "src/app/services/report.py").read_text(
        encoding="utf-8"
    )


def test_resolve_symbol_finds_definition(sample_project: Path) -> None:
    manager = PyrightProcessManager()
    service = SemanticService(PyrightSemanticProvider(manager))

    async def _run():
        try:
            return await service.resolve_symbol(
                sample_project,
                module="app.services.report",
                symbol="ReportDAO",
                source_root="src",
            )
        finally:
            await manager.shutdown()

    position = asyncio.run(_run())
    assert position.path.as_posix().endswith("src/app/services/report.py")
    assert position.line == 0
