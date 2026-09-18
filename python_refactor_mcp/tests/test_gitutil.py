import subprocess
from pathlib import Path

from python_refactor_mcp.utils import gitutil


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_snapshot_porcelain_returns_empty_outside_git(tmp_path: Path) -> None:
    assert gitutil.snapshot_porcelain(tmp_path) == []


def test_snapshot_porcelain_lists_dirty_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("print(1)\n", encoding="utf-8")
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "a.py")
    _git(repo, "commit", "-m", "init")
    (repo / "b.py").write_text("print(2)\n", encoding="utf-8")
    (repo / "a.py").write_text("print(3)\n", encoding="utf-8")
    lines = gitutil.snapshot_porcelain(repo)
    joined = "\n".join(lines)
    assert "b.py" in joined
    assert "a.py" in joined


def test_gitutil_has_no_reset_api() -> None:
    assert not hasattr(gitutil, "reset")
    assert not hasattr(gitutil, "hard_reset")
    assert not hasattr(gitutil, "checkout")
