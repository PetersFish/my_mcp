from __future__ import annotations

import shutil
from pathlib import Path

from python_refactor_mcp.adapters.pyright.runtime_resolver import PyrightRuntimeResolver
from python_refactor_mcp.models import RefactorRequest
from python_refactor_mcp.orchestration.refactor_orchestrator import run_refactor
from python_refactor_mcp.services.verification_service import run_pyright


def test_pyright_uses_mcp_fallback_when_path_empty(mini_pkg: Path, monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    runtime = PyrightRuntimeResolver().resolve(mini_pkg)
    assert runtime.cli is not None
    status = run_pyright(mini_pkg, ["app/services/report.py"])
    assert status in {"ok", "failed"}


def test_pyright_skipped_only_when_no_cli(mini_pkg: Path, monkeypatch) -> None:
    class EmptyRuntime:
        cli = None

    monkeypatch.setattr(
        "python_refactor_mcp.adapters.pyright.runtime_resolver.PyrightRuntimeResolver.resolve",
        lambda self, root: EmptyRuntime(),
    )
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert run_pyright(mini_pkg, ["app/services/report.py"]) == "skipped"


def test_rename_reports_mcp_fallback_runtime(sample_project: Path, monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    result = run_refactor(
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(sample_project),
            module="app.services.report",
            symbol="ReportDAO",
            new_name="ReportRepository",
            source_root="src",
            dry_run=True,
            verify=["pyright"],
        )
    )
    assert result.status == "success"
    assert result.details.get("pyright_runtime") == "mcp_fallback"
    assert result.details.get("semantic_backend") == "pyright"
