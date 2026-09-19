from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from python_refactor_mcp.orchestration.operation_context import OperationContext
from python_refactor_mcp.services.verification_service import (
    _scan_with_python,
    run_pyright,
    run_verification,
)


def test_scan_with_python_uses_py_glob(tmp_path: Path) -> None:
    (tmp_path / "keep.py").write_text("OLD_NAME = 1\n", encoding="utf-8")
    (tmp_path / "skip.txt").write_text("OLD_NAME in text\n", encoding="utf-8")
    nested = tmp_path / "pkg"
    nested.mkdir()
    (nested / "mod.py").write_text("# OLD_NAME\n", encoding="utf-8")
    junk = tmp_path / ".venv" / "lib"
    junk.mkdir(parents=True)
    (junk / "site.py").write_text("OLD_NAME\n", encoding="utf-8")

    count, samples = _scan_with_python(tmp_path, ["OLD_NAME"], {".venv", ".git"})
    assert count == 2
    assert all("keep.py" in s or "mod.py" in s for s in samples)
    assert not any(".venv" in s for s in samples)


def test_run_verification_reuses_cached_diagnostics_status(tmp_path: Path) -> None:
    calls: list[tuple] = []

    def runner(root: Path, changed: list[str]) -> str:
        calls.append((root, changed))
        return "failed"

    verification, _, _ = run_verification(
        tmp_path,
        changed_files=["a.py"],
        needles=[],
        verify=["diagnostics"],
        pytest_args=None,
        dry_run=False,
        diagnostics_runner=runner,
        diagnostics_status="ok",
    )
    assert verification["diagnostics"] == "ok"
    assert calls == []


def test_run_pyright_prefers_lsp_runner(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    def lsp_runner(root: Path, changed: list[str]) -> str:
        assert changed == ["a.py"]
        return "ok"

    with patch(
        "python_refactor_mcp.services.verification_service.subprocess.run"
    ) as mocked:
        status = run_pyright(tmp_path, ["a.py"], lsp_runner=lsp_runner)
    assert status == "ok"
    mocked.assert_not_called()


def test_run_pyright_falls_back_to_cli_when_lsp_skips(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    class FakeRuntime:
        cli = tmp_path / "fake-pyright"
        source = "test"

    FakeRuntime.cli.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    monkeypatch.setattr(
        "python_refactor_mcp.adapters.pyright.runtime_resolver.PyrightRuntimeResolver.resolve",
        lambda self, root: FakeRuntime(),
    )

    def lsp_runner(root: Path, changed: list[str]) -> str:
        return "skipped"

    class Result:
        returncode = 0

    with patch(
        "python_refactor_mcp.services.verification_service.subprocess.run",
        return_value=Result(),
    ) as mocked:
        status = run_pyright(tmp_path, ["a.py"], lsp_runner=lsp_runner)
    assert status == "ok"
    mocked.assert_called_once()


def test_operation_context_caches_diagnostics_status() -> None:
    ctx = OperationContext(
        operation_id="op",
        project_root=Path("/tmp"),
        operation_type="move_module",
    )
    assert ctx.cached_diagnostics_status is None
    ctx.cached_diagnostics_status = "ok"
    assert ctx.cached_diagnostics_status == "ok"
