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
from python_refactor_mcp.utils.packages import module_file, resolve_source_root
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

    async def diagnostics(
        self,
        project_root: Path,
        path: Path | None = None,
        *,
        wait_timeout: float = 2.0,
    ) -> object:
        return await self._provider.diagnostics(
            project_root,
            path,
            wait_timeout=wait_timeout,
        )

    async def resolve_symbol(
        self,
        project_root: str | Path,
        module: str,
        symbol: str,
        source_root: str | None = None,
    ) -> SourcePosition:
        root = resolve_project_root(project_root)
        src = resolve_source_root(root, source_root, dotted_module=module)
        path = module_file(src, module)
        if path is None:
            raise RefactorError("SOURCE_NOT_FOUND", f"module not found: {module}")
        symbols = await self._provider.document_symbols(root, path)
        items = symbols if isinstance(symbols, list) else []
        matches = _match_document_symbols(path, items, symbol)
        if not matches:
            raise RefactorError("SYMBOL_NOT_FOUND", f"symbol not found: {symbol}")
        if len(matches) > 1:
            raise RefactorError("AMBIGUOUS_SYMBOL", f"symbol is not unique: {symbol}")
        return matches[0]

    async def module_defines_symbol(
        self,
        project_root: str | Path,
        module: str,
        symbol: str,
        source_root: str | None = None,
    ) -> bool:
        root = resolve_project_root(project_root)
        src = resolve_source_root(root, source_root, dotted_module=module)
        path = module_file(src, module)
        if path is None:
            return False
        symbols = await self._provider.document_symbols(root, path)
        items = symbols if isinstance(symbols, list) else []
        return bool(_match_document_symbols(path, items, symbol.split(".")[-1]))

    async def refresh(
        self,
        project_root: Path,
        *,
        created: list[Path] | None = None,
        changed: list[Path] | None = None,
        deleted: list[Path] | None = None,
    ) -> None:
        await self._provider.refresh(
            project_root,
            created=created,
            changed=changed,
            deleted=deleted,
        )

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


def _match_document_symbols(path: Path, symbols: list[object], symbol: str) -> list[SourcePosition]:
    if "." in symbol:
        owner, leaf = symbol.split(".", 1)
        matches: list[SourcePosition] = []
        for item in _top_level_symbols(symbols):
            if _document_symbol_name(item) != owner:
                continue
            for child in _symbol_children(item):
                if _document_symbol_name(child) == leaf:
                    matches.append(_symbol_position(path, child))
        for item in _top_level_symbols(symbols):
            if _document_symbol_name(item) == leaf and item.get("containerName") == owner:
                matches.append(_symbol_position(path, item))
        return matches
    return [
        _symbol_position(path, item)
        for item in _top_level_symbols(symbols)
        if _document_symbol_name(item) == symbol and not item.get("containerName")
    ]


def _top_level_symbols(symbols: list[object]) -> list[dict[str, object]]:
    return [item for item in symbols if isinstance(item, dict)]


def _symbol_children(item: dict[str, object]) -> list[dict[str, object]]:
    children = item.get("children") or []
    if not isinstance(children, list):
        return []
    return [child for child in children if isinstance(child, dict)]


def _document_symbol_name(item: dict[str, object]) -> str:
    name = item.get("name")
    return name if isinstance(name, str) else ""


def _symbol_position(path: Path, item: dict[str, object]) -> SourcePosition:
    selection = item.get("selectionRange")
    if not isinstance(selection, dict):
        location = item.get("location")
        selection = location.get("range") if isinstance(location, dict) else item.get("range")
    start = selection.get("start") if isinstance(selection, dict) else {}
    if not isinstance(start, dict):
        start = {}
    line = int(start.get("line", 0) or 0)
    character = int(start.get("character", 0) or 0)
    name = _document_symbol_name(item)
    if name:
        try:
            text_line = path.read_text(encoding="utf-8").splitlines()[line]
        except (OSError, IndexError, UnicodeDecodeError):
            text_line = ""
        idx = text_line.find(name)
        if idx >= 0:
            character = idx
    return SourcePosition(
        path=path,
        line=line,
        character=character,
    )


def _compact_type(hover: HoverInfo | None) -> str | None:
    if hover is None or not hover.contents:
        return None
    for raw in hover.contents.splitlines():
        text = raw.strip().strip("`")
        if text and not text.startswith("```"):
            return text[:200]
    return hover.contents.splitlines()[0][:200]
