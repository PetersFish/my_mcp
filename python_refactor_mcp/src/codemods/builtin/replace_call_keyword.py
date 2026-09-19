from __future__ import annotations

import libcst as cst
from libcst.metadata import QualifiedNameProvider
from pydantic import BaseModel, Field

from python_refactor_mcp.codemods.base import attribute_to_dotted
from python_refactor_mcp.models.errors import RefactorError


class ReplaceCallKeywordParams(BaseModel):
    function: str = Field(min_length=1)
    old: str = Field(min_length=1)
    new: str = Field(min_length=1)


class _ReplaceCallKeywordTransformer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (QualifiedNameProvider,)

    def __init__(self, function: str, old: str, new: str) -> None:
        super().__init__()
        self.function = function
        self.old = old
        self.new = new
        self.transform_count = 0

    def _callee_matches(self, func: cst.BaseExpression) -> bool:
        dotted = attribute_to_dotted(func)
        if dotted == self.function:
            return True
        qnames = self.get_metadata(QualifiedNameProvider, func, set())
        return any(getattr(qn, "name", None) == self.function for qn in qnames)

    def leave_Call(
        self, original_node: cst.Call, updated_node: cst.Call
    ) -> cst.Call:
        if not self._callee_matches(original_node.func):
            return updated_node
        new_args: list[cst.Arg] = []
        changed = False
        for arg in updated_node.args:
            if (
                arg.keyword is not None
                and isinstance(arg.keyword, cst.Name)
                and arg.keyword.value == self.old
            ):
                changed = True
                self.transform_count += 1
                new_args.append(arg.with_changes(keyword=cst.Name(self.new)))
            else:
                new_args.append(arg)
        if changed:
            return updated_node.with_changes(args=new_args)
        return updated_node


class ReplaceCallKeywordCodemod:
    id = "replace_call_keyword"
    description = "Rename a keyword argument on a qualified function call."
    params_model = ReplaceCallKeywordParams

    def validate_params(self, params: dict[str, object] | None) -> ReplaceCallKeywordParams:
        try:
            return ReplaceCallKeywordParams.model_validate(params or {})
        except Exception as exc:
            raise RefactorError(
                "CODEMOD_VALIDATION_ERROR",
                f"invalid params for {self.id}",
            ) from exc

    def transform(self, params: BaseModel) -> cst.CSTTransformer:
        assert isinstance(params, ReplaceCallKeywordParams)
        return _ReplaceCallKeywordTransformer(params.function, params.old, params.new)


def build_transformer(params: BaseModel) -> cst.CSTTransformer:
    assert isinstance(params, ReplaceCallKeywordParams)
    return _ReplaceCallKeywordTransformer(params.function, params.old, params.new)
