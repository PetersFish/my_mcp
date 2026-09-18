from pathlib import Path

from python_refactor_mcp.services.verification_service import scan_residual


def test_scan_residual_finds_dynamic_import_string(mini_pkg: Path) -> None:
    count, samples = scan_residual(mini_pkg, ["app.services.report"])
    assert count >= 1
    assert any("dynamic.py" in item and "app.services.report" in item for item in samples)
    assert len(samples) <= 20


def test_scan_residual_skips_venv_and_git(mini_pkg: Path) -> None:
    venv_file = mini_pkg / ".venv" / "lib" / "old.py"
    venv_file.parent.mkdir(parents=True)
    venv_file.write_text('importlib.import_module("app.services.report")\n', encoding="utf-8")
    git_file = mini_pkg / ".git" / "hooks" / "x"
    git_file.parent.mkdir(parents=True)
    git_file.write_text("app.services.report\n", encoding="utf-8")
    count, samples = scan_residual(mini_pkg, ["app.services.report"])
    assert all(".venv" not in item and "/.git/" not in item for item in samples)
    assert count >= 1
