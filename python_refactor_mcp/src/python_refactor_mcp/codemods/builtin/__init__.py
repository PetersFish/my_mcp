from __future__ import annotations

from python_refactor_mcp.adapters.libcst.registry import CodemodRegistry
from python_refactor_mcp.codemods.builtin.replace_call_keyword import (
    ReplaceCallKeywordCodemod,
    build_transformer as build_call_keyword,
)
from python_refactor_mcp.codemods.builtin.replace_decorator import (
    ReplaceDecoratorCodemod,
    build_transformer as build_decorator,
)
from python_refactor_mcp.codemods.builtin.replace_qualified_name import (
    ReplaceQualifiedNameCodemod,
    build_transformer as build_qualified_name,
)
from python_refactor_mcp.codemods.builtin.normalize_imports import (
    NormalizeImportsCodemod,
    build_transformer as build_normalize_imports,
)

_DEFAULT: CodemodRegistry | None = None


def default_registry() -> CodemodRegistry:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = build_builtin_registry()
    return _DEFAULT


def build_builtin_registry() -> CodemodRegistry:
    registry = CodemodRegistry()
    normalize = NormalizeImportsCodemod()
    registry.register(
        normalize.id,
        build_normalize_imports,
        normalize.params_model,
        description=normalize.description,
    )
    qn = ReplaceQualifiedNameCodemod()
    registry.register(
        qn.id,
        build_qualified_name,
        qn.params_model,
        description=qn.description,
    )
    ck = ReplaceCallKeywordCodemod()
    registry.register(
        ck.id,
        build_call_keyword,
        ck.params_model,
        description=ck.description,
    )
    dec = ReplaceDecoratorCodemod()
    registry.register(
        dec.id,
        build_decorator,
        dec.params_model,
        description=dec.description,
    )
    return registry
