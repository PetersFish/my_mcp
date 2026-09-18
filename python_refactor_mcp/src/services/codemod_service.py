from __future__ import annotations


class CodemodService:
    def preview(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError("LibCST codemods land in Batch 3")

    def apply(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError("LibCST codemods land in Batch 3")
