from __future__ import annotations

from pathlib import Path

from python_refactor_mcp.models import RefactorRequest
from python_refactor_mcp.models.common import SourcePosition
from python_refactor_mcp.orchestration.refactor_orchestrator import run_refactor
from python_refactor_mcp.services.semantic_service import SemanticService


class SpySemanticService:
    def __init__(self, inner: SemanticService | None = None) -> None:
        self.inner = inner or SemanticService()
        self.resolve_calls = 0
        self.references_calls = 0
        self.refresh_calls = 0
        self.diagnostics_calls = 0
        self.module_defines_calls = 0

    async def resolve_symbol(self, *args, **kwargs):
        self.resolve_calls += 1
        return await self.inner.resolve_symbol(*args, **kwargs)

    async def references(self, *args, **kwargs):
        self.references_calls += 1
        return await self.inner.references(*args, **kwargs)

    async def module_defines_symbol(self, *args, **kwargs):
        self.module_defines_calls += 1
        return await self.inner.module_defines_symbol(*args, **kwargs)

    async def refresh(self, *args, **kwargs):
        self.refresh_calls += 1
        return await self.inner.refresh(*args, **kwargs)

    async def diagnostics(self, *args, **kwargs):
        self.diagnostics_calls += 1
        return await self.inner.diagnostics(*args, **kwargs)


class WarningDiagnosticsService(SpySemanticService):
    async def diagnostics(self, project_root, path=None, *, wait_timeout: float = 2.0):
        self.diagnostics_calls += 1
        return [
            {
                "severity": 1,
                "message": "Import \"missing_after_move\" could not be resolved",
            }
        ]


class TypeCheckingDiagnosticsService(SpySemanticService):
    async def diagnostics(self, project_root, path=None, *, wait_timeout: float = 2.0):
        self.diagnostics_calls += 1
        if path is not None and path.name == "type_consumer.py":
            return [
                {
                    "severity": 1,
                    "message": '"ReportDAO" is not defined',
                    "range": {
                        "start": {"line": 5, "character": 18},
                        "end": {"line": 5, "character": 27},
                    },
                }
            ]
        return []


class SelfImportDiagnosticsService(SpySemanticService):
    async def diagnostics(self, project_root, path=None, *, wait_timeout: float = 2.0):
        self.diagnostics_calls += 1
        if path is not None and path.name == "self_import_new.py":
            return [
                {
                    "severity": 1,
                    "message": 'Import "app.services.self_import_new" could not be resolved',
                    "range": {
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 10},
                    },
                }
            ]
        return []


def test_module_ops_skip_heavy_preflight(sample_project: Path) -> None:
    spy = SpySemanticService()
    result = run_refactor(
        RefactorRequest(
            operation="move_module",
            project_root=str(sample_project),
            source="app.services.report",
            target="app.reporting.report",
            source_root="src",
            dry_run=True,
        ),
        semantic_service=spy,
    )
    assert result.status == "success"
    assert spy.resolve_calls == 0
    assert spy.references_calls == 0
    assert spy.refresh_calls == 0


def test_move_module_refresh_keeps_definition_at_new_path(sample_project: Path) -> None:
    result = run_refactor(
        RefactorRequest(
            operation="move_module",
            project_root=str(sample_project),
            source="app.services.report",
            target="app.reporting.report",
            source_root="src",
        )
    )
    assert result.status == "success"
    new_path = sample_project / "src/app/reporting/report.py"
    assert new_path.is_file()
    assert not (sample_project / "src/app/services/report.py").exists()
    assert result.details["lsp_session_scope"] == "mcp_managed"
    assert result.details["client_lsp_synchronized"] is False

    from python_refactor_mcp.adapters.pyright.process_manager import default_manager
    from python_refactor_mcp.adapters.pyright.semantic_provider import PyrightSemanticProvider

    manager = default_manager()
    provider = PyrightSemanticProvider(manager)
    service = SemanticService(provider)
    position = SourcePosition(path=new_path, line=0, character=6)
    hit = manager.runner.run(service.definition(sample_project, position))
    assert hit is not None
    assert hit.path.resolve() == new_path.resolve()
    session = manager.runner.run(manager.get_or_start(sample_project))
    assert session.start_count == 1


def test_module_diagnostics_surface_as_warnings_in_best_effort(sample_project: Path) -> None:
    spy = WarningDiagnosticsService()
    result = run_refactor(
        RefactorRequest(
            operation="rename_module",
            project_root=str(sample_project),
            source="app.services.report",
            new_name="report_service",
            source_root="src",
            semantic_mode="best_effort",
        ),
        semantic_service=spy,
    )
    assert result.status == "success"
    assert spy.refresh_calls == 1
    assert spy.diagnostics_calls >= 1
    assert any("could not be resolved" in warning for warning in result.warnings)
    assert result.import_issues
    assert all("dangling_import" in issue for issue in result.import_issues)
    assert any("app/services/report_service.py" in issue for issue in result.import_issues)


def test_type_checking_diagnostic_is_located_and_classified(sample_project: Path) -> None:
    type_consumer = sample_project / "src/app/services/type_consumer.py"
    type_consumer.write_text(
        "from typing import TYPE_CHECKING\n"
        "\n"
        "if TYPE_CHECKING:\n"
        "    from app.services.report import ReportDAO\n"
        "\n"
        "def load(value: ReportDAO) -> int:\n"
        "    return value.load()\n",
        encoding="utf-8",
    )
    result = run_refactor(
        RefactorRequest(
            operation="rename_module",
            project_root=str(sample_project),
            source="app.services.report",
            new_name="report_service",
            source_root="src",
            semantic_mode="best_effort",
        ),
        semantic_service=TypeCheckingDiagnosticsService(),
    )

    assert result.status == "success"
    assert result.import_issues == [
        'src/app/services/type_consumer.py:6:19: '
        'type_checking_annotation_reference: "ReportDAO" is not defined'
    ]


def test_self_import_diagnostic_is_classified(sample_project: Path) -> None:
    self_import = sample_project / "src/app/services/self_import.py"
    self_import.write_text(
        "from . import self_import, missing\n\n"
        "class ReportDAO:\n"
        "    pass\n",
        encoding="utf-8",
    )
    result = run_refactor(
        RefactorRequest(
            operation="rename_module",
            project_root=str(sample_project),
            source="app.services.self_import",
            new_name="self_import_new",
            source_root="src",
            semantic_mode="best_effort",
        ),
        semantic_service=SelfImportDiagnosticsService(),
    )

    assert result.status == "success"
    assert result.import_issues == [
        "src/app/services/self_import_new.py:1:1: self_import: "
        'Import "app.services.self_import_new" could not be resolved'
    ]
