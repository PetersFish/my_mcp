from __future__ import annotations

import libcst as cst
from libcst.metadata import QualifiedNameProvider
from pydantic import BaseModel, Field

from python_refactor_mcp.codemods.base import attribute_to_dotted, dotted_to_attribute
from python_refactor_mcp.models.errors import RefactorError


class ReplaceDecoratorParams(BaseModel):
    old: str = Field(min_length=1)
    new: str = Field(min_length=1)


class _ReplaceDecoratorTransformer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (QualifiedNameProvider,)

    def __init__(self, old: str, new: str) -> None:
        super().__init__()
        self.old = old
        self.new = new
        self.transform_count = 0

    def _decorator_expr(self, node: cst.Decorator) -> cst.BaseExpression:
        return node.decorator

    def _matches(self, expr: cst.BaseExpression) -> bool:
        # @old.route() -> Call; @old.route -> Attribute/Name
        target = expr
        if isinstance(expr, cst.Call):
            target = expr.func
        dotted = attribute_to_dotted(target)
        if dotted == self.old:
            return True
        qnames = self.get_metadata(QualifiedNameProvider, target, set())
        return any(getattr(qn, "name", None) == self.old for qn in qnames)

    def leave_Decorator(
        self, original_node: cst.Decorator, updated_node: cst.Decorator
    ) -> cst.Decorator:
        expr = self._decorator_expr(original_node)
        if not self._matches(expr):
            return updated_node
        self.transform_count += 1
        if isinstance(updated_node.decorator, cst.Call):
            new_func = dotted_to_attribute(self.new)
            return updated_node.with_changes(
                decorator=updated_node.decorator.with_changes(func=new_func)
            )
        return updated_node.with_changes(decorator=dotted_to_attribute(self.new))


class ReplaceDecoratorCodemod:
    id = "replace_decorator"
    description = "Replace a decorator qualified name."
    params_model = ReplaceDecoratorParams

    def validate_params(self, params: dict[str, object] | None) -> ReplaceDecoratorParams:
        try:
            return ReplaceDecoratorParams.model_validate(params or {})
        except Exception as exc:
            raise RefactorError(
                "CODEMOD_VALIDATION_ERROR",
                f"invalid params for {self.id}",
            ) from exc

    def transform(self, params: BaseModel) -> cst.CSTTransformer:
        assert isinstance(params, ReplaceDecoratorParams)
        return _ReplaceDecoratorTransformer(params.old, params.new)


def build_transformer(params: BaseModel) -> cst.CSTTransformer:
    assert isinstance(params, ReplaceDecoratorParams)
    return _ReplaceDecoratorTransformer(params.old, params.new)
