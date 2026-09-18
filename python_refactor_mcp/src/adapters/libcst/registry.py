from __future__ import annotations


class CodemodRegistry:
    def register(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError("Codemod registry lands in Batch 3")
