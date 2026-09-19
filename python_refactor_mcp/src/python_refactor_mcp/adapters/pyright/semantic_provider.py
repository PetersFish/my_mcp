from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from python_refactor_mcp.adapters.pyright.lsp_client import PyrightLspClient
from python_refactor_mcp.adapters.pyright.process_manager import PyrightProcessManager
from python_refactor_mcp.models.common import SourcePosition
from python_refactor_mcp.models.errors import RefactorError
from python_refactor_mcp.utils.paths import ensure_inside_project, resolve_project_root, uri_to_path


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
        client, root, path = await self._prepare(project_root, position.path, open_workspace=False)
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
        # Open target + import dependents only (not full-workspace didOpen flood).
        client, root, path = await self._prepare(project_root, position.path, open_workspace=False)
        await self._open_import_dependents(client, root, path)
        locations = await self._references_request(client, root, path, position)
        return ReferenceHits(locations=locations)

    async def _open_import_dependents(
        self,
        client: PyrightLspClient,
        root: Path,
        path: Path,
    ) -> None:
        for dep in _find_import_dependents(root, path):
            uri = dep.resolve().as_uri()
            if uri in client._opened:
                continue
            try:
                text = dep.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            await client.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "python",
                        "version": 1,
                        "text": text,
                    }
                },
            )

    async def _references_request(
        self,
        client: PyrightLspClient,
        root: Path,
        path: Path,
        position: SourcePosition,
    ) -> list[SourcePosition]:
        result = await client.request(
            "textDocument/references",
            {
                **_text_position(path, position),
                "context": {"includeDeclaration": True},
            },
        )
        locations = _as_locations(result)
        safe: list[SourcePosition] = []
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
        return safe

    async def hover(self, project_root: Path, position: SourcePosition) -> HoverInfo:
        client, _root, path = await self._prepare(project_root, position.path, open_workspace=False)
        result = await client.request("textDocument/hover", _text_position(path, position))
        return HoverInfo(contents=_hover_text(result))

    async def workspace_symbols(self, project_root: Path, query: str) -> list[dict[str, Any]]:
        client, root, _path = await self._prepare(project_root, None, open_workspace=True)
        result = await client.request("workspace/symbol", {"query": query})
        return result or []

    async def document_symbols(self, project_root: Path, path: Path) -> list[dict[str, Any]]:
        client, _root, document = await self._prepare(project_root, path, open_workspace=False)
        result = await client.request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": document.as_uri()}},
        )
        return result or []

    async def diagnostics(
        self,
        project_root: Path,
        path: Path | None = None,
        *,
        wait_timeout: float = 2.0,
    ) -> list[dict[str, Any]]:
        # Diagnostics only need the target buffer; avoid workspace didOpen flood here.
        client, _root, target = await self._prepare(
            project_root, path, open_workspace=False
        )
        if path is not None:
            if wait_timeout <= 0:
                return client.diagnostics(target)
            deadline = asyncio.get_running_loop().time() + wait_timeout
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
        *,
        open_workspace: bool = False,
    ) -> tuple[PyrightLspClient, Path, Path]:
        root = resolve_project_root(project_root)
        session = await self._manager.get_or_start(root)
        client = session.client
        if not isinstance(client, PyrightLspClient):
            raise RefactorError("LSP_PROTOCOL_ERROR", "semantic provider requires PyrightLspClient")
        target = root if path is None else ensure_inside_project(root, path)
        if path is not None and target.is_file():
            uri = target.as_uri()
            if uri not in client._opened:
                await client.notify(
                    "textDocument/didOpen",
                    {
                        "textDocument": {
                            "uri": uri,
                            "languageId": "python",
                            "version": 1,
                            "text": target.read_text(encoding="utf-8"),
                        }
                    },
                )
        if open_workspace and not session.extra.get("workspace_opened"):
            await _open_workspace_python_files(client, root)
            session.extra["workspace_opened"] = True
        return client, root, target


_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__"}


async def _open_workspace_python_files(client: PyrightLspClient, root: Path) -> None:
    for path in root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        uri = path.resolve().as_uri()
        if uri in client._opened:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        await client.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": "python",
                    "version": 1,
                    "text": text,
                }
            },
        )


def _find_import_dependents(root: Path, target: Path) -> list[Path]:
    """Return Python files that likely import ``target`` (lightweight text scan)."""
    try:
        rel = target.resolve().relative_to(root.resolve())
    except ValueError:
        return []
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return []
    # Strip common source roots for dotted import matching.
    for prefix in ("src", "lib"):
        if parts and parts[0] == prefix:
            parts = parts[1:]
            break
    dotted = ".".join(parts)
    if not dotted:
        return []
    needles = (
        f"import {dotted}",
        f"from {dotted} ",
        f"from {dotted}.",
        f"from {'.'.join(parts[:-1])} import" if len(parts) > 1 else None,
    )
    needles = tuple(n for n in needles if n)
    leaf = parts[-1]
    dependents: list[Path] = []
    for path in root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        if path.resolve() == target.resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(needle in text for needle in needles):
            dependents.append(path)
            continue
        # `from pkg import leaf` style
        if f"import {leaf}" in text and dotted.rsplit(".", 1)[0] in text:
            dependents.append(path)
    return dependents


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
                path=uri_to_path(str(target)),
                line=int(start.get("line", 0)),
                character=int(start.get("character", 0)),
            )
        )
    return locations


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
