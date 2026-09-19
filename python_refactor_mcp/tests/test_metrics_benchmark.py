from __future__ import annotations

import json
from pathlib import Path

from python_refactor_mcp.models import RefactorRequest
from python_refactor_mcp.orchestration.refactor_orchestrator import run_refactor
from python_refactor_mcp.services.codemod_service import CodemodService

# Soft cap: compact payloads must stay small (no source/diff dumps).
RESULT_CHARS_SOFT_CAP = 50_000


def test_rename_metrics_include_duration_and_result_chars(mini_pkg: Path) -> None:
    result = run_refactor(
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(mini_pkg),
            module="app.services.report",
            symbol="ReportDAO",
            new_name="ReportRepository",
            dry_run=True,
            semantic_mode="best_effort",
        )
    )
    assert result.status == "success"
    assert "duration_ms" in result.metrics
    assert result.metrics["duration_ms"] >= 0
    assert "result_chars" in result.metrics
    assert 0 < result.metrics["result_chars"] < RESULT_CHARS_SOFT_CAP
    assert "files_changed" in result.metrics
    raw = result.model_dump_json()
    assert "--- a/" not in raw
    assert "+++ b/" not in raw


def test_codemod_dry_run_metrics_compact(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("from old.mod import Foo\n", encoding="utf-8")
    result = CodemodService().apply(
        tmp_path,
        codemod="replace_qualified_name",
        params={"old": "old.mod.Foo", "new": "new.mod.Foo"},
        dry_run=True,
    )
    assert result.status == "success"
    assert result.metrics["duration_ms"] >= 0
    assert result.metrics["result_chars"] < RESULT_CHARS_SOFT_CAP
    assert "transform_count" in result.metrics
    dumped = json.dumps(result.model_dump())
    assert "from old.mod import Foo" not in dumped or "changed_files" in dumped
    # Must not embed full transformed source
    assert "original" not in result.details
    assert "transformed" not in result.details
