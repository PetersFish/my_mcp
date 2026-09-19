from __future__ import annotations

import json
from pathlib import Path

from python_refactor_mcp.services.verification_service import _format_rg_json_match, _scan_with_rg
from python_refactor_mcp.utils.paths import uri_to_path
from python_refactor_mcp.utils.process import language_server_argv


def test_uri_to_path_unix_file_uri() -> None:
    path = uri_to_path("file:///Users/x/a.py")
    assert path.as_posix() == "/Users/x/a.py"


def test_uri_to_path_windows_drive_uri() -> None:
    path = uri_to_path("file:///C:/Users/x/a.py")
    assert path.as_posix().replace("\\", "/").endswith("Users/x/a.py")
    text = path.as_posix()
    assert text.startswith("C:") or (len(path.parts) >= 1 and "C:" in path.parts[0])
    assert path.name == "a.py"


def test_language_server_argv_plain() -> None:
    argv = language_server_argv(Path("/usr/bin/pyright-langserver"))
    assert argv == ["/usr/bin/pyright-langserver", "--stdio"]


def test_language_server_argv_cmd_on_windows() -> None:
    argv = language_server_argv(
        Path("node_modules/.bin/pyright-langserver.cmd"),
        os_name="nt",
        comspec=r"C:\Windows\System32\cmd.exe",
    )
    assert argv[0].lower().endswith("cmd.exe")
    assert argv[1] == "/c"
    assert argv[2].endswith("pyright-langserver.cmd")
    assert argv[3] == "--stdio"


def test_language_server_argv_exe_on_windows() -> None:
    argv = language_server_argv(
        Path("Scripts/pyright-langserver.exe"),
        os_name="nt",
    )
    assert argv == ["Scripts/pyright-langserver.exe", "--stdio"]


def test_rg_json_preserves_windows_absolute_path(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    win_abs = r"C:\Users\x\proj\pkg\mod.py"
    event = {
        "type": "match",
        "data": {
            "path": {"text": win_abs},
            "line_number": 3,
            "lines": {"text": "from old.mod import Foo\n"},
        },
    }

    class Result:
        returncode = 0
        stdout = json.dumps(event) + "\n"
        stderr = ""

    monkeypatch.setattr(
        "python_refactor_mcp.services.verification_service.subprocess.run",
        lambda *a, **k: Result(),
    )
    count, samples = _scan_with_rg("rg", root, ["old.mod"], set())
    assert count == 1
    assert samples[0].startswith("C:/Users/x/proj/pkg/mod.py:3:") or "mod.py:3:" in samples[0]
    assert not samples[0].startswith("C:3:")
    assert "from old.mod import Foo" in samples[0]


def test_format_rg_json_match_relativizes_under_root(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    (root / "pkg").mkdir(parents=True)
    target = root / "pkg" / "mod.py"
    target.write_text("x\n", encoding="utf-8")
    sample = _format_rg_json_match(root, str(target), 1, "x")
    assert sample == "pkg/mod.py:1:x"
