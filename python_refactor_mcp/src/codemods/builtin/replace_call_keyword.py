from __future__ import annotations


class ReplaceCallKeywordCodemod:
    id = "replace_call_keyword"
    description = "Rename a keyword argument on a qualified function call."

    def validate_params(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError("replace_call_keyword lands in Batch 3")

    def transform(self, *_args: object, **_kwargs: object) -> object:
        raise NotImplementedError("replace_call_keyword lands in Batch 3")
