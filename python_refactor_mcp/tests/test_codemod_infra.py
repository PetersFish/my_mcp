from __future__ import annotations

from pathlib import Path

import pytest

from python_refactor_mcp.adapters.libcst.adapter import LibCSTCodemodProvider
from python_refactor_mcp.adapters.libcst.registry import CodemodRegistry
from python_refactor_mcp.codemods.builtin import default_registry
from python_refactor_mcp.models.errors import RefactorError
from python_refactor_mcp.services.codemod_service import CodemodService


def test_registry_lists_builtin_ids() -> None:
    ids = default_registry().list_ids()
    assert ids == [
        "replace_call_keyword",
        "replace_decorator",
        "replace_qualified_name",
    ]


def test_registry_unknown_id_raises() -> None:
    with pytest.raises(RefactorError) as exc:
        default_registry().get("nope")
    assert exc.value.code == "CODEMOD_NOT_FOUND"


def test_path_escape_rejected(tmp_path: Path) -> None:
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    service = CodemodService()
    result = service.preview(
        tmp_path,
        codemod="replace_qualified_name",
        params={"old": "a.b", "new": "c.d"},
        paths=["../outside"],
    )
    assert result.status == "error"
    assert result.code == "SOURCE_NOT_FOUND"


def test_parse_error_fail_closed_zero_writes(tmp_path: Path) -> None:
    good = tmp_path / "good.py"
    bad = tmp_path / "bad.py"
    good.write_text("from old.mod import Foo\n", encoding="utf-8")
    bad.write_text("def (\n", encoding="utf-8")
    before = good.read_text(encoding="utf-8")
    result = CodemodService().apply(
        tmp_path,
        codemod="replace_qualified_name",
        params={"old": "old.mod.Foo", "new": "new.mod.Foo"},
        paths=["."],
        dry_run=False,
    )
    assert result.status == "error"
    assert result.code == "CODEMOD_PARSE_ERROR"
    assert good.read_text(encoding="utf-8") == before


def test_concurrent_modification_detected(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("from old.mod import Foo\nx = Foo()\n", encoding="utf-8")
    service = CodemodService()
    preview = service.preview(
        tmp_path,
        codemod="replace_qualified_name",
        params={"old": "old.mod.Foo", "new": "new.mod.Foo"},
    )
    assert preview.status == "success"
    assert preview.files_matched >= 1
    hashes = preview.details.get("preview_hashes")
    assert isinstance(hashes, dict)
    target.write_text("from old.mod import Foo\nx = Foo()\n# edited\n", encoding="utf-8")
    result = service.apply(
        tmp_path,
        codemod="replace_qualified_name",
        params={"old": "old.mod.Foo", "new": "new.mod.Foo"},
        dry_run=False,
        expected_hashes=hashes,  # type: ignore[arg-type]
    )
    assert result.status == "error"
    assert result.code == "CONCURRENT_MODIFICATION"


def test_empty_registry_get() -> None:
    registry = CodemodRegistry()
    with pytest.raises(RefactorError) as exc:
        registry.get("replace_qualified_name")
    assert exc.value.code == "CODEMOD_NOT_FOUND"


def test_provider_preview_counts(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("from old.mod import Foo\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("x = 1\n", encoding="utf-8")
    provider = LibCSTCodemodProvider()
    registry = default_registry()
    params = registry.validate_params(
        "replace_qualified_name", {"old": "old.mod.Foo", "new": "new.mod.Bar"}
    )
    run = provider.preview(
        tmp_path,
        codemod_id="replace_qualified_name",
        params=params,
        paths=["."],
        registry=registry,
    )
    assert run.files_scanned == 2
    assert run.files_matched == 1
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "from old.mod import Foo\n"
