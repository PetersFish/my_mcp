from __future__ import annotations

import asyncio
from pathlib import Path

from python_refactor_mcp.adapters.rope_adapter import PlannedChanges
from python_refactor_mcp.adapters.rope_provider import RopeRefactorProvider
from python_refactor_mcp.models import RefactorRequest
from python_refactor_mcp.providers.codemod import CodemodProvider
from python_refactor_mcp.providers.refactor import RefactorProvider
from python_refactor_mcp.providers.semantic import SemanticProvider
from python_refactor_mcp.providers.type_provider import TypeProvider
from python_refactor_mcp.services.refactor_service import run_rope_refactor


def test_provider_protocols_declare_expected_methods() -> None:
    assert {"definition", "references", "hover", "workspace_symbols", "document_symbols", "diagnostics", "refresh"} <= set(
        dir(SemanticProvider)
    )
    assert {"rename_symbol", "move_symbol", "rename_module", "move_module"} <= set(dir(RefactorProvider))
    assert {"preview", "apply"} <= set(dir(CodemodProvider))
    assert {"get_computed_type", "get_declared_type", "get_expected_type", "resolve_import"} <= set(
        dir(TypeProvider)
    )


def test_rope_refactor_provider_matches_run_rope(mini_pkg: Path) -> None:
    request = RefactorRequest(
        operation="rename_symbol",
        project_root=str(mini_pkg),
        module="app.services.report",
        symbol="ReportDAO",
        new_name="ReportRepository",
        dry_run=True,
    )
    planned = asyncio.run(RopeRefactorProvider().rename_symbol(request))
    assert isinstance(planned, PlannedChanges)
    assert planned.changed_files
    via_service = run_rope_refactor(request)
    assert via_service.changed_files == planned.changed_files
