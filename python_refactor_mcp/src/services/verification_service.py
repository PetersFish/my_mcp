from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from python_refactor_mcp.models.common import (
    VERIFICATION_MODE_STEPS,
    VerificationMode,
    VerifyStep,
)
from python_refactor_mcp.utils.summaries import LEFTOVER_SAMPLES_LIMIT

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}

MAX_PYTEST_FILES = 10


def resolve_verify_steps(
    *,
    verify: list[VerifyStep] | None,
    verification_mode: VerificationMode | None,
) -> tuple[list[VerifyStep], VerificationMode | None, bool]:
    """Resolve verification steps.

    Lock: explicit ``verify`` wins when provided; otherwise ``verification_mode``
    expands to steps; otherwise default ``[\"residual\"]`` (V1 compat).
    Returns (steps, mode_used, full_pytest).
    """
    if verify is not None:
        mode = verification_mode
        full_pytest = verification_mode == "full"
        return list(verify), mode, full_pytest
    if verification_mode is not None:
        return list(VERIFICATION_MODE_STEPS[verification_mode]), verification_mode, verification_mode == "full"
    return ["residual"], None, False


def scan_residual(
    project_root: str | Path,
    needles: list[str],
    *,
    extra_skip_dirs: set[str] | None = None,
) -> tuple[int, list[str]]:
    root = Path(project_root)
    skip = SKIP_DIRS | (extra_skip_dirs or set())
    if not needles:
        return 0, []

    rg = shutil.which("rg")
    if rg:
        return _scan_with_rg(rg, root, needles, skip)
    return _scan_with_python(root, needles, skip)


def run_verification(
    project_root: str | Path,
    *,
    changed_files: list[str],
    needles: list[str],
    verify: list[VerifyStep] | None = None,
    verification_mode: VerificationMode | None = None,
    pytest_args: list[str] | None,
    dry_run: bool,
    diagnostics_runner: Any | None = None,
) -> tuple[dict[str, str], int, list[str]]:
    steps, _mode, full_pytest = resolve_verify_steps(
        verify=verify,
        verification_mode=verification_mode,
    )
    verification: dict[str, str] = {}
    remaining = 0
    samples: list[str] = []
    root = Path(project_root)

    if "diagnostics" in steps:
        verification["diagnostics"] = _run_diagnostics(
            root, changed_files, diagnostics_runner=diagnostics_runner
        )
    if "residual" in steps:
        if dry_run:
            verification["residual"] = "skipped"
        else:
            remaining, samples = scan_residual(root, needles)
            verification["residual"] = "ok" if remaining == 0 else "failed"
    if "ruff" in steps:
        verification["ruff"] = run_ruff(root, changed_files)
    if "pyright" in steps:
        verification["pyright"] = run_pyright(root, changed_files)
    if "pytest" in steps:
        verification["pytest"] = run_pytest(
            root,
            changed_files,
            pytest_args=pytest_args,
            full_suite=full_pytest,
        )
    return verification, remaining, samples


def _run_diagnostics(
    root: Path,
    changed_files: list[str],
    *,
    diagnostics_runner: Any | None,
) -> str:
    if diagnostics_runner is None:
        return "skipped"
    try:
        return diagnostics_runner(root, changed_files)
    except Exception:
        return "skipped"


def run_ruff(project_root: str | Path, changed_files: list[str]) -> str:
    root = Path(project_root)
    py_files = [
        path
        for path in changed_files
        if path.endswith(".py") and (root / path).is_file()
    ]
    if not py_files or not shutil.which("ruff"):
        return "skipped"
    result = subprocess.run(
        ["ruff", "check", *py_files],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return "ok" if result.returncode == 0 else "failed"


def run_pyright(project_root: str | Path, changed_files: list[str]) -> str:
    from python_refactor_mcp.adapters.pyright.runtime_resolver import PyrightRuntimeResolver

    root = Path(project_root)
    try:
        runtime = PyrightRuntimeResolver().resolve(root)
    except Exception:
        return "skipped"
    cli = runtime.cli
    if cli is None:
        which = shutil.which("pyright")
        if which is None:
            return "skipped"
        cli = Path(which)
    py_files = [
        path
        for path in changed_files
        if path.endswith(".py") and (root / path).is_file()
    ]
    cmd = [str(cli), *py_files] if py_files else [str(cli)]
    result = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    return "ok" if result.returncode == 0 else "failed"


def run_pytest(
    project_root: str | Path,
    changed_files: list[str],
    pytest_args: list[str] | None,
    *,
    full_suite: bool = False,
) -> str:
    root = Path(project_root)
    if not shutil.which("pytest"):
        return "skipped"
    if pytest_args:
        args = list(pytest_args)
    elif full_suite:
        args = []
    else:
        test_files = [
            path
            for path in changed_files
            if _is_test_path(path) and (root / path).is_file()
        ][:MAX_PYTEST_FILES]
        if not test_files:
            return "skipped"
        args = test_files
    result = subprocess.run(
        ["pytest", *args],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return "ok" if result.returncode == 0 else "failed"


def _is_test_path(path: str) -> bool:
    posix = path.replace("\\", "/")
    name = Path(posix).name
    return posix.startswith("tests/") or name.startswith("test_") or name.endswith("_test.py")


def _scan_with_rg(
    rg: str,
    root: Path,
    needles: list[str],
    skip: set[str],
) -> tuple[int, list[str]]:
    glob_args: list[str] = []
    for name in sorted(skip):
        glob_args.extend(["--glob", f"!{name}/**"])
    pattern = "|".join(_escape_rg(n) for n in needles)
    result = subprocess.run(
        [
            rg,
            "--json",
            "--glob",
            "*.py",
            pattern,
            *glob_args,
            ".",
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        return _scan_with_python(root, needles, skip)
    samples: list[str] = []
    count = 0
    try:
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if event.get("type") != "match":
                continue
            data = event.get("data") or {}
            path_info = data.get("path") or {}
            raw_path = str(path_info.get("text") or "")
            lineno = int(data.get("line_number") or 0)
            lines_info = data.get("lines") or {}
            snippet = str(lines_info.get("text") or "").strip()[:120]
            count += 1
            if len(samples) < LEFTOVER_SAMPLES_LIMIT:
                samples.append(_format_rg_json_match(root, raw_path, lineno, snippet))
    except (json.JSONDecodeError, TypeError, ValueError):
        return _scan_with_python(root, needles, skip)
    return count, samples


def _escape_rg(needle: str) -> str:
    return needle.replace("\\", "\\\\").replace(".", r"\.")


def _format_rg_json_match(root: Path, raw_path: str, lineno: int, snippet: str) -> str:
    path = Path(raw_path)
    try:
        if not path.is_absolute():
            path = (root / path).resolve()
        else:
            path = path.resolve()
        display = path.relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        display = raw_path.replace("\\", "/")
    return f"{display}:{lineno}:{snippet}"


def _scan_with_python(
    root: Path,
    needles: list[str],
    skip: set[str],
) -> tuple[int, list[str]]:
    samples: list[str] = []
    count = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip for part in path.parts):
            continue
        if path.suffix != ".py":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(root).as_posix()
        for lineno, raw in enumerate(text.splitlines(), start=1):
            if any(needle in raw for needle in needles):
                count += 1
                if len(samples) < LEFTOVER_SAMPLES_LIMIT:
                    samples.append(f"{rel}:{lineno}:{raw.strip()[:120]}")
    return count, samples
