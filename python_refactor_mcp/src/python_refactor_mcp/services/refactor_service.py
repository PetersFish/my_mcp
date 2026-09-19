from __future__ import annotations

from python_refactor_mcp.adapters.rope_adapter import PlannedChanges, run_rope
from python_refactor_mcp.models import RefactorRequest


def run_rope_refactor(request: RefactorRequest) -> PlannedChanges:
    """Apply Rope refactor synchronously (no nested event loop)."""
    return run_rope(request)
