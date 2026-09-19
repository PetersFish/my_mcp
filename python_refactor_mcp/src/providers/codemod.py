from __future__ import annotations

from typing import Protocol


class CodemodProvider(Protocol):
    def preview(self, *_args: object, **_kwargs: object) -> object: ...

    def apply(self, *_args: object, **_kwargs: object) -> object: ...
