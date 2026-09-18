import json
from pathlib import Path

from python_refactor_mcp.install import (
    BLOCK_END,
    BLOCK_START,
    SERVER_NAME,
    doctor,
    parse_args,
    setup,
    uninstall,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def _empty_path_env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "empty-bin"
    bin_dir.mkdir()
    return {"PATH": str(bin_dir)}


def test_parse_args_setup_cursor() -> None:
    parsed = parse_args(["setup", "--client", "cursor", "--yes"])
    assert parsed.command == "setup"
    assert parsed.client == "cursor"
    assert parsed.yes is True


def test_setup_registers_cursor_and_copies_skill(tmp_path: Path) -> None:
    home = tmp_path / "home"
    result = setup(
        package_root=PACKAGE_ROOT,
        home=home,
        client="cursor",
        skip_venv=True,
        skip_doctor=True,
    )
    assert result.ok
    mcp_path = home / ".cursor" / "mcp.json"
    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert SERVER_NAME in data["mcpServers"]
    skill = home / ".cursor" / "skills" / "python-refactor" / "SKILL.md"
    assert skill.is_file()
    assert "python_refactor" in skill.read_text(encoding="utf-8")
    assert not (home / ".claude" / "CLAUDE.md").exists()


def test_uninstall_removes_cursor_server(tmp_path: Path) -> None:
    home = tmp_path / "home"
    setup(
        package_root=PACKAGE_ROOT,
        home=home,
        client="cursor",
        skip_venv=True,
        skip_doctor=True,
    )
    result = uninstall(home=home, client="cursor", purge=True)
    assert result.ok
    mcp_path = home / ".cursor" / "mcp.json"
    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert SERVER_NAME not in data.get("mcpServers", {})
    assert not (home / ".cursor" / "skills" / "python-refactor").exists()


def test_doctor_reports_missing_venv(tmp_path: Path) -> None:
    package_root = tmp_path / "pkg"
    package_root.mkdir()
    home = tmp_path / "home"
    result = doctor(package_root=package_root, home=home, skip_probe=True)
    assert result.ok is False
    assert any("venv" in issue.lower() or ".venv" in issue for issue in result.issues)


def test_setup_writes_claude_json_and_claude_md_without_cli(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = _empty_path_env(tmp_path)
    result = setup(
        package_root=PACKAGE_ROOT,
        home=home,
        client="claude",
        skip_venv=True,
        skip_doctor=True,
        env=env,
    )
    assert result.ok
    data = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    assert SERVER_NAME in data["mcpServers"]
    assert data["mcpServers"][SERVER_NAME]["args"] == ["-m", "python_refactor_mcp"]
    skill = home / ".claude" / "skills" / "python-refactor" / "SKILL.md"
    assert skill.is_file()
    claude_md = (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
    assert BLOCK_START in claude_md
    assert BLOCK_END in claude_md
    assert "python_refactor" in claude_md
    assert "name: python-refactor" not in claude_md.split(BLOCK_START, 1)[1]


def test_setup_writes_opencode_json_and_agents_md_without_cli(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = _empty_path_env(tmp_path)
    result = setup(
        package_root=PACKAGE_ROOT,
        home=home,
        client="opencode",
        skip_venv=True,
        skip_doctor=True,
        env=env,
    )
    assert result.ok
    data = json.loads((home / ".config" / "opencode" / "opencode.json").read_text(encoding="utf-8"))
    assert SERVER_NAME in data["mcp"]["servers"]
    assert data["mcp"]["servers"][SERVER_NAME]["type"] == "local"
    agents = (home / ".config" / "opencode" / "AGENTS.md").read_text(encoding="utf-8")
    assert BLOCK_START in agents
    assert "python_refactor" in agents


def test_setup_instruction_block_is_idempotent(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = _empty_path_env(tmp_path)
    kwargs = {
        "package_root": PACKAGE_ROOT,
        "home": home,
        "client": "claude",
        "skip_venv": True,
        "skip_doctor": True,
        "env": env,
    }
    claude_md = home / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True)
    claude_md.write_text("user rules\n", encoding="utf-8")
    setup(**kwargs)
    setup(**kwargs)
    text = claude_md.read_text(encoding="utf-8")
    assert text.startswith("user rules")
    assert text.count(BLOCK_START) == 1
    assert text.count(BLOCK_END) == 1


def test_uninstall_purge_removes_mcp_skill_and_keeps_other_claude_md(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = _empty_path_env(tmp_path)
    claude_md = home / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True)
    claude_md.write_text("keep this intro\n", encoding="utf-8")
    setup(
        package_root=PACKAGE_ROOT,
        home=home,
        client="claude",
        skip_venv=True,
        skip_doctor=True,
        env=env,
    )
    result = uninstall(home=home, client="claude", purge=True, env=env)
    assert result.ok
    data = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    assert SERVER_NAME not in data.get("mcpServers", {})
    assert not (home / ".claude" / "skills" / "python-refactor").exists()
    leftover = claude_md.read_text(encoding="utf-8")
    assert "keep this intro" in leftover
    assert BLOCK_START not in leftover
    assert "python_refactor" not in leftover


def test_doctor_accepts_file_config_without_cli(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = _empty_path_env(tmp_path)
    setup(
        package_root=PACKAGE_ROOT,
        home=home,
        client="claude",
        skip_venv=True,
        skip_doctor=True,
        env=env,
    )
    result = doctor(
        package_root=PACKAGE_ROOT,
        home=home,
        client="claude",
        env=env,
        skip_probe=True,
    )
    assert result.ok
    assert any("Claude" in message for message in result.messages)
