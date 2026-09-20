from __future__ import annotations

from pathlib import Path

import pytest

from python_refactor_mcp.models.errors import RefactorError
from python_refactor_mcp.services.codemod_service import CodemodService


@pytest.fixture
def codemod_pkg(tmp_path: Path) -> Path:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "client.py").write_text(
        "\n".join(
            [
                "from old.mod import Foo",
                "",
                "def run(client):",
                "    client.request(url='/x')",
                "    return Foo()",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (pkg / "routes.py").write_text(
        "\n".join(
            [
                "from old import route",
                "",
                "@old.route('/hi')",
                "def hello():",
                "    return 'ok'",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    # Fix routes to use attribute form consistently
    (pkg / "routes.py").write_text(
        "\n".join(
            [
                "import old",
                "",
                "@old.route('/hi')",
                "def hello():",
                "    return 'ok'",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return tmp_path


def test_replace_qualified_name_dry_run_no_writes(codemod_pkg: Path) -> None:
    client = codemod_pkg / "pkg" / "client.py"
    before = client.read_text(encoding="utf-8")
    result = CodemodService().apply(
        codemod_pkg,
        codemod="replace_qualified_name",
        params={"old": "old.mod.Foo", "new": "new.mod.Foo"},
        dry_run=True,
    )
    assert result.status == "success"
    assert result.dry_run is True
    assert result.files_matched >= 1
    assert result.files_changed == 0
    assert client.read_text(encoding="utf-8") == before


def test_replace_qualified_name_apply(codemod_pkg: Path) -> None:
    result = CodemodService().apply(
        codemod_pkg,
        codemod="replace_qualified_name",
        params={"old": "old.mod.Foo", "new": "new.mod.Foo"},
        dry_run=False,
    )
    assert result.status == "success"
    text = (codemod_pkg / "pkg" / "client.py").read_text(encoding="utf-8")
    assert "from new.mod import Foo" in text
    assert "from old.mod import Foo" not in text


def test_normalize_imports_rewrites_safe_qualified_module_use(tmp_path: Path) -> None:
    target = tmp_path / "consumer.py"
    target.write_text(
        "import app.services.report_ops\n"
        "\n"
        "\n"
        "def run() -> int:\n"
        "    return app.services.report_ops.build_report()\n",
        encoding="utf-8",
    )

    preview = CodemodService().apply(
        tmp_path,
        codemod="normalize_imports",
        dry_run=True,
    )

    assert preview.status == "success"
    assert preview.files_matched == 1
    assert target.read_text(encoding="utf-8") == (
        "import app.services.report_ops\n"
        "\n"
        "\n"
        "def run() -> int:\n"
        "    return app.services.report_ops.build_report()\n"
    )

    result = CodemodService().apply(
        tmp_path,
        codemod="normalize_imports",
        dry_run=False,
    )

    assert result.status == "success"
    assert target.read_text(encoding="utf-8") == (
        "import app.services.report_ops\n"
        "from app.services.report_ops import build_report\n"
        "\n"
        "\n"
        "def run() -> int:\n"
        "    return build_report()\n"
    )


def test_normalize_imports_skips_unsafe_bindings(tmp_path: Path) -> None:
    target = tmp_path / "consumer.py"
    source = (
        "import app.services.report_ops\n"
        "\n"
        "\n"
        "def run(app) -> int:\n"
        "    return app.services.report_ops.build_report()\n"
    )
    target.write_text(source, encoding="utf-8")

    result = CodemodService().apply(
        tmp_path,
        codemod="normalize_imports",
        dry_run=False,
    )

    assert result.status == "success"
    assert result.files_matched == 0
    assert target.read_text(encoding="utf-8") == source


def test_normalize_imports_skips_aliases_and_module_object_use(tmp_path: Path) -> None:
    target = tmp_path / "consumer.py"
    source = (
        "import app.services.report_ops as report_ops\n"
        "\n"
        "\n"
        "def run() -> object:\n"
        "    return report_ops\n"
    )
    target.write_text(source, encoding="utf-8")

    result = CodemodService().apply(
        tmp_path,
        codemod="normalize_imports",
        dry_run=False,
    )

    assert result.status == "success"
    assert result.files_matched == 0
    assert target.read_text(encoding="utf-8") == source


@pytest.mark.parametrize(
    "binding",
    [
        "    for app in items:\n        return app.services.report_ops.build_report()\n",
        "    with context() as app:\n        return app.services.report_ops.build_report()\n",
        "    return app.services.report_ops.build_report()\n",
    ],
)
def test_normalize_imports_skips_shadowed_bindings(
    tmp_path: Path,
    binding: str,
) -> None:
    target = tmp_path / "consumer.py"
    source = (
        "import app.services.report_ops\n"
        "import other as build_report\n"
        "\n"
        "def run(items, context) -> object:\n"
        f"{binding}"
    )
    target.write_text(source, encoding="utf-8")

    result = CodemodService().apply(
        tmp_path,
        codemod="normalize_imports",
        dry_run=False,
    )

    assert result.status == "success"
    assert result.files_matched == 0
    assert target.read_text(encoding="utf-8") == source


@pytest.mark.parametrize(
    "source",
    [
        "import app.services.report_ops\n"
        "import other.deep as app\n\n"
        "def run() -> object:\n"
        "    return app.services.report_ops.build_report()\n",
        "import app.services.report_ops\n\n"
        "def run() -> object:\n"
        "    return app.services\n",
        "import app.services.report_ops\n\n"
        "def run(value) -> object:\n"
        "    app.services.report_ops.build_report = value\n"
        "    return value\n",
        "import app.services.report_ops\n\n"
        "def run() -> None:\n"
        "    del app.services.report_ops.build_report\n",
        "import app.services.report_ops\n\n"
        "def run() -> None:\n"
        "    del app.services.report_ops.handlers[\"x\"]\n",
        "from other import *\n"
        "import app.services.report_ops\n\n"
        "def run() -> object:\n"
        "    return app.services.report_ops.build_report()\n",
        "import app.services.report_ops\n\n"
        "def run(items) -> object:\n"
        "    return [app.services.report_ops.build_report() for app in items]\n",
    ],
)
def test_normalize_imports_skips_ambiguous_module_usage(
    tmp_path: Path,
    source: str,
) -> None:
    target = tmp_path / "consumer.py"
    target.write_text(source, encoding="utf-8")

    result = CodemodService().apply(
        tmp_path,
        codemod="normalize_imports",
        dry_run=False,
    )

    assert result.status == "success"
    assert result.files_matched == 0
    assert target.read_text(encoding="utf-8") == source


def test_replace_call_keyword_apply(codemod_pkg: Path) -> None:
    result = CodemodService().apply(
        codemod_pkg,
        codemod="replace_call_keyword",
        params={"function": "client.request", "old": "url", "new": "endpoint"},
        dry_run=False,
    )
    assert result.status == "success"
    text = (codemod_pkg / "pkg" / "client.py").read_text(encoding="utf-8")
    assert "endpoint=" in text
    assert "url=" not in text


def test_replace_decorator_apply(codemod_pkg: Path) -> None:
    result = CodemodService().apply(
        codemod_pkg,
        codemod="replace_decorator",
        params={"old": "old.route", "new": "new.route"},
        dry_run=False,
    )
    assert result.status == "success"
    text = (codemod_pkg / "pkg" / "routes.py").read_text(encoding="utf-8")
    assert "@new.route" in text
    assert "@old.route" not in text


def test_invalid_params_validation_error(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    result = CodemodService().apply(
        tmp_path,
        codemod="replace_qualified_name",
        params={},
        dry_run=True,
    )
    assert result.status == "error"
    assert result.code == "CODEMOD_VALIDATION_ERROR"


def test_validate_params_raises_refactor_error() -> None:
    from python_refactor_mcp.codemods.builtin import default_registry

    with pytest.raises(RefactorError) as exc:
        default_registry().validate_params("replace_call_keyword", {"function": "x"})
    assert exc.value.code == "CODEMOD_VALIDATION_ERROR"
