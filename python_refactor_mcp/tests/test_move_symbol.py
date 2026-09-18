from pathlib import Path

from python_refactor_mcp.models import RefactorRequest
from python_refactor_mcp.adapters.rope_adapter import run_rope


def test_move_symbol_to_new_module(mini_pkg: Path) -> None:
    dest = mini_pkg / "app" / "services" / "report_ops.py"
    dest.write_text("", encoding="utf-8")
    result = run_rope(
        RefactorRequest(
            operation="move_symbol",
            project_root=str(mini_pkg),
            module="app.services.report",
            symbol="build_report",
            target="app.services.report_ops",
        )
    )
    source = (mini_pkg / "app" / "services" / "report.py").read_text(encoding="utf-8")
    moved = dest.read_text(encoding="utf-8")
    api = (mini_pkg / "app" / "api" / "report.py").read_text(encoding="utf-8")
    assert "def build_report" not in source
    assert "def build_report" in moved
    assert "report_ops" in api or "build_report" in api
    assert result.changed_files
