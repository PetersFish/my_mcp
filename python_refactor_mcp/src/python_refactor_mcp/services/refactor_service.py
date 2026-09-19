from __future__ import annotations

import asyncio

from python_refactor_mcp.adapters.rope_adapter import PlannedChanges
from python_refactor_mcp.adapters.rope_provider import RopeRefactorProvider
from python_refactor_mcp.models import RefactorRequest

_PROVIDER = RopeRefactorProvider()


def run_rope_refactor(request: RefactorRequest) -> PlannedChanges:
    return asyncio.run(_PROVIDER.run(request))
