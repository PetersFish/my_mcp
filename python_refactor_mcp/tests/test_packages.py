from pathlib import Path

from python_refactor_mcp.packages import ensure_package, module_file, resolve_source_root


def _write_module(root: Path, rel: str, body: str = "x = 1\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_resolve_source_root_explicit(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    assert resolve_source_root(tmp_path, "src") == src.resolve()


def test_resolve_source_root_prefers_layout_where_module_exists(tmp_path: Path) -> None:
    _write_module(tmp_path / "src", "app/services/report.py")
    found = resolve_source_root(tmp_path, None, dotted_module="app.services.report")
    assert found == (tmp_path / "src").resolve()


def test_resolve_source_root_falls_back_to_project_root(tmp_path: Path) -> None:
    _write_module(tmp_path, "app/services/report.py")
    found = resolve_source_root(tmp_path, None, dotted_module="app.services.report")
    assert found == tmp_path.resolve()


def test_ensure_package_creates_missing_init_only(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    existing = app / "__init__.py"
    existing.write_text("# keep\n", encoding="utf-8")
    created = ensure_package(tmp_path, "app.reporting.application")
    assert created == tmp_path / "app" / "reporting" / "application"
    assert existing.read_text(encoding="utf-8") == "# keep\n"
    assert (tmp_path / "app" / "reporting" / "__init__.py").read_text(encoding="utf-8") == ""
    assert (tmp_path / "app" / "reporting" / "application" / "__init__.py").exists()


def test_module_file_finds_py_and_package(tmp_path: Path) -> None:
    _write_module(tmp_path, "app/services/report.py")
    pkg = tmp_path / "app" / "api"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("v = 1\n", encoding="utf-8")
    assert module_file(tmp_path, "app.services.report") == tmp_path / "app" / "services" / "report.py"
    assert module_file(tmp_path, "app.api") == pkg / "__init__.py"
    assert module_file(tmp_path, "missing.mod") is None
