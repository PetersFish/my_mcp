"""Lightweight timing benches for python_refactor MCP hot paths.

Run: ``.venv/bin/python -m pytest tests/test_perf_timing_bench.py -q -s``
"""

from __future__ import annotations

import time
from pathlib import Path

from python_refactor_mcp.adapters.pyright.process_manager import default_manager
from python_refactor_mcp.models import RefactorRequest
from python_refactor_mcp.orchestration.refactor_orchestrator import run_refactor
from python_refactor_mcp.services.semantic_service import SemanticService
from python_refactor_mcp.services.verification_service import run_verification


def _large_tree(tmp_path: Path, n_files: int = 80) -> Path:
    """Build a ~N-file project with a real cross-module symbol."""
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "core.py").write_text(
        "class Target:\n    def value(self) -> int:\n        return 1\n",
        encoding="utf-8",
    )
    (src / "user.py").write_text(
        "from pkg.core import Target\n\ndef run() -> int:\n    return Target().value()\n",
        encoding="utf-8",
    )
    for i in range(n_files):
        (tmp_path / f"noise_{i}.py").write_text(f"N{i} = {i}\n", encoding="utf-8")
    return tmp_path


def test_bench_rename_symbol_cold(tmp_path: Path) -> None:
    root = _large_tree(tmp_path)
    t0 = time.perf_counter()
    result = run_refactor(
        RefactorRequest(
            operation="rename_symbol",
            project_root=str(root),
            module="pkg.core",
            symbol="Target",
            new_name="Renamed",
            source_root="src",
            dry_run=False,
            verify=["residual"],
        )
    )
    elapsed = time.perf_counter() - t0
    print(f"\n[bench] rename_symbol cold ({80}+ files): {elapsed:.3f}s status={result.status}")
    assert result.status == "success"
    assert elapsed < 55.0


def test_bench_move_module_cold(tmp_path: Path) -> None:
    root = _large_tree(tmp_path, n_files=60)
    dest = root / "src" / "pkg" / "moved"
    dest.mkdir(parents=True)
    (dest / "__init__.py").write_text("", encoding="utf-8")
    t0 = time.perf_counter()
    result = run_refactor(
        RefactorRequest(
            operation="move_module",
            project_root=str(root),
            source="pkg.user",
            target="pkg.moved.user",
            source_root="src",
            dry_run=False,
            verify=["residual"],
        )
    )
    elapsed = time.perf_counter() - t0
    print(f"\n[bench] move_module cold: {elapsed:.3f}s status={result.status}")
    assert result.status in {"success", "conflict"}
    assert elapsed < 55.0


def test_bench_inspect_symbol(tmp_path: Path) -> None:
    root = _large_tree(tmp_path, n_files=80)
    service = SemanticService()
    manager = default_manager()
    t0 = time.perf_counter()
    payload = manager.runner.run(
        service.inspect(
            root,
            "src/pkg/core.py",
            line=1,
            character=7,
        )
    )
    elapsed = time.perf_counter() - t0
    print(
        f"\n[bench] inspect_symbol: {elapsed:.3f}s refs={payload.get('reference_count')}"
    )
    assert payload["status"] == "success"
    assert int(payload["reference_count"]) >= 2
    assert elapsed < 55.0


def test_bench_verify_fast_and_standard(sample_project: Path) -> None:
    changed = ["src/app/services/report.py"]
    t0 = time.perf_counter()
    fast, _, _ = run_verification(
        sample_project,
        changed_files=changed,
        needles=["ReportDAO"],
        verification_mode="fast",
        pytest_args=None,
        dry_run=False,
    )
    fast_elapsed = time.perf_counter() - t0

    t1 = time.perf_counter()
    standard, _, _ = run_verification(
        sample_project,
        changed_files=changed,
        needles=["ReportDAO"],
        verification_mode="standard",
        pytest_args=None,
        dry_run=False,
    )
    standard_elapsed = time.perf_counter() - t1
    print(f"\n[bench] verify fast: {fast_elapsed:.3f}s -> {fast}")
    print(f"[bench] verify standard: {standard_elapsed:.3f}s -> {standard}")
    assert fast_elapsed < 30.0
    assert standard_elapsed < 55.0
