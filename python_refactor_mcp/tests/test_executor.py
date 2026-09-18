from pathlib import Path

from python_refactor_mcp.orchestration.refactor_orchestrator import run_refactor
from python_refactor_mcp.models import RefactorRequest


def test_executor_rename_symbol_success(mini_pkg: Path) -> None:
    result = run_refactor(
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(mini_pkg),
            module="app.services.report",
            symbol="ReportDAO",
            new_name="ReportRepository",
        )
    )
    assert result.status == "success"
    assert result.files_changed >= 1
    assert "diff" not in result.model_dump()
    assert result.verification.get("residual") == "ok"
    assert "ReportDAO" not in (mini_pkg / "app" / "dynamic.py").read_text(encoding="utf-8")
    assert result.remaining_old_references == 0
    assert result.leftover_samples == []
    assert result.leftover_replace_from == "ReportDAO"
    assert result.leftover_replace_to == "ReportRepository"
    assert result.next_action.startswith("No leftovers")
    assert "Do not search" in result.next_action


def test_executor_move_module_reports_leftovers_and_empty_packages(mini_pkg: Path) -> None:
    result = run_refactor(
        RefactorRequest(
            operation="move_module",
            project_root=str(mini_pkg),
            source="app.services.report",
            target="app.reporting.application.report_service",
        )
    )
    assert result.status == "success"
    assert result.leftover_replace_from == "app.services.report"
    assert result.leftover_replace_to == "app.reporting.application.report_service"
    assert any(
        "dynamic.py" in item and "app.services.report" in item
        for item in result.leftover_samples
    )
    assert "app/services" in result.empty_packages
    assert "app" not in result.empty_packages
    assert "Edit only leftover_samples" in result.next_action
    assert "Do not grep or glob" in result.next_action
    assert "app.services.report -> app.reporting.application.report_service" in result.next_action


def test_executor_dry_run_skips_residual(mini_pkg: Path) -> None:
    result = run_refactor(
        RefactorRequest(
            operation="move_module",
            project_root=str(mini_pkg),
            source="app.services.report",
            target="app.reporting.application.report_service",
            dry_run=True,
        )
    )
    assert result.status == "success"
    assert result.dry_run is True
    assert result.verification.get("residual") == "skipped"
    assert (mini_pkg / "app" / "services" / "report.py").exists()
    assert result.empty_packages == []
    assert result.leftover_replace_from == "app.services.report"
    assert "No leftovers" not in result.next_action
    assert "Dry run" in result.next_action
    assert "Re-run without dry_run" in result.next_action


def test_executor_conflict_when_target_exists(mini_pkg: Path) -> None:
    dest = mini_pkg / "app" / "reporting" / "application"
    dest.mkdir(parents=True)
    (dest / "__init__.py").write_text("", encoding="utf-8")
    (dest / "report_service.py").write_text("x = 1\n", encoding="utf-8")
    result = run_refactor(
        RefactorRequest(
            operation="move_module",
            project_root=str(mini_pkg),
            source="app.services.report",
            target="app.reporting.application.report_service",
        )
    )
    assert result.status == "conflict"
    assert result.conflicts
    assert "did not succeed" in result.next_action
    assert (mini_pkg / "app" / "services" / "report.py").exists()


def test_executor_missing_module_is_error(mini_pkg: Path) -> None:
    result = run_refactor(
        RefactorRequest(
            operation="rename_module",
            project_root=str(mini_pkg),
            source="app.missing.nope",
            new_name="other",
        )
    )
    assert result.status == "error"
    assert result.error
    assert "Traceback" not in (result.error or "")


def test_executor_records_git_dirty_without_reset(mini_pkg: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=mini_pkg, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=mini_pkg, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=mini_pkg, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=mini_pkg, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=mini_pkg, check=True, capture_output=True)
    (mini_pkg / "scratch.py").write_text("print(1)\n", encoding="utf-8")
    result = run_refactor(
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(mini_pkg),
            module="app.services.report",
            symbol="ReportDAO",
            new_name="ReportRepository",
        )
    )
    assert result.status == "success"
    assert result.git_dirty_before is True
    assert (mini_pkg / "scratch.py").exists()
