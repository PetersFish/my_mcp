from pathlib import Path

from python_refactor_mcp.models import RefactorRequest
from python_refactor_mcp.adapters.rope_adapter import run_rope


def test_rename_module_same_package(mini_pkg: Path) -> None:
    result = run_rope(
        RefactorRequest(
            operation="rename_module",
            project_root=str(mini_pkg),
            source="app.services.report",
            new_name="report_service",
        )
    )
    assert not (mini_pkg / "app" / "services" / "report.py").exists()
    assert (mini_pkg / "app" / "services" / "report_service.py").exists()
    api = (mini_pkg / "app" / "api" / "report.py").read_text(encoding="utf-8")
    assert "app.services.report_service" in api
    assert "from app.services.report import" not in api
    dynamic = (mini_pkg / "app" / "dynamic.py").read_text(encoding="utf-8")
    assert 'import_module("app.services.report")' in dynamic
    assert result.changed_files


def test_rename_module_dry_run_keeps_source(mini_pkg: Path) -> None:
    result = run_rope(
        RefactorRequest(
            operation="rename_module",
            project_root=str(mini_pkg),
            source="app.services.report",
            new_name="report_service",
            dry_run=True,
        )
    )
    assert (mini_pkg / "app" / "services" / "report.py").exists()
    assert not (mini_pkg / "app" / "services" / "report_service.py").exists()
    assert result.changed_files
