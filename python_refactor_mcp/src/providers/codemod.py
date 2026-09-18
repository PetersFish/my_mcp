from __future__ import annotations

from typing import Protocol


class CodemodProvider(Protocol):
    async def preview(self, *_args: object, **_kwargs: object) -> object: ...

    async def apply(self, *_args: object, **_kwargs: object) -> object: ...
