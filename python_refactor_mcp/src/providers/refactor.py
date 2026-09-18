from __future__ import annotations

from typing import Protocol

from python_refactor_mcp.adapters.rope_adapter import PlannedChanges
from python_refactor_mcp.models import RefactorRequest


class RefactorProvider(Protocol):
    async def rename_symbol(self, request: RefactorRequest) -> PlannedChanges: ...

    async def move_symbol(self, request: RefactorRequest) -> PlannedChanges: ...

    async def rename_module(self, request: RefactorRequest) -> PlannedChanges: ...

    async def move_module(self, request: RefactorRequest) -> PlannedChanges: ...
