from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from python_refactor_mcp.models.common import VerifyStep
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
    verify: list[VerifyStep],
    pytest_args: list[str] | None,
    dry_run: bool,
) -> tuple[dict[str, str], int, list[str]]:
    verification: dict[str, str] = {}
    remaining = 0
    samples: list[str] = []
    root = Path(project_root)

    if "residual" in verify:
        if dry_run:
            verification["residual"] = "skipped"
        else:
            remaining, samples = scan_residual(root, needles)
            verification["residual"] = "ok" if remaining == 0 else "failed"
    if "ruff" in verify:
        verification["ruff"] = run_ruff(root, changed_files)
    if "pyright" in verify:
        verification["pyright"] = run_pyright(root, changed_files)
    if "pytest" in verify:
        verification["pytest"] = run_pytest(root, changed_files, pytest_args=pytest_args)
    return verification, remaining, samples


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
    root = Path(project_root)
    if not shutil.which("pyright"):
        return "skipped"
    py_files = [
        path
        for path in changed_files
        if path.endswith(".py") and (root / path).is_file()
    ]
    cmd = ["pyright", *py_files] if py_files else ["pyright"]
    result = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    return "ok" if result.returncode == 0 else "failed"


def run_pytest(
    project_root: str | Path,
    changed_files: list[str],
    pytest_args: list[str] | None,
) -> str:
    root = Path(project_root)
    if not shutil.which("pytest"):
        return "skipped"
    if pytest_args:
        args = list(pytest_args)
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
            "--line-number",
            "--no-heading",
            "-n",
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
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        count += 1
        if len(samples) < LEFTOVER_SAMPLES_LIMIT:
            samples.append(_format_match_line(line))
    return count, samples


def _escape_rg(needle: str) -> str:
    return needle.replace("\\", "\\\\").replace(".", r"\.")


def _format_match_line(line: str) -> str:
    parts = line.split(":", 2)
    if len(parts) < 3:
        return line[:200]
    path, lineno, snippet = parts
    return f"{path}:{lineno}:{snippet.strip()[:120]}"


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
