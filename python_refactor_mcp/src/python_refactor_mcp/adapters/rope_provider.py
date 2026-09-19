from __future__ import annotations

from python_refactor_mcp.adapters.rope_adapter import PlannedChanges, run_rope
from python_refactor_mcp.models import RefactorRequest


class RopeRefactorProvider:
    async def rename_symbol(self, request: RefactorRequest) -> PlannedChanges:
        return run_rope(request)

    async def move_symbol(self, request: RefactorRequest) -> PlannedChanges:
        return run_rope(request)

    async def rename_module(self, request: RefactorRequest) -> PlannedChanges:
        return run_rope(request)

    async def move_module(self, request: RefactorRequest) -> PlannedChanges:
        return run_rope(request)

    async def run(self, request: RefactorRequest) -> PlannedChanges:
        return run_rope(request)
