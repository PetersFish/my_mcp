from __future__ import annotations

from pathlib import Path
from typing import Protocol

from python_refactor_mcp.models.common import SourcePosition


class SemanticProvider(Protocol):
    async def definition(self, project_root: Path, position: SourcePosition) -> object: ...

    async def references(self, project_root: Path, position: SourcePosition) -> object: ...

    async def hover(self, project_root: Path, position: SourcePosition) -> object: ...

    async def workspace_symbols(self, project_root: Path, query: str) -> object: ...

    async def document_symbols(self, project_root: Path, path: Path) -> object: ...

    async def diagnostics(self, project_root: Path, path: Path | None = None) -> object: ...

    async def refresh(
        self,
        project_root: Path,
        *,
        created: list[Path] | None = None,
        changed: list[Path] | None = None,
        deleted: list[Path] | None = None,
    ) -> None: ...
