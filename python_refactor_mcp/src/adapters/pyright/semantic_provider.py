from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from python_refactor_mcp.adapters.pyright.lsp_client import PyrightLspClient
from python_refactor_mcp.adapters.pyright.process_manager import PyrightProcessManager
from python_refactor_mcp.models.common import SourcePosition
from python_refactor_mcp.models.errors import RefactorError
from python_refactor_mcp.utils.paths import ensure_inside_project, resolve_project_root


@dataclass(frozen=True)
class DefinitionHit:
    path: Path
    line: int
    character: int
    name: str | None = None


@dataclass(frozen=True)
class ReferenceHits:
    locations: list[SourcePosition]

    @property
    def count(self) -> int:
        return len(self.locations)


@dataclass(frozen=True)
class HoverInfo:
    contents: str


class PyrightSemanticProvider:
    def __init__(self, manager: PyrightProcessManager | None = None) -> None:
        self._manager = manager or PyrightProcessManager()

    async def definition(self, project_root: Path, position: SourcePosition) -> DefinitionHit | None:
        client, root, path = await self._prepare(project_root, position.path)
        result = await client.request(
            "textDocument/definition",
            _text_position(path, position),
        )
        locations = _as_locations(result)
        if not locations:
            return None
        hit = locations[0]
        return DefinitionHit(path=hit.path, line=hit.line, character=hit.character)

    async def references(self, project_root: Path, position: SourcePosition) -> ReferenceHits:
        client, root, path = await self._prepare(project_root, position.path)
        result = await client.request(
            "textDocument/references",
            {
                **_text_position(path, position),
                "context": {"includeDeclaration": True},
            },
        )
        locations = _as_locations(result)
        safe = []
        for item in locations:
            try:
                safe.append(
                    SourcePosition(
                        path=ensure_inside_project(root, item.path),
                        line=item.line,
                        character=item.character,
                    )
                )
            except ValueError:
                continue
        return ReferenceHits(locations=safe)

    async def hover(self, project_root: Path, position: SourcePosition) -> HoverInfo:
        client, _root, path = await self._prepare(project_root, position.path)
        result = await client.request("textDocument/hover", _text_position(path, position))
        return HoverInfo(contents=_hover_text(result))

    async def workspace_symbols(self, project_root: Path, query: str) -> list[dict[str, Any]]:
        client, root, _path = await self._prepare(project_root, None)
        result = await client.request("workspace/symbol", {"query": query})
        return result or []

    async def document_symbols(self, project_root: Path, path: Path) -> list[dict[str, Any]]:
        client, _root, document = await self._prepare(project_root, path)
        result = await client.request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": document.as_uri()}},
        )
        return result or []

    async def diagnostics(self, project_root: Path, path: Path | None = None) -> list[dict[str, Any]]:
        client, _root, target = await self._prepare(project_root, path)
        if path is not None:
            deadline = asyncio.get_running_loop().time() + 2.0
            while asyncio.get_running_loop().time() < deadline:
                items = client.diagnostics(target)
                if items:
                    return items
                await asyncio.sleep(0.1)
            return client.diagnostics(target)
        return client.diagnostics(None)

    async def refresh(
        self,
        project_root: Path,
        *,
        created: list[Path] | None = None,
        changed: list[Path] | None = None,
        deleted: list[Path] | None = None,
    ) -> None:
        root = resolve_project_root(project_root)
        await self._manager.refresh(
            root,
            created=[ensure_inside_project(root, path) for path in created or []],
            changed=[ensure_inside_project(root, path) for path in changed or []],
            deleted=[ensure_inside_project(root, path) for path in deleted or []],
        )

    async def _prepare(
        self,
        project_root: Path,
        path: Path | None,
    ) -> tuple[PyrightLspClient, Path, Path]:
        root = resolve_project_root(project_root)
        session = await self._manager.get_or_start(root)
        client = session.client
        if not isinstance(client, PyrightLspClient):
            raise RefactorError("LSP_PROTOCOL_ERROR", "semantic provider requires PyrightLspClient")
        target = root if path is None else ensure_inside_project(root, path)
        if path is not None and target.is_file():
            await client.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": target.as_uri(),
                        "languageId": "python",
                        "version": 1,
                        "text": target.read_text(encoding="utf-8"),
                    }
                },
            )
        if not session.extra.get("workspace_opened"):
            await _open_workspace_python_files(client, root)
            session.extra["workspace_opened"] = True
        return client, root, target


async def _open_workspace_python_files(client: PyrightLspClient, root: Path) -> None:
    skip = {".git", ".venv", "venv", "node_modules", "__pycache__"}
    for path in root.rglob("*.py"):
        if any(part in skip for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        await client.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": path.resolve().as_uri(),
                    "languageId": "python",
                    "version": 1,
                    "text": text,
                }
            },
        )


def _text_position(path: Path, position: SourcePosition) -> dict[str, object]:
    return {
        "textDocument": {"uri": path.as_uri()},
        "position": {"line": position.line, "character": position.character},
    }


def _as_locations(result: object) -> list[SourcePosition]:
    if not result:
        return []
    items = result if isinstance(result, list) else [result]
    locations: list[SourcePosition] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        target = item.get("targetUri") or item.get("uri")
        rng = item.get("targetSelectionRange") or item.get("targetRange") or item.get("range") or {}
        start = rng.get("start") or {}
        if not target:
            continue
        locations.append(
            SourcePosition(
                path=_uri_to_path(str(target)),
                line=int(start.get("line", 0)),
                character=int(start.get("character", 0)),
            )
        )
    return locations


def _uri_to_path(uri: str) -> Path:
    parsed = urlparse(uri)
    return Path(unquote(parsed.path))


def _hover_text(result: object) -> str:
    if not isinstance(result, dict):
        return ""
    contents = result.get("contents")
    if isinstance(contents, str):
        return contents.strip()
    if isinstance(contents, dict):
        return str(contents.get("value", "")).strip()
    if isinstance(contents, list):
        parts = []
        for item in contents:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("value", "")))
        return "\n".join(part for part in parts if part).strip()
    return ""
