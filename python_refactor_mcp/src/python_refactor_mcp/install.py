from __future__ import annotations

import json
import locale
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

SERVER_NAME = "python-refactor"
SKILL_NAME = "python-refactor"
BLOCK_START = "<!-- python-refactor-mcp:start -->"
BLOCK_END = "<!-- python-refactor-mcp:end -->"
OPENCODE_SCHEMA = "https://opencode.ai/config.json"


@dataclass
class ParsedArgs:
    command: str | None = None
    client: str = "all"
    yes: bool = False
    purge: bool = False


@dataclass
class CommandResult:
    ok: bool
    messages: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def parse_args(argv: list[str]) -> ParsedArgs:
    rest = list(argv)
    parsed = ParsedArgs()
    if rest and not rest[0].startswith("-"):
        command = rest.pop(0)
        if command not in {"setup", "doctor", "uninstall"}:
            raise ValueError(f"未知命令: {command}")
        parsed.command = command
    while rest:
        arg = rest.pop(0)
        if arg in {"--yes", "-y"}:
            parsed.yes = True
        elif arg == "--purge":
            parsed.purge = True
        elif arg == "--client":
            if not rest:
                raise ValueError("--client 需要值")
            value = rest.pop(0)
            if value not in {"all", "cursor", "claude", "opencode"}:
                raise ValueError(f"无效的 --client: {value}")
            parsed.client = value
        else:
            raise ValueError(f"未知参数: {arg}")
    return parsed


def package_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def venv_python(package_root: Path) -> Path:
    if os.name == "nt":
        return package_root / ".venv" / "Scripts" / "python.exe"
    return package_root / ".venv" / "bin" / "python"


def wrapper_path(package_root: Path) -> Path:
    return package_root / "bin" / "python-refactor-mcp"


def skill_source_dir(package_root: Path) -> Path:
    return package_root / "skills" / SKILL_NAME


def cursor_mcp_path(home: Path) -> Path:
    return home / ".cursor" / "mcp.json"


def cursor_skill_dir(home: Path) -> Path:
    return home / ".cursor" / "skills" / SKILL_NAME


def claude_skill_dir(home: Path) -> Path:
    return home / ".claude" / "skills" / SKILL_NAME


def opencode_skill_dir(home: Path) -> Path:
    return home / ".config" / "opencode" / "skills" / SKILL_NAME


def claude_json_path(home: Path) -> Path:
    return home / ".claude.json"


def claude_md_path(home: Path) -> Path:
    return home / ".claude" / "CLAUDE.md"


def opencode_json_path(home: Path) -> Path:
    return home / ".config" / "opencode" / "opencode.json"


def opencode_jsonc_path(home: Path) -> Path:
    return home / ".config" / "opencode" / "opencode.jsonc"


def opencode_agents_md_path(home: Path) -> Path:
    return home / ".config" / "opencode" / "AGENTS.md"


def wants_client(client: str, name: str) -> bool:
    return client == "all" or client == name


def copy_skill(src_dir: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for item in src_dir.iterdir():
        if item.is_file() and not item.name.startswith("."):
            shutil.copy2(item, dest_dir / item.name)


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _server_config(package_root: Path) -> dict[str, object]:
    python = venv_python(package_root)
    command = str(python if python.exists() else sys.executable)
    return {
        "command": command,
        "args": ["-m", "python_refactor_mcp"],
        "cwd": str(package_root),
    }


def _opencode_server_entry(package_root: Path) -> dict[str, object]:
    python = str(venv_python(package_root) if venv_python(package_root).exists() else sys.executable)
    return {
        "type": "local",
        "command": [python, "-m", "python_refactor_mcp"],
        "enabled": True,
    }


def _python_bin(package_root: Path) -> str:
    python = venv_python(package_root)
    return str(python if python.exists() else sys.executable)


def skill_instruction_body(package_root: Path) -> str:
    text = (skill_source_dir(package_root) / "SKILL.md").read_text(encoding="utf-8")
    if text.startswith("---"):
        rest = text[3:]
        end = rest.find("\n---")
        if end != -1:
            text = rest[end + 4:].lstrip("\n")
    return text.strip() + "\n"


def upsert_marked_block(path: Path, body: str) -> None:
    block = f"{BLOCK_START}\n{body.rstrip()}\n{BLOCK_END}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    start = text.find(BLOCK_START)
    end = text.find(BLOCK_END)
    if start != -1 and end != -1 and end > start:
        end_at = end + len(BLOCK_END)
        if end_at < len(text) and text[end_at] == "\n":
            end_at += 1
        new_text = text[:start] + block + text[end_at:]
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        if text:
            text += "\n"
        new_text = text + block
    path.write_text(new_text, encoding="utf-8")


def remove_marked_block(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    start = text.find(BLOCK_START)
    end = text.find(BLOCK_END)
    if start == -1 or end == -1 or end < start:
        return False
    end_at = end + len(BLOCK_END)
    if end_at < len(text) and text[end_at] == "\n":
        end_at += 1
    new_text = text[:start] + text[end_at:]
    path.write_text(new_text, encoding="utf-8")
    return True


def install_instruction_files(home: Path, package_root: Path, client: str, messages: list[str]) -> None:
    body = skill_instruction_body(package_root)
    if wants_client(client, "claude"):
        path = claude_md_path(home)
        upsert_marked_block(path, body)
        messages.append(f"已写入指令到 {path}")
    if wants_client(client, "opencode"):
        agents = opencode_agents_md_path(home)
        upsert_marked_block(agents, body)
        messages.append(f"已写入指令到 {agents}")


def purge_instruction_files(home: Path, client: str, messages: list[str]) -> None:
    paths: list[Path] = []
    if wants_client(client, "claude"):
        paths.append(claude_md_path(home))
    if wants_client(client, "opencode"):
        paths.append(opencode_agents_md_path(home))
    removed = [str(path) for path in paths if remove_marked_block(path)]
    if removed:
        messages.append("已从指令文件移除 python-refactor 标记块")


def register_cursor(home: Path, package_root: Path, messages: list[str]) -> None:
    path = cursor_mcp_path(home)
    data = _load_json(path)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers
    servers[SERVER_NAME] = _server_config(package_root)
    _write_json(path, data)
    messages.append(f"已注册 Cursor MCP: {path}")


def unregister_cursor(home: Path, messages: list[str]) -> None:
    path = cursor_mcp_path(home)
    data = _load_json(path)
    servers = data.get("mcpServers")
    if isinstance(servers, dict) and SERVER_NAME in servers:
        del servers[SERVER_NAME]
        _write_json(path, data)
        messages.append("已从 Cursor 移除 python-refactor")


def find_command(name: str, env: dict[str, str] | None = None) -> str | None:
    return shutil.which(name, path=(env or os.environ).get("PATH"))


def _decode_captured(stream: bytes) -> str:
    preferred = locale.getpreferredencoding(False)
    try:
        return stream.decode(preferred)
    except UnicodeDecodeError:
        return stream.decode("utf-8", errors="replace")


def _run(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    raw = subprocess.run(command, env=env, capture_output=True)
    stdout = _decode_captured(raw.stdout or b"")
    stderr = _decode_captured(raw.stderr or b"")
    return subprocess.CompletedProcess(raw.args, raw.returncode, stdout, stderr)


def write_claude_mcp(home: Path, package_root: Path, messages: list[str]) -> None:
    path = claude_json_path(home)
    data = _load_json(path)
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers
    servers[SERVER_NAME] = _server_config(package_root)
    _write_json(path, data)
    messages.append(f"已写入 Claude Code MCP 配置: {path}")


def write_opencode_mcp(home: Path, package_root: Path, messages: list[str]) -> None:
    path = opencode_json_path(home)
    data = _load_json(path)
    mcp = data.get("mcp")
    if not isinstance(mcp, dict):
        mcp = {}
        data["mcp"] = mcp
    entry = _opencode_server_entry(package_root)
    # OpenCode schema: mcp.<name> is McpLocalConfig|McpRemoteConfig — NOT mcp.servers.<name>.
    legacy_servers = mcp.get("servers")
    mcp[SERVER_NAME] = entry
    if isinstance(legacy_servers, dict) and SERVER_NAME in legacy_servers:
        del legacy_servers[SERVER_NAME]
        if not legacy_servers:
            del mcp["servers"]
    if "$schema" not in data:
        data["$schema"] = OPENCODE_SCHEMA
    _write_json(path, data)
    messages.append(f"已写入 OpenCode MCP 配置: {path}")


def register_claude(
    home: Path,
    env: dict[str, str],
    package_root: Path,
    messages: list[str],
) -> None:
    claude = find_command("claude", env)
    python = _python_bin(package_root)
    if claude:
        _run([claude, "mcp", "remove", "--scope", "user", SERVER_NAME], env)
        result = _run(
            [
                claude,
                "mcp",
                "add",
                "--scope",
                "user",
                "--transport",
                "stdio",
                SERVER_NAME,
                "--",
                python,
                "-m",
                "python_refactor_mcp",
            ],
            env,
        )
        if result.returncode == 0:
            messages.append("已注册 Claude Code MCP（user scope）: python-refactor")
            return
        messages.append("claude mcp add 失败，改写 ~/.claude.json")
    else:
        messages.append("未找到 claude CLI，改写 ~/.claude.json")
    write_claude_mcp(home, package_root, messages)


def register_opencode(
    home: Path,
    env: dict[str, str],
    package_root: Path,
    messages: list[str],
) -> None:
    opencode = find_command("opencode", env)
    python = _python_bin(package_root)
    if opencode:
        args = ["mcp", "add", "--global", SERVER_NAME, "--", python, "-m", "python_refactor_mcp"]
        result = _run([opencode, *args], env)
        if result.returncode != 0:
            result = _run(
                [opencode, "mcp", "add", "--global", "--force", SERVER_NAME, "--", python, "-m", "python_refactor_mcp"],
                env,
            )
        if result.returncode == 0:
            messages.append("已注册 OpenCode MCP（global）: python-refactor")
            return
        messages.append("opencode mcp add 失败，改写配置文件")
    else:
        messages.append("未找到 opencode CLI，改写配置文件")
    write_opencode_mcp(home, package_root, messages)


def unregister_claude(home: Path, env: dict[str, str], messages: list[str]) -> None:
    claude = find_command("claude", env)
    if claude:
        _run([claude, "mcp", "remove", "--scope", "user", SERVER_NAME], env)
    path = claude_json_path(home)
    data = _load_json(path)
    servers = data.get("mcpServers")
    if isinstance(servers, dict) and SERVER_NAME in servers:
        del servers[SERVER_NAME]
        _write_json(path, data)
        messages.append("已从 Claude Code 移除 python-refactor")
    elif claude:
        messages.append("已从 Claude Code 移除 python-refactor")


def unregister_opencode(home: Path, env: dict[str, str], messages: list[str]) -> None:
    opencode = find_command("opencode", env)
    if opencode:
        _run([opencode, "mcp", "remove", "--global", SERVER_NAME], env)
        _run([opencode, "mcp", "remove", SERVER_NAME], env)
    changed_any = False
    for file in (opencode_json_path(home), opencode_jsonc_path(home)):
        data = _load_json(file)
        if not data:
            continue
        changed = False
        mcp = data.get("mcp")
        if isinstance(mcp, dict):
            servers = mcp.get("servers")
            if isinstance(servers, dict) and SERVER_NAME in servers:
                del servers[SERVER_NAME]
                if not servers:
                    del mcp["servers"]
                changed = True
            if SERVER_NAME in mcp:
                del mcp[SERVER_NAME]
                changed = True
        if changed:
            _write_json(file, data)
            changed_any = True
    if changed_any or opencode:
        messages.append("已从 OpenCode 配置移除 python-refactor（若存在）")


def ensure_venv(package_root: Path, messages: list[str]) -> None:
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("需要 uv 来创建虚拟环境。请先安装 uv。")
    venv_dir = package_root / ".venv"
    if not venv_dir.exists():
        raw = subprocess.run([uv, "venv", str(venv_dir)], cwd=package_root, capture_output=True)
        stdout = _decode_captured(raw.stdout or b"")
        stderr = _decode_captured(raw.stderr or b"")
        if raw.returncode != 0:
            raise RuntimeError(f"uv venv 失败: {(stderr or stdout).strip()}")
    python = venv_python(package_root)
    raw = subprocess.run(
        [uv, "pip", "install", "--python", str(python), "-e", "."],
        cwd=package_root,
        capture_output=True,
    )
    stdout = _decode_captured(raw.stdout or b"")
    stderr = _decode_captured(raw.stderr or b"")
    if raw.returncode != 0:
        raise RuntimeError(f"uv pip install 失败: {(stderr or stdout).strip()}")
    messages.append(f"已准备虚拟环境 {venv_dir}")


def probe_mcp_initialize(package_root: Path, env: dict[str, str]) -> None:
    python = venv_python(package_root)
    command = [str(python if python.exists() else sys.executable), "-m", "python_refactor_mcp"]
    proc = subprocess.Popen(
        command,
        cwd=package_root,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    request = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "python-refactor-doctor", "version": "0.1.0"},
            },
        }
    )
    assert proc.stdin is not None
    try:
        proc.stdin.write(request.encode("utf-8") + b"\n")
        proc.stdin.flush()
        stdout = ""
        deadline = time.time() + 15
        while time.time() < deadline:
            if proc.poll() is not None:
                stderr_raw = proc.stderr.read() if proc.stderr else b""
                stderr = _decode_captured(stderr_raw or b"")
                raise RuntimeError(stderr.strip() or f"MCP 进程退出码 {proc.returncode}")
            line_raw = proc.stdout.readline() if proc.stdout else b""
            if not line_raw:
                time.sleep(0.05)
                continue
            line = _decode_captured(line_raw)
            stdout += line
            if '"result"' in stdout or '"id": 1' in stdout or '"id":1' in stdout:
                return
        stderr_raw = proc.stderr.read() if proc.stderr else b""
        raise RuntimeError(_decode_captured(stderr_raw or b"") or "MCP initialize 超时")
    finally:
        proc.kill()
        proc.wait(timeout=5)


def setup(
    *,
    package_root: Path,
    home: Path,
    client: str = "all",
    skip_venv: bool = False,
    skip_doctor: bool = False,
    env: dict[str, str] | None = None,
) -> CommandResult:
    env = env or os.environ.copy()
    messages: list[str] = []
    if not skip_venv:
        ensure_venv(package_root, messages)
    if wants_client(client, "cursor"):
        register_cursor(home, package_root, messages)
        copy_skill(skill_source_dir(package_root), cursor_skill_dir(home))
        messages.append(f"已安装 skill 到 {cursor_skill_dir(home)}")
    if wants_client(client, "claude"):
        register_claude(home, env, package_root, messages)
        copy_skill(skill_source_dir(package_root), claude_skill_dir(home))
        messages.append(f"已安装 skill 到 {claude_skill_dir(home)}")
    if wants_client(client, "opencode"):
        register_opencode(home, env, package_root, messages)
        copy_skill(skill_source_dir(package_root), opencode_skill_dir(home))
        messages.append(f"已安装 skill 到 {opencode_skill_dir(home)}")
    install_instruction_files(home, package_root, client, messages)
    if skip_doctor:
        return CommandResult(ok=True, messages=messages)
    health = doctor(package_root=package_root, home=home, client=client, env=env)
    messages.extend(health.messages)
    return CommandResult(ok=health.ok, messages=messages, issues=health.issues)


def _cursor_registered(home: Path) -> bool:
    servers = _load_json(cursor_mcp_path(home)).get("mcpServers")
    return isinstance(servers, dict) and SERVER_NAME in servers


def _claude_registered(home: Path) -> bool:
    servers = _load_json(claude_json_path(home)).get("mcpServers")
    return isinstance(servers, dict) and SERVER_NAME in servers


def _opencode_registered(home: Path) -> bool:
    for file in (opencode_json_path(home), opencode_jsonc_path(home)):
        mcp = _load_json(file).get("mcp")
        if not isinstance(mcp, dict):
            continue
        if SERVER_NAME in mcp:
            return True
        servers = mcp.get("servers")
        if isinstance(servers, dict) and SERVER_NAME in servers:
            return True
    return False


def _cli_lists_server(bin_name: str, env: dict[str, str]) -> bool | None:
    command = find_command(bin_name, env)
    if not command:
        return None
    result = _run([command, "mcp", "list"], env)
    return SERVER_NAME in f"{result.stdout}\n{result.stderr}"


def doctor(
    *,
    package_root: Path,
    home: Path,
    client: str = "all",
    env: dict[str, str] | None = None,
    skip_probe: bool = False,
) -> CommandResult:
    env = env or os.environ.copy()
    issues: list[str] = []
    messages: list[str] = []
    python = venv_python(package_root)
    if not python.exists():
        issues.append(f"缺少虚拟环境解释器: {python}")
    if wants_client(client, "cursor"):
        if _cursor_registered(home):
            messages.append("Cursor: python-refactor 已注册")
        else:
            issues.append("Cursor mcp.json 未看到 python-refactor")
    if wants_client(client, "claude"):
        listed = _cli_lists_server("claude", env)
        if _claude_registered(home) or listed is True:
            messages.append("Claude: python-refactor 已注册")
        else:
            issues.append("Claude ~/.claude.json 未看到 python-refactor")
    if wants_client(client, "opencode"):
        listed = _cli_lists_server("opencode", env)
        if _opencode_registered(home) or listed is True:
            messages.append("OpenCode: python-refactor 已注册")
        else:
            issues.append("OpenCode 配置未看到 python-refactor")
    if not skip_probe and python.exists():
        try:
            probe_mcp_initialize(package_root, env)
            messages.append("MCP initialize 成功")
        except Exception as exc:
            issues.append(f"MCP initialize 失败: {exc}")
    return CommandResult(ok=not issues, messages=messages, issues=issues)


def uninstall(
    *,
    home: Path,
    client: str = "all",
    purge: bool = False,
    env: dict[str, str] | None = None,
) -> CommandResult:
    env = env or os.environ.copy()
    messages: list[str] = []
    if wants_client(client, "cursor"):
        unregister_cursor(home, messages)
    if wants_client(client, "claude"):
        unregister_claude(home, env, messages)
    if wants_client(client, "opencode"):
        unregister_opencode(home, env, messages)
    if purge:
        for dest in (cursor_skill_dir(home), claude_skill_dir(home), opencode_skill_dir(home)):
            shutil.rmtree(dest, ignore_errors=True)
        purge_instruction_files(home, client, messages)
        messages.append("已删除已安装 skill")
    return CommandResult(ok=True, messages=messages)


def main(argv: list[str] | None = None) -> int:
    parsed = parse_args(argv if argv is not None else sys.argv[1:])
    home = Path(os.environ.get("HOME") or os.environ.get("USERPROFILE") or Path.home())
    root = package_root_from_here()
    env = os.environ.copy()
    if parsed.command == "setup":
        result = setup(package_root=root, home=home, client=parsed.client, env=env)
    elif parsed.command == "doctor":
        result = doctor(package_root=root, home=home, client=parsed.client, env=env)
    elif parsed.command == "uninstall":
        result = uninstall(home=home, client=parsed.client, purge=parsed.purge, env=env)
    else:
        print("用法: python -m python_refactor_mcp setup|doctor|uninstall", file=sys.stderr)
        return 2
    for message in result.messages:
        print(message)
    for issue in result.issues:
        print(issue, file=sys.stderr)
    return 0 if result.ok else 1
