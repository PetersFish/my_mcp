from __future__ import annotations

from dataclasses import dataclass, field

import libcst as cst
from libcst.metadata import MetadataWrapper, ParentNodeProvider
from pydantic import BaseModel

from python_refactor_mcp.codemods.base import attribute_to_dotted, dotted_to_attribute
from python_refactor_mcp.models.errors import RefactorError


class NormalizeImportsParams(BaseModel):
    pass


@dataclass
class _ImportCandidate:
    module: str
    local_name: str
    symbols: set[str] = field(default_factory=set)
    module_used: bool = False
    rewritable: bool = True


class _ImportUsageCollector(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (ParentNodeProvider,)

    def __init__(self) -> None:
        super().__init__()
        self.candidates: dict[tuple[str, str], _ImportCandidate] = {}
        self.attributes: list[tuple[str, bool]] = []
        self.store_attributes: set[str] = set()
        self.bound_names: set[str] = set()
        self.bare_names: set[str] = set()
        self.import_bindings: dict[str, int] = {}
        self.has_star_import = False

    def visit_Import(self, node: cst.Import) -> bool:
        aliases = [alias for alias in node.names if isinstance(alias, cst.ImportAlias)]
        single_alias = len(aliases) == 1
        for alias in aliases:
            module = attribute_to_dotted(alias.name)
            if module is None:
                continue
            local_name = (
                attribute_to_dotted(alias.asname.name)
                if alias.asname is not None
                else module.split(".")[0]
            )
            if local_name is None:
                continue
            self.import_bindings[local_name] = self.import_bindings.get(local_name, 0) + 1
            if "." not in module:
                self.bound_names.add(local_name)
                continue
            candidate = _ImportCandidate(
                module=module,
                local_name=local_name,
                rewritable=single_alias,
            )
            self.candidates[(module, local_name)] = candidate
        # Import aliases are not usage expressions.
        return False

    def visit_ImportFrom(self, node: cst.ImportFrom) -> bool:
        if isinstance(node.names, cst.ImportStar):
            self.has_star_import = True
            return False
        for alias in node.names:
            if not isinstance(alias, cst.ImportAlias):
                continue
            name = (
                attribute_to_dotted(alias.asname.name)
                if alias.asname is not None
                else attribute_to_dotted(alias.name)
            )
            if name is not None and "." not in name:
                self.bound_names.add(name)
        return False

    def visit_Param(self, node: cst.Param) -> bool:
        name = attribute_to_dotted(node.name)
        if name is not None and "." not in name:
            self.bound_names.add(name)
        return True

    def visit_AssignTarget(self, node: cst.AssignTarget) -> bool:
        self._record_target(node.target)
        return True

    def visit_AnnAssign(self, node: cst.AnnAssign) -> bool:
        self._record_target(node.target)
        return True

    def visit_For(self, node: cst.For) -> bool:
        self._record_target(node.target)
        return True

    def visit_CompFor(self, node: cst.CompFor) -> bool:
        self._record_target(node.target)
        return True

    def visit_NamedExpr(self, node: cst.NamedExpr) -> bool:
        self._record_target(node.target)
        return True

    def visit_With(self, node: cst.With) -> bool:
        for item in node.items:
            if item.asname is not None:
                name = attribute_to_dotted(item.asname.name)
                if name is not None and "." not in name:
                    self.bound_names.add(name)
        return True

    def visit_ExceptHandler(self, node: cst.ExceptHandler) -> bool:
        if node.name is not None:
            name = attribute_to_dotted(node.name.name)
            if name is not None and "." not in name:
                self.bound_names.add(name)
        return True

    def visit_MatchAs(self, node: cst.MatchAs) -> bool:
        if node.name is not None:
            name = attribute_to_dotted(node.name)
            if name is not None and "." not in name:
                self.bound_names.add(name)
        return True

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool:
        self.bound_names.add(node.name.value)
        return True

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        self.bound_names.add(node.name.value)
        return True

    def _record_target(self, node: cst.CSTNode) -> None:
        if isinstance(node, cst.AssignTarget):
            self._record_target(node.target)
            return
        if isinstance(node, (cst.Tuple, cst.List)):
            for element in node.elements:
                if isinstance(element, cst.Element):
                    self._record_target(element.value)
            return
        if isinstance(node, cst.StarredElement):
            self._record_target(node.value)
            return
        name = attribute_to_dotted(node) if isinstance(node, cst.BaseExpression) else None
        if name is not None and "." not in name:
            self.bound_names.add(name)

    def visit_Attribute(self, node: cst.Attribute) -> bool:
        dotted = attribute_to_dotted(node)
        if dotted is not None:
            parent = self.get_metadata(ParentNodeProvider, node, None)
            is_nested = isinstance(parent, cst.Attribute)
            self.attributes.append((dotted, is_nested))
            if _is_mutation_context(self, node):
                self.store_attributes.add(dotted)
        return True

    def visit_Name(self, node: cst.Name) -> bool:
        parent = self.get_metadata(ParentNodeProvider, node, None)
        if not isinstance(parent, cst.Attribute):
            self.bare_names.add(node.value)
        return True


class _NormalizeImportsTransformer(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (ParentNodeProvider,)

    def __init__(self) -> None:
        super().__init__()
        self.transform_count = 0
        self._candidates: dict[tuple[str, str], _ImportCandidate] = {}
        self._by_module: dict[str, list[_ImportCandidate]] = {}
        self._bound_names: set[str] = set()
        self._has_star_import = False

    def visit_Module(self, node: cst.Module) -> bool:
        collector = _ImportUsageCollector()
        MetadataWrapper(node).visit(collector)
        self._candidates = collector.candidates
        self._bound_names = collector.bound_names
        self._bound_names.update(collector.bare_names)
        self._has_star_import = collector.has_star_import
        self._by_module = {}
        for candidate in self._candidates.values():
            if collector.import_bindings.get(candidate.local_name, 0) > 1:
                candidate.rewritable = False
            self._by_module.setdefault(candidate.module, []).append(candidate)

        for dotted, is_nested in collector.attributes:
            for candidate in self._by_module.get(dotted, []):
                if not is_nested:
                    candidate.module_used = True
            for candidate in self._candidates.values():
                if not is_nested and (
                    dotted == candidate.local_name
                    or candidate.module.startswith(dotted + ".")
                ):
                    candidate.module_used = True
                prefix = candidate.module + "."
                if dotted.startswith(prefix):
                    suffix = dotted[len(prefix) :]
                    if "." not in suffix:
                        candidate.symbols.add(suffix)
                    else:
                        candidate.module_used = True
        for dotted in collector.store_attributes:
            for candidate in self._candidates.values():
                if dotted == candidate.module or dotted.startswith(candidate.module + "."):
                    candidate.module_used = True
        return True

    def leave_SimpleStatementLine(
        self,
        original_node: cst.SimpleStatementLine,
        updated_node: cst.SimpleStatementLine,
    ) -> cst.BaseStatement | cst.FlattenSentinel[cst.BaseStatement]:
        if len(updated_node.body) != 1 or not isinstance(updated_node.body[0], cst.Import):
            return updated_node
        alias = updated_node.body[0].names[0] if len(updated_node.body[0].names) == 1 else None
        if alias is None:
            return updated_node
        module = attribute_to_dotted(alias.name)
        if module is None:
            return updated_node
        local_name = (
            attribute_to_dotted(alias.asname.name)
            if alias.asname is not None
            else module.split(".")[0]
        )
        if local_name is None:
            return updated_node
        candidate = self._candidates.get((module, local_name))
        if not self._can_rewrite(candidate):
            return updated_node
        assert candidate is not None
        self.transform_count += len(candidate.symbols) + 1
        names = tuple(cst.ImportAlias(name=cst.Name(symbol)) for symbol in sorted(candidate.symbols))
        module_node = dotted_to_attribute(module)
        if not isinstance(module_node, (cst.Name, cst.Attribute)):
            return updated_node
        return cst.FlattenSentinel(
            [
                updated_node,
                cst.SimpleStatementLine(body=[cst.ImportFrom(module=module_node, names=names)]),
            ]
        )

    def leave_Attribute(
        self,
        original_node: cst.Attribute,
        updated_node: cst.Attribute,
    ) -> cst.BaseExpression:
        if _is_mutation_context(self, original_node):
            return updated_node
        dotted = attribute_to_dotted(original_node)
        if dotted is None:
            return updated_node
        for candidate in self._candidates.values():
            prefix = candidate.module + "."
            if not dotted.startswith(prefix):
                continue
            symbol = dotted[len(prefix) :]
            if symbol in candidate.symbols and self._can_rewrite(candidate):
                self.transform_count += 1
                return cst.Name(symbol)
        return updated_node

    def _can_rewrite(self, candidate: _ImportCandidate | None) -> bool:
        if candidate is None:
            return False
        if (
            not candidate.symbols
            or candidate.module_used
            or not candidate.rewritable
            or self._has_star_import
        ):
            return False
        if candidate.local_name in self._bound_names:
            return False
        if self._bound_names.intersection(candidate.symbols):
            return False
        return True


def _is_mutation_context(
    transformer: cst.CSTTransformer | cst.CSTVisitor,
    node: cst.CSTNode,
) -> bool:
    parent = transformer.get_metadata(ParentNodeProvider, node, None)
    while parent is not None:
        if isinstance(parent, (cst.AssignTarget, cst.AnnAssign, cst.AugAssign, cst.Del)):
            return True
        if isinstance(parent, cst.SimpleStatementLine):
            return False
        parent = transformer.get_metadata(ParentNodeProvider, parent, None)
    return False


class NormalizeImportsCodemod:
    id = "normalize_imports"
    description = "Normalize safe qualified module imports to direct from-imports."
    params_model = NormalizeImportsParams

    def validate_params(self, params: dict[str, object] | None) -> NormalizeImportsParams:
        try:
            return NormalizeImportsParams.model_validate(params or {})
        except Exception as exc:
            raise RefactorError(
                "CODEMOD_VALIDATION_ERROR",
                f"invalid params for {self.id}",
            ) from exc

    def transform(self, params: BaseModel) -> cst.CSTTransformer:
        assert isinstance(params, NormalizeImportsParams)
        return _NormalizeImportsTransformer()


def build_transformer(params: BaseModel) -> cst.CSTTransformer:
    assert isinstance(params, NormalizeImportsParams)
    return _NormalizeImportsTransformer()
