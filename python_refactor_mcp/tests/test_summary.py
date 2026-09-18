from python_refactor_mcp.models import RefactorResult
from python_refactor_mcp.summary import CHANGED_FILES_LIMIT, compact_result


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


def test_compact_result_is_refactor_result() -> None:
    result = compact_result(operation="rename_module", dry_run=False, source="a.b")
    assert isinstance(result, RefactorResult)
    assert result.changed_files == []
    assert result.changed_files_truncated is False
