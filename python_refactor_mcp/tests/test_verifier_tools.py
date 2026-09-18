import shutil
from pathlib import Path

from python_refactor_mcp.services.verification_service import run_pyright, run_pytest, run_ruff, run_verification


def test_ruff_skipped_when_binary_missing(mini_pkg: Path, monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert run_ruff(mini_pkg, ["app/services/report.py"]) == "skipped"


def test_pyright_skipped_when_binary_missing(mini_pkg: Path, monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert run_pyright(mini_pkg, ["app/services/report.py"]) == "skipped"


def test_pytest_skipped_without_test_files(mini_pkg: Path) -> None:
    assert run_pytest(mini_pkg, ["app/services/report.py"], pytest_args=None) == "skipped"


def test_pytest_args_are_passed(mini_pkg: Path, monkeypatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("python_refactor_mcp.services.verification_service.subprocess.run", fake_run)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/pytest" if name == "pytest" else None)
    status = run_pytest(mini_pkg, [], pytest_args=["-k", "test_build"])
    assert status == "ok"
    assert captured["cmd"][:1] == ["pytest"] or captured["cmd"][0].endswith("pytest")
    assert captured["cmd"][-2:] == ["-k", "test_build"]


def test_run_verification_respects_requested_steps(mini_pkg: Path, monkeypatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    verification, _remaining, _samples = run_verification(
        mini_pkg,
        changed_files=["app/api/report.py"],
        needles=["ReportDAO"],
        verify=["ruff", "pyright"],
        pytest_args=None,
        dry_run=False,
    )
    assert verification["ruff"] == "skipped"
    assert verification["pyright"] == "skipped"
    assert "residual" not in verification
    assert "pytest" not in verification
