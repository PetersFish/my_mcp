from __future__ import annotations


class LibCSTCodemodProvider:
    async def preview(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError("LibCST adapter lands in Batch 3")

    async def apply(self, *_args: object, **_kwargs: object) -> None:
        raise NotImplementedError("LibCST adapter lands in Batch 3")
