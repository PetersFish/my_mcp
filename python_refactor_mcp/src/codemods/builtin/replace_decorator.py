from __future__ import annotations


class ReplaceDecoratorCodemod:
    id = "replace_decorator"
    description = "Replace a decorator qualified name."

    def validate_params(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError("replace_decorator lands in Batch 3")

    def transform(self, *_args: object, **_kwargs: object) -> object:
        raise NotImplementedError("replace_decorator lands in Batch 3")
