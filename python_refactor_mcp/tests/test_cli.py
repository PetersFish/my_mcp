import json
import subprocess
import sys
from pathlib import Path

from python_refactor_mcp.models import RefactorResult
from python_refactor_mcp.cli import build_parser


def test_cli_defaults_to_fast_verification() -> None:
    args = build_parser().parse_args(
        ["--operation", "rename_module", "--project-root", "/tmp/project"]
    )

    assert args.verify == "diagnostics,ruff"


def test_cli_prints_compact_json(mini_pkg: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "python_refactor_mcp.cli",
            "--operation",
            "rename_symbol",
            "--project-root",
            str(mini_pkg),
            "--module",
            "app.services.report",
            "--symbol",
            "ReportDAO",
            "--new-name",
            "ReportRepository",
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    result = RefactorResult.model_validate(payload)
    assert result.status == "success"
    assert result.dry_run is True
    for banned in ("diff", "content", "description"):
        assert banned not in payload
