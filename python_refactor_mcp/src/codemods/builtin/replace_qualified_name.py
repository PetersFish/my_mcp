from __future__ import annotations


class ReplaceQualifiedNameCodemod:
    id = "replace_qualified_name"
    description = "Replace a qualified name across imports and references."

    def validate_params(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError("replace_qualified_name lands in Batch 3")

    def transform(self, *_args: object, **_kwargs: object) -> object:
        raise NotImplementedError("replace_qualified_name lands in Batch 3")
