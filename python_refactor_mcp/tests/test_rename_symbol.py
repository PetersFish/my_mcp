from pathlib import Path

from python_refactor_mcp.models import RefactorRequest
from python_refactor_mcp.rope_adapter import RopeConflictError, run_rope


def test_rename_symbol_updates_imports(mini_pkg: Path) -> None:
    result = run_rope(
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(mini_pkg),
            module="app.services.report",
            symbol="ReportDAO",
            new_name="ReportRepository",
        )
    )
    source = (mini_pkg / "app" / "services" / "report.py").read_text(encoding="utf-8")
    api = (mini_pkg / "app" / "api" / "report.py").read_text(encoding="utf-8")
    tests = (mini_pkg / "tests" / "test_report.py").read_text(encoding="utf-8")
    assert "class ReportRepository" in source
    assert "class ReportDAO" not in source
    assert "ReportRepository" in api
    assert "ReportDAO" not in api
    assert "ReportRepository" in tests
    assert result.changed_files
    payload_keys = set(result.__dict__.keys())
    assert "diff" not in payload_keys


def test_rename_symbol_dry_run_does_not_write(mini_pkg: Path) -> None:
    original = (mini_pkg / "app" / "services" / "report.py").read_text(encoding="utf-8")
    result = run_rope(
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(mini_pkg),
            module="app.services.report",
            symbol="ReportDAO",
            new_name="ReportRepository",
            dry_run=True,
        )
    )
    assert (mini_pkg / "app" / "services" / "report.py").read_text(encoding="utf-8") == original
    assert result.changed_files


def test_rename_symbol_missing_name_is_conflict(mini_pkg: Path) -> None:
    try:
        run_rope(
            RefactorRequest(
                operation="rename_symbol",
                project_root=str(mini_pkg),
                module="app.services.report",
                symbol="MissingType",
                new_name="Other",
            )
        )
    except RopeConflictError as exc:
        assert exc.conflicts
    else:
        raise AssertionError("expected RopeConflictError")
