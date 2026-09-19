from __future__ import annotations

from typing import Protocol

import libcst as cst
from pydantic import BaseModel


class CodemodDefinition(Protocol):
    id: str
    description: str

    def validate_params(self, params: dict[str, object] | None) -> BaseModel: ...

    def transform(self, params: BaseModel) -> cst.CSTTransformer: ...


def dotted_to_attribute(dotted: str) -> cst.BaseExpression:
    parts = dotted.split(".")
    node: cst.BaseExpression = cst.Name(parts[0])
    for part in parts[1:]:
        node = cst.Attribute(value=node, attr=cst.Name(part))
    return node


def attribute_to_dotted(node: cst.BaseExpression) -> str | None:
    if isinstance(node, cst.Name):
        return node.value
    if isinstance(node, cst.Attribute):
        left = attribute_to_dotted(node.value)
        if left is None:
            return None
        return f"{left}.{node.attr.value}"
    return None


def matches_qualified_name(node: cst.CSTNode, target: str, *, provider: object) -> bool:
    """Return True if metadata QualifiedNameProvider names the node as *target*."""
    from libcst.metadata import QualifiedNameProvider

    get_metadata = getattr(provider, "get_metadata", None)
    if get_metadata is None:
        return False
    qnames = get_metadata(QualifiedNameProvider, node, set())
    return any(getattr(qn, "name", None) == target for qn in qnames)
