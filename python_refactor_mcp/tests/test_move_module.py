from pathlib import Path

import pytest

from python_refactor_mcp.models import RefactorRequest
from python_refactor_mcp.rope_adapter import RopeConflictError, run_rope


def test_move_module_creates_packages(mini_pkg: Path) -> None:
    result = run_rope(
        RefactorRequest(
            operation="move_module",
            project_root=str(mini_pkg),
            source="app.services.report",
            target="app.reporting.application.report_service",
        )
    )
    assert not (mini_pkg / "app" / "services" / "report.py").exists()
    moved = mini_pkg / "app" / "reporting" / "application" / "report_service.py"
    assert moved.exists()
    assert "class ReportDAO" in moved.read_text(encoding="utf-8")
    assert (mini_pkg / "app" / "reporting" / "__init__.py").exists()
    assert (mini_pkg / "app" / "reporting" / "application" / "__init__.py").exists()
    api = (mini_pkg / "app" / "api" / "report.py").read_text(encoding="utf-8")
    assert "app.reporting.application.report_service" in api
    dynamic = (mini_pkg / "app" / "dynamic.py").read_text(encoding="utf-8")
    assert 'import_module("app.services.report")' in dynamic
    assert result.changed_files


def test_move_module_conflict_when_target_exists(mini_pkg: Path) -> None:
    dest_dir = mini_pkg / "app" / "reporting" / "application"
    dest_dir.mkdir(parents=True)
    (dest_dir / "__init__.py").write_text("", encoding="utf-8")
    (dest_dir / "report_service.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(RopeConflictError):
        run_rope(
            RefactorRequest(
                operation="move_module",
                project_root=str(mini_pkg),
                source="app.services.report",
                target="app.reporting.application.report_service",
            )
        )
    assert (mini_pkg / "app" / "services" / "report.py").exists()
