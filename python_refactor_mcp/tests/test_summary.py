from python_refactor_mcp.models import RefactorResult
from python_refactor_mcp.utils.summaries import (
    CHANGED_FILES_LIMIT,
    LEFTOVER_SAMPLES_LIMIT,
    compact_result,
    leftover_replace_pair,
)


def test_compact_result_truncates_changed_files() -> None:
    paths = [f"app/f{i}.py" for i in range(CHANGED_FILES_LIMIT + 5)]
    result = compact_result(
        operation="move_module",
        dry_run=True,
        source="app.old",
        target="app.new",
        changed_files=paths,
        created_files=["app/new.py"],
        deleted_files=["app/old.py"],
    )
    assert result.status == "success"
    assert result.files_changed == CHANGED_FILES_LIMIT + 5
    assert result.files_created == 1
    assert result.files_deleted == 1
    assert len(result.changed_files) == CHANGED_FILES_LIMIT
    assert result.changed_files_truncated is True
    payload = result.model_dump()
    for banned in ("diff", "content", "description"):
        assert banned not in payload
    assert "next_action" in payload
    assert "leftover_replace_from" in payload
    assert "empty_packages" in payload


def test_compact_result_conflict_status() -> None:
    result = compact_result(
        operation="rename_symbol",
        dry_run=False,
        source="app.mod",
        target="NewName",
        status="conflict",
        conflicts=["symbol NewName already exists"],
    )
    assert result.status == "conflict"
    assert result.conflicts == ["symbol NewName already exists"]
    assert "Do not grep or glob" in result.next_action
    assert "did not succeed" in result.next_action


def test_compact_result_is_refactor_result() -> None:
    result = compact_result(
        operation="rename_module",
        dry_run=False,
        source="a.b",
        verification={"residual": "ok"},
    )
    assert isinstance(result, RefactorResult)
    assert result.changed_files == []
    assert result.changed_files_truncated is False
    assert result.next_action == (
        "No leftovers. Do not search. Run verification if not already ok. "
        "Coding-client LSP diagnostics are independent; independently verify "
        "immediate conflicts before editing."
    )


def test_compact_result_next_action_with_leftovers() -> None:
    result = compact_result(
        operation="move_module",
        dry_run=False,
        leftover_samples=['app/dynamic.py:3:import_module("app.old")'],
        remaining_old_references=1,
        leftover_replace_from="app.old",
        leftover_replace_to="app.new",
        verification={"residual": "failed"},
    )
    assert result.next_action == (
        "Edit only leftover_samples in place (app.old -> app.new). Do not grep or glob. "
        "Coding-client LSP diagnostics are independent; independently verify "
        "immediate conflicts before editing."
    )


def test_compact_result_dry_run_does_not_claim_no_leftovers() -> None:
    result = compact_result(
        operation="move_module",
        dry_run=True,
        source="app.old",
        target="app.new",
        leftover_replace_from="app.old",
        leftover_replace_to="app.new",
        verification={"residual": "skipped"},
    )
    assert "No leftovers" not in result.next_action
    assert "Dry run" in result.next_action
    assert "leftovers are unknown" in result.next_action
    assert "Re-run without dry_run" in result.next_action
    assert "Do not grep or glob" in result.next_action


def test_compact_result_without_residual_check_does_not_claim_no_leftovers() -> None:
    result = compact_result(
        operation="move_module",
        dry_run=False,
        source="app.old",
        target="app.new",
        verification={"ruff": "ok"},
    )
    assert "No leftovers" not in result.next_action
    assert "residual was not scanned" in result.next_action
    assert 'verify=["residual"]' in result.next_action


def test_compact_result_next_action_surfaces_import_issues() -> None:
    result = compact_result(
        operation="move_module",
        dry_run=False,
        verification={"residual": "ok"},
        import_issues=["app/api/reports.py:1:1: dangling_import: missing module"],
    )
    assert result.import_issues == [
        "app/api/reports.py:1:1: dangling_import: missing module"
    ]
    assert result.next_action == (
        "Rope left 1 import issue(s). Fix each file:line, then run pyright/ruff. "
        "Coding-client LSP diagnostics are independent; independently verify "
        "immediate conflicts before editing."
    )


def test_compact_result_next_action_truncated_dotted_needle() -> None:
    samples = [f"f{i}.py:1:app.old" for i in range(LEFTOVER_SAMPLES_LIMIT + 5)]
    result = compact_result(
        operation="move_module",
        dry_run=False,
        leftover_samples=samples,
        remaining_old_references=LEFTOVER_SAMPLES_LIMIT + 5,
        leftover_replace_from="app.old",
        leftover_replace_to="app.new",
        empty_packages=["app/oldpkg"],
        verification={"residual": "failed"},
    )
    assert len(result.leftover_samples) == LEFTOVER_SAMPLES_LIMIT
    assert "truncated" in result.next_action
    assert "rg leftover_replace_from exactly" in result.next_action
    assert "Do not glob" in result.next_action
    assert "empty_packages are local keep-or-delete decisions" in result.next_action


def test_compact_result_next_action_truncated_bare_identifier() -> None:
    samples = [f"f{i}.py:1:save()" for i in range(LEFTOVER_SAMPLES_LIMIT + 5)]
    result = compact_result(
        operation="rename_symbol",
        dry_run=False,
        leftover_samples=samples,
        remaining_old_references=LEFTOVER_SAMPLES_LIMIT + 5,
        leftover_replace_from="ReportDAO.save",
        leftover_replace_to="ReportDAO.persist",
        verification={"residual": "failed"},
    )
    assert "bare identifier" in result.next_action
    assert "do not grep it repo-wide" in result.next_action
    assert "rg leftover_replace_from exactly" not in result.next_action
    assert "Ruff/Pyright" in result.next_action


def test_leftover_replace_pair_by_operation() -> None:
    assert leftover_replace_pair(
        "move_module",
        source="app.services.report",
        target="app.reporting.application.report_service",
    ) == ("app.services.report", "app.reporting.application.report_service")
    assert leftover_replace_pair(
        "rename_module",
        source="app.services.report",
        new_name="report_service",
    ) == ("app.services.report", "app.services.report_service")
    assert leftover_replace_pair(
        "rename_symbol",
        module="app.services.report",
        symbol="ReportDAO.save",
        new_name="persist",
    ) == ("ReportDAO.save", "ReportDAO.persist")
    assert leftover_replace_pair(
        "rename_symbol",
        module="app.services.report",
        symbol="ReportDAO",
        new_name="ReportRepository",
    ) == ("ReportDAO", "ReportRepository")
    assert leftover_replace_pair(
        "move_symbol",
        module="app.services.report",
        symbol="ReportDAO",
        target="app.reporting.dao",
    ) == ("app.services.report:ReportDAO", "app.reporting.dao:ReportDAO")
