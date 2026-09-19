from __future__ import annotations

import libcst as cst
from libcst.metadata import ParentNodeProvider, QualifiedNameProvider
from pydantic import BaseModel, Field

from python_refactor_mcp.codemods.base import attribute_to_dotted, dotted_to_attribute
from python_refactor_mcp.models.errors import RefactorError


class ReplaceQualifiedNameParams(BaseModel):
    old: str = Field(min_length=1)
    new: str = Field(min_length=1)


def _is_import_context(transformer: cst.CSTTransformer, node: cst.CSTNode) -> bool:
    parent = transformer.get_metadata(ParentNodeProvider, node, None)
    while parent is not None:
        if isinstance(parent, (cst.Import, cst.ImportFrom, cst.ImportAlias)):
            return True
        parent = transformer.get_metadata(ParentNodeProvider, parent, None)
    return False


class _ReplaceQualifiedNameTransformer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (QualifiedNameProvider, ParentNodeProvider)

    def __init__(self, old: str, new: str) -> None:
        super().__init__()
        self.old = old
        self.new = new
        self.transform_count = 0
        self._old_parts = old.split(".")
        self._new_parts = new.split(".")

    def leave_ImportFrom(
        self, original_node: cst.ImportFrom, updated_node: cst.ImportFrom
    ) -> cst.ImportFrom:
        if updated_node.module is None or isinstance(updated_node.names, cst.ImportStar):
            return updated_node
        module_name = attribute_to_dotted(updated_node.module)
        if module_name is None:
            return updated_node

        if len(self._old_parts) >= 2 and module_name == ".".join(self._old_parts[:-1]):
            leaf = self._old_parts[-1]
            new_leaf = self._new_parts[-1]
            new_module = ".".join(self._new_parts[:-1])
            changed = False
            new_names: list[cst.ImportAlias] = []
            for alias in updated_node.names:
                if isinstance(alias.name, cst.Name) and alias.name.value == leaf:
                    changed = True
                    self.transform_count += 1
                    new_names.append(alias.with_changes(name=cst.Name(new_leaf)))
                else:
                    new_names.append(alias)
            if changed:
                return updated_node.with_changes(
                    module=dotted_to_attribute(new_module),
                    names=new_names,
                )

        if module_name == self.old:
            self.transform_count += 1
            return updated_node.with_changes(module=dotted_to_attribute(self.new))

        if module_name.startswith(self.old + "."):
            suffix = module_name[len(self.old) :]
            self.transform_count += 1
            return updated_node.with_changes(
                module=dotted_to_attribute(self.new + suffix)
            )
        return updated_node

    def leave_Import(
        self, original_node: cst.Import, updated_node: cst.Import
    ) -> cst.Import:
        new_names: list[cst.ImportAlias] = []
        changed = False
        for alias in updated_node.names:
            dotted = attribute_to_dotted(alias.name)
            if dotted == self.old:
                changed = True
                self.transform_count += 1
                new_names.append(alias.with_changes(name=dotted_to_attribute(self.new)))
            elif dotted is not None and dotted.startswith(self.old + "."):
                changed = True
                self.transform_count += 1
                suffix = dotted[len(self.old) :]
                new_names.append(
                    alias.with_changes(name=dotted_to_attribute(self.new + suffix))
                )
            else:
                new_names.append(alias)
        if changed:
            return updated_node.with_changes(names=new_names)
        return updated_node

    def leave_Attribute(
        self, original_node: cst.Attribute, updated_node: cst.Attribute
    ) -> cst.BaseExpression:
        if _is_import_context(self, original_node):
            return updated_node
        dotted = attribute_to_dotted(original_node)
        if dotted == self.old:
            self.transform_count += 1
            return dotted_to_attribute(self.new)
        qnames = self.get_metadata(QualifiedNameProvider, original_node, set())
        if any(getattr(qn, "name", None) == self.old for qn in qnames):
            self.transform_count += 1
            return dotted_to_attribute(self.new)
        return updated_node

    def leave_Name(
        self, original_node: cst.Name, updated_node: cst.Name
    ) -> cst.BaseExpression:
        if _is_import_context(self, original_node):
            return updated_node
        if len(self._old_parts) == 1 and original_node.value == self.old:
            self.transform_count += 1
            return (
                cst.Name(self.new)
                if len(self._new_parts) == 1
                else dotted_to_attribute(self.new)
            )
        qnames = self.get_metadata(QualifiedNameProvider, original_node, set())
        if any(getattr(qn, "name", None) == self.old for qn in qnames):
            self.transform_count += 1
            if len(self._new_parts) == 1:
                return cst.Name(self._new_parts[0])
            # Keep simple local name when only the defining module path changed.
            if self._old_parts[-1] == self._new_parts[-1]:
                return updated_node
            return dotted_to_attribute(self.new)
        return updated_node


class ReplaceQualifiedNameCodemod:
    id = "replace_qualified_name"
    description = "Replace a qualified name across imports and references."
    params_model = ReplaceQualifiedNameParams

    def validate_params(self, params: dict[str, object] | None) -> ReplaceQualifiedNameParams:
        try:
            return ReplaceQualifiedNameParams.model_validate(params or {})
        except Exception as exc:
            raise RefactorError(
                "CODEMOD_VALIDATION_ERROR",
                f"invalid params for {self.id}",
            ) from exc

    def transform(self, params: BaseModel) -> cst.CSTTransformer:
        assert isinstance(params, ReplaceQualifiedNameParams)
        return _ReplaceQualifiedNameTransformer(params.old, params.new)


def build_transformer(params: BaseModel) -> cst.CSTTransformer:
    assert isinstance(params, ReplaceQualifiedNameParams)
    return _ReplaceQualifiedNameTransformer(params.old, params.new)
