from __future__ import annotations

import asyncio
from pathlib import Path

from fastmcp import Client

from python_refactor_mcp.models.common import VERIFICATION_MODE_STEPS
from python_refactor_mcp.models import RefactorRequest
from python_refactor_mcp.orchestration.refactor_orchestrator import run_refactor
from python_refactor_mcp.server import mcp
from python_refactor_mcp.services.verification_service import resolve_verify_steps, run_verification


def test_mode_step_tables() -> None:
    assert VERIFICATION_MODE_STEPS["fast"] == ["diagnostics", "ruff"]
    assert "pytest" in VERIFICATION_MODE_STEPS["standard"]
    assert VERIFICATION_MODE_STEPS["full"] == VERIFICATION_MODE_STEPS["standard"]


def test_explicit_verify_wins_over_mode() -> None:
    steps, mode, full = resolve_verify_steps(
        verify=["residual"],
        verification_mode="full",
    )
    assert steps == ["residual"]
    assert mode == "full"
    assert full is True


def test_mode_expands_when_verify_omitted() -> None:
    steps, mode, full = resolve_verify_steps(verify=None, verification_mode="fast")
    assert steps == ["diagnostics", "ruff"]
    assert mode == "fast"
    assert full is False


def test_default_residual_when_both_omitted() -> None:
    steps, mode, full = resolve_verify_steps(verify=None, verification_mode=None)
    assert steps == ["residual"]
    assert mode is None
    assert full is False


def test_python_refactor_verification_mode_standard(mini_pkg: Path) -> None:
    result = run_refactor(
        RefactorRequest(
            operation="rename_module",
            project_root=str(mini_pkg),
            source="app.services.report",
            new_name="report_service",
            dry_run=True,
            verification_mode="standard",
        )
    )
    assert result.status == "success"
    assert "residual" in result.verification
    assert result.verification["residual"] == "skipped"


def test_verify_refactor_tool_present_and_runs(mini_pkg: Path) -> None:
    async def _call() -> dict:
        async with Client(mcp) as client:
            tools = [t.name for t in await client.list_tools()]
            assert "verify_refactor" in tools
            result = await client.call_tool(
                "verify_refactor",
                {
                    "project_root": str(mini_pkg),
                    "changed_files": ["app/services/report.py"],
                    "needles": [],
                    "verification_mode": "fast",
                },
            )
            data = result.data if getattr(result, "data", None) is not None else None
            assert isinstance(data, dict)
            return data

    payload = asyncio.run(_call())
    assert payload["status"] in {"success", "error"}
    assert "verification" in payload
    assert "diagnostics" in payload["verification"] or "ruff" in payload["verification"]


def test_full_suite_flag_passed(monkeypatch, tmp_path: Path) -> None:
    calls: list[dict] = []

    def fake_pytest(root, changed_files, pytest_args, *, full_suite=False):
        calls.append({"full_suite": full_suite, "args": pytest_args})
        return "skipped"

    monkeypatch.setattr(
        "python_refactor_mcp.services.verification_service.run_pytest",
        fake_pytest,
    )
    run_verification(
        tmp_path,
        changed_files=[],
        needles=[],
        verify=None,
        verification_mode="full",
        pytest_args=None,
        dry_run=False,
    )
    assert calls and calls[0]["full_suite"] is True
