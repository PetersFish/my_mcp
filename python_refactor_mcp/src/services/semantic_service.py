from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from python_refactor_mcp.adapters.pyright.process_manager import default_manager
from python_refactor_mcp.adapters.pyright.semantic_provider import (
    DefinitionHit,
    HoverInfo,
    PyrightSemanticProvider,
    ReferenceHits,
)
from python_refactor_mcp.models.common import SourcePosition
from python_refactor_mcp.models.errors import RefactorError
from python_refactor_mcp.providers.semantic import SemanticProvider
from python_refactor_mcp.utils.paths import ensure_inside_project, resolve_project_root
from python_refactor_mcp.utils.summaries import MAX_REFERENCES_DEFAULT, format_location, truncate_items

logger = logging.getLogger(__name__)


class SemanticService:
    def __init__(self, provider: SemanticProvider | None = None) -> None:
        self._provider = provider or PyrightSemanticProvider(default_manager())

    async def definition(self, project_root: Path, position: SourcePosition) -> DefinitionHit | None:
        return await self._provider.definition(project_root, position)

    async def references(self, project_root: Path, position: SourcePosition) -> ReferenceHits:
        return await self._provider.references(project_root, position)

    async def hover(self, project_root: Path, position: SourcePosition) -> HoverInfo:
        return await self._provider.hover(project_root, position)

    async def refresh(self, project_root: Path, changed_files: list[Path]) -> None:
        await self._provider.refresh(project_root, changed_files)

    async def inspect(
        self,
        project_root: str | Path,
        file: str,
        line: int,
        character: int,
        *,
        include_definition: bool = True,
        include_references: bool = True,
        include_type: bool = True,
        max_references: int = MAX_REFERENCES_DEFAULT,
    ) -> dict[str, object]:
        root = resolve_project_root(project_root)
        path = ensure_inside_project(root, file)
        if not path.is_file():
            raise RefactorError("SOURCE_NOT_FOUND", f"file not found: {file}")
        if line < 1 or character < 1:
            raise RefactorError("SOURCE_NOT_FOUND", "line and character must be 1-based and >= 1")
        position = SourcePosition(path=path, line=line - 1, character=character - 1)
        tasks: dict[str, asyncio.Task[object]] = {}
        if include_definition:
            tasks["definition"] = asyncio.create_task(self.definition(root, position))
        if include_references:
            tasks["references"] = asyncio.create_task(self.references(root, position))
        if include_type:
            tasks["hover"] = asyncio.create_task(self.hover(root, position))
        gathered = await asyncio.gather(*tasks.values())
        results = dict(zip(tasks, gathered, strict=True))
        definition = results.get("definition")
        references = results.get("references")
        hover = results.get("hover")
        definition_hit = definition if isinstance(definition, DefinitionHit) else None
        reference_hits = references if isinstance(references, ReferenceHits) else None
        hover_info = hover if isinstance(hover, HoverInfo) else None
        locations = []
        if reference_hits is not None:
            locations = [
                format_location(root, item.path, item.line, item.character)
                for item in reference_hits.locations
            ]
        listed, truncated = truncate_items(locations, max_references)
        session = await default_manager().get_or_start(root)
        payload: dict[str, object] = {
            "status": "success",
            "symbol": _symbol_name(path, position, hover_info),
            "definition": (
                format_location(root, definition_hit.path, definition_hit.line, definition_hit.character)
                if definition_hit is not None
                else None
            ),
            "reference_count": reference_hits.count if reference_hits is not None else 0,
            "references": listed,
            "references_returned": len(listed),
            "references_truncated": truncated,
            "type": _compact_type(hover_info),
            "semantic_backend": "pyright",
            "pyright_runtime": session.runtime.source,
        }
        if definition_hit is None and include_definition and (reference_hits is None or reference_hits.count == 0):
            raise RefactorError("SYMBOL_NOT_FOUND", f"no symbol at {file}:{line}:{character}")
        return payload


def _symbol_name(path: Path, position: SourcePosition, hover: HoverInfo | None) -> str:
    try:
        line = path.read_text(encoding="utf-8").splitlines()[position.line]
    except (OSError, IndexError, UnicodeDecodeError):
        line = ""
    match = re.search(r"[A-Za-z_][A-Za-z0-9_]*", line[position.character :] or line)
    if match:
        return match.group(0)
    if hover and hover.contents:
        return hover.contents.splitlines()[0][:80]
    return ""


def _compact_type(hover: HoverInfo | None) -> str | None:
    if hover is None or not hover.contents:
        return None
    for raw in hover.contents.splitlines():
        text = raw.strip().strip("`")
        if text and not text.startswith("```"):
            return text[:200]
    return hover.contents.splitlines()[0][:200]
