from __future__ import annotations

import json
from pathlib import Path

from python_refactor_mcp.adapters.rope_adapter import RopeAdapterError
from python_refactor_mcp.models import RefactorRequest
from python_refactor_mcp.models.errors import RefactorError
from python_refactor_mcp.orchestration.refactor_orchestrator import run_refactor
from python_refactor_mcp.services.codemod_service import CodemodService


class _BoomSemantic:
    async def resolve_symbol(self, *args, **kwargs):
        raise RefactorError("PYRIGHT_UNAVAILABLE", "down")

    async def references(self, *args, **kwargs):
        raise RefactorError("PYRIGHT_UNAVAILABLE", "down")

    async def module_defines_symbol(self, *args, **kwargs) -> bool:
        return False

    async def refresh(self, *args, **kwargs) -> None:
        return None

    async def diagnostics(self, *args, **kwargs):
        return []


def test_pyright_down_best_effort_continues(mini_pkg: Path) -> None:
    result = run_refactor(
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(mini_pkg),
            module="app.services.report",
            symbol="ReportDAO",
            new_name="ReportRepository",
            dry_run=True,
            semantic_mode="best_effort",
        ),
        semantic_service=_BoomSemantic(),
    )
    assert result.status == "success"
    assert result.semantic_status == "unavailable"
    raw = result.model_dump_json()
    assert "Traceback" not in raw


def test_pyright_down_required_aborts(mini_pkg: Path) -> None:
    result = run_refactor(
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(mini_pkg),
            module="app.services.report",
            symbol="ReportDAO",
            new_name="ReportRepository",
            dry_run=True,
            semantic_mode="required",
        ),
        semantic_service=_BoomSemantic(),
    )
    assert result.status == "error"
    assert result.files_changed == 0
    assert "Traceback" not in result.model_dump_json()


def test_rope_error_surfaces_as_error(mini_pkg: Path, monkeypatch) -> None:
    def boom(_request):
        raise RopeAdapterError("rope exploded")

    monkeypatch.setattr(
        "python_refactor_mcp.orchestration.refactor_orchestrator.run_rope_refactor",
        boom,
    )
    result = run_refactor(
        RefactorRequest(
            operation="rename_module",
            project_root=str(mini_pkg),
            source="app.services.report",
            new_name="report_service",
            dry_run=True,
        )
    )
    assert result.status == "error"
    assert "Traceback" not in (result.error or "")


def test_libcst_parse_failure_zero_writes(tmp_path: Path) -> None:
    good = tmp_path / "good.py"
    bad = tmp_path / "bad.py"
    good.write_text("from old.mod import Foo\n", encoding="utf-8")
    bad.write_text("class (\n", encoding="utf-8")
    before = good.read_text(encoding="utf-8")
    result = CodemodService().apply(
        tmp_path,
        codemod="replace_qualified_name",
        params={"old": "old.mod.Foo", "new": "new.mod.Foo"},
        dry_run=False,
    )
    assert result.status == "error"
    assert result.code == "CODEMOD_PARSE_ERROR"
    assert good.read_text(encoding="utf-8") == before
    assert "Traceback" not in json.dumps(result.model_dump())


def test_concurrent_modification(tmp_path: Path) -> None:
    path = tmp_path / "a.py"
    path.write_text("from old.mod import Foo\n", encoding="utf-8")
    service = CodemodService()
    preview = service.preview(
        tmp_path,
        codemod="replace_qualified_name",
        params={"old": "old.mod.Foo", "new": "new.mod.Foo"},
    )
    hashes = preview.details["preview_hashes"]
    path.write_text("from old.mod import Foo\n# x\n", encoding="utf-8")
    result = service.apply(
        tmp_path,
        codemod="replace_qualified_name",
        params={"old": "old.mod.Foo", "new": "new.mod.Foo"},
        dry_run=False,
        expected_hashes=hashes,  # type: ignore[arg-type]
    )
    assert result.code == "CONCURRENT_MODIFICATION"


def test_verification_failed_status_in_verify_refactor(mini_pkg: Path, monkeypatch) -> None:
    from python_refactor_mcp import server as server_mod

    def fail_ruff(*_a, **_k):
        return "failed"

    monkeypatch.setattr(
        "python_refactor_mcp.services.verification_service.run_ruff",
        fail_ruff,
    )
    payload = server_mod.verify_refactor(
        project_root=str(mini_pkg),
        changed_files=["app/services/report.py"],
        verification_mode="fast",
        verify=["ruff"],
    )
    assert payload["status"] == "error"
    assert payload["code"] == "VERIFICATION_FAILED"
    assert "Traceback" not in json.dumps(payload)
