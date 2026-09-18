from __future__ import annotations

from typing import Protocol


class CodemodDefinition(Protocol):
    id: str
    description: str

    def validate_params(self, *_args: object, **_kwargs: object) -> None: ...

    def transform(self, *_args: object, **_kwargs: object) -> object: ...
