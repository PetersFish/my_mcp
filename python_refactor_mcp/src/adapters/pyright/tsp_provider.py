from __future__ import annotations

class PyrightTypeProvider:
    async def get_computed_type(self, *_args: object, **_kwargs: object) -> object:
        raise NotImplementedError("TSP is reserved for a later batch")

    async def get_declared_type(self, *_args: object, **_kwargs: object) -> object:
        raise NotImplementedError("TSP is reserved for a later batch")

    async def get_expected_type(self, *_args: object, **_kwargs: object) -> object:
        raise NotImplementedError("TSP is reserved for a later batch")

    async def resolve_import(self, *_args: object, **_kwargs: object) -> object:
        raise NotImplementedError("TSP is reserved for a later batch")
