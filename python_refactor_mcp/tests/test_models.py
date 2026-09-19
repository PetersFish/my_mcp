from pathlib import Path

import pytest
from pydantic import ValidationError

from python_refactor_mcp.models import RefactorRequest, RefactorResult


def test_move_module_requires_source_and_target(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        RefactorRequest(
            operation="move_module",
            project_root=str(tmp_path),
            source="app.services.report",
        )


def test_rename_module_requires_source_and_new_name(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        RefactorRequest(
            operation="rename_module",
            project_root=str(tmp_path),
            source="app.services.report",
        )


def test_rename_module_rejects_dotted_new_name(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="move_module"):
        RefactorRequest(
            operation="rename_module",
            project_root=str(tmp_path),
            source="app.services.report",
            new_name="reporting.report_service",
        )


def test_rename_symbol_requires_module_symbol_and_new_name(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(tmp_path),
            module="app.services.report",
            symbol="ReportDAO",
        )


def test_move_symbol_requires_module_symbol_and_target(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        RefactorRequest(
            operation="move_symbol",
            project_root=str(tmp_path),
            module="app.services.report",
            symbol="build_report",
        )


def test_relative_project_root_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValidationError, match="absolute"):
        RefactorRequest(
            operation="rename_module",
            project_root=".",
            source="app.services.report",
            new_name="report_service",
        )


def test_missing_project_root_is_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(ValidationError, match="exist"):
        RefactorRequest(
            operation="rename_module",
            project_root=str(missing),
            source="app.services.report",
            new_name="report_service",
        )


def test_valid_move_module_request(tmp_path: Path) -> None:
    req = RefactorRequest(
        operation="move_module",
        project_root=str(tmp_path),
        source="app.services.report",
        target="app.reporting.application.report_service",
        dry_run=True,
    )
    assert req.verify is None
    assert req.verification_mode is None
    assert req.dry_run is True


def test_nested_symbol_deeper_than_one_level_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="Class.method"):
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(tmp_path),
            module="app.services.report",
            symbol="ReportDAO.Inner.load",
            new_name="fetch",
        )


def test_result_dump_has_no_diff_keys() -> None:
    result = RefactorResult(status="success", operation="move_module", dry_run=False)
    payload = result.model_dump()
    for banned in ("diff", "content", "description"):
        assert banned not in payload
