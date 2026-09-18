from pathlib import Path

from python_refactor_mcp.packages import (
    ensure_package,
    find_empty_packages,
    module_file,
    resolve_source_root,
)


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


def test_find_empty_packages_walks_empty_parents(tmp_path: Path) -> None:
    services = tmp_path / "app" / "services"
    services.mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (services / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "api.py").write_text("x = 1\n", encoding="utf-8")
    found = find_empty_packages(tmp_path, "app.services.report", tmp_path)
    assert found == ["app/services"]


def test_find_empty_packages_ignores_pycache_and_stops_on_content(tmp_path: Path) -> None:
    services = tmp_path / "app" / "services"
    services.mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("# keep app\n", encoding="utf-8")
    (services / "__init__.py").write_text("", encoding="utf-8")
    cache = services / "__pycache__"
    cache.mkdir()
    (cache / "x.pyc").write_text("", encoding="utf-8")
    found = find_empty_packages(tmp_path, "app.services.report", tmp_path)
    assert found == ["app/services"]


def test_find_empty_packages_reports_source_package_own_dir(tmp_path: Path) -> None:
    reporting = tmp_path / "app" / "reporting"
    reporting.mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (reporting / "__init__.py").write_text("", encoding="utf-8")
    found = find_empty_packages(tmp_path, "app.reporting", tmp_path)
    assert found == ["app/reporting"]


def test_find_empty_packages_stops_at_parent_holding_surviving_child(tmp_path: Path) -> None:
    inner = tmp_path / "app" / "services" / "legacy"
    inner.mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "app" / "services" / "__init__.py").write_text("", encoding="utf-8")
    (inner / "__init__.py").write_text("", encoding="utf-8")
    found = find_empty_packages(tmp_path, "app.services.legacy", tmp_path)
    assert found == ["app/services/legacy"]


def test_find_empty_packages_ignores_dir_without_init(tmp_path: Path) -> None:
    services = tmp_path / "app" / "services"
    services.mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    assert find_empty_packages(tmp_path, "app.services.report", tmp_path) == []


def test_find_empty_packages_skips_nonempty_init(tmp_path: Path) -> None:
    services = tmp_path / "app" / "services"
    services.mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (services / "__init__.py").write_text("from . import report\n", encoding="utf-8")
    assert find_empty_packages(tmp_path, "app.services.report", tmp_path) == []
