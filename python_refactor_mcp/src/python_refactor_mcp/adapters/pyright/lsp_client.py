from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from python_refactor_mcp.adapters.pyright.runtime import PyrightRuntime
from python_refactor_mcp.models.errors import RefactorError
from python_refactor_mcp.utils.process import language_server_argv

JsonObject = dict[str, Any]

FILE_CREATED = 1
FILE_CHANGED = 2
FILE_DELETED = 3
DIAGNOSTICS_SETTLE_SECONDS = 0.4


class PyrightLspClient:
    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._next_id = 1
        self._lock = asyncio.Lock()
        self._opened: set[str] = set()
        self._diagnostics: dict[str, list[JsonObject]] = {}

    async def start(
        self,
        runtime: PyrightRuntime,
        project_root: Path,
        python_path: Path | None,
    ) -> None:
        root = project_root.resolve()
        argv = language_server_argv(runtime.language_server)
        self._process = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(root),
        )
        if self._process.stdout is None or self._process.stdin is None:
            raise RefactorError("LSP_PROTOCOL_ERROR", "pyright-langserver stdio pipes were not created")
        self._reader_task = asyncio.create_task(self._read_loop(), name="pyright-lsp-reader")
        initialize_params: JsonObject = {
            "processId": os.getpid(),
            "rootUri": root.as_uri(),
            "rootPath": str(root),
            "capabilities": {
                "textDocument": {
                    "definition": {"dynamicRegistration": False},
                    "references": {"dynamicRegistration": False},
                    "hover": {"dynamicRegistration": False},
                    "documentSymbol": {"dynamicRegistration": False},
                    "publishDiagnostics": {},
                },
                "workspace": {
                    "workspaceFolders": True,
                    "symbol": {"dynamicRegistration": False},
                },
            },
            "workspaceFolders": [{"uri": root.as_uri(), "name": root.name}],
            "initializationOptions": {},
        }
        if python_path is not None:
            initialize_params["initializationOptions"] = {
                "pythonPath": str(python_path),
            }
        await self.request("initialize", initialize_params, timeout=30)
        await self.notify("initialized", {})
        if python_path is not None:
            await self.notify(
                "workspace/didChangeConfiguration",
                {"settings": {"python": {"pythonPath": str(python_path)}}},
            )

    async def request(self, method: str, params: JsonObject, timeout: float = 20) -> Any:
        request_id = self._next_id
        self._next_id += 1
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Any] = loop.create_future()
        self._pending[request_id] = future
        await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError as exc:
            self._pending.pop(request_id, None)
            raise RefactorError("PYRIGHT_TIMEOUT", f"LSP request timed out: {method}") from exc

    async def notify(self, method: str, params: JsonObject) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})
        if method == "textDocument/didOpen":
            uri = (params.get("textDocument") or {}).get("uri")
            if isinstance(uri, str):
                self._opened.add(uri)
        elif method == "textDocument/didClose":
            uri = (params.get("textDocument") or {}).get("uri")
            if isinstance(uri, str):
                self._opened.discard(uri)

    async def health_check(self) -> bool:
        process = self._process
        return process is not None and process.returncode is None

    async def refresh(
        self,
        *,
        created: list[Path] | None = None,
        changed: list[Path] | None = None,
        deleted: list[Path] | None = None,
        settle_timeout: float = DIAGNOSTICS_SETTLE_SECONDS,
    ) -> None:
        deleted_paths = {path.resolve() for path in deleted or []}
        created_paths = {path.resolve() for path in created or []} - deleted_paths
        changed_paths = {path.resolve() for path in changed or []} - deleted_paths - created_paths
        watched: list[JsonObject] = []
        for path in deleted_paths:
            watched.append({"uri": path.as_uri(), "type": FILE_DELETED})
            await self._close_document(path)
            self._diagnostics.pop(path.as_uri(), None)
        for path, change_type in (
            *((item, FILE_CREATED) for item in created_paths),
            *((item, FILE_CHANGED) for item in changed_paths),
        ):
            watched.append({"uri": path.as_uri(), "type": change_type})
            await self._reopen_document(path)
        if watched:
            await self.notify("workspace/didChangeWatchedFiles", {"changes": watched})
        if settle_timeout > 0:
            await asyncio.sleep(settle_timeout)

    def diagnostics(self, path: Path | None = None) -> list[JsonObject]:
        if path is None:
            items: list[JsonObject] = []
            for uri, diags in self._diagnostics.items():
                for diag in diags:
                    item = dict(diag)
                    item.setdefault("uri", uri)
                    items.append(item)
            return items
        uri = path.resolve().as_uri()
        items = []
        for diag in self._diagnostics.get(uri, []):
            item = dict(diag)
            item.setdefault("uri", uri)
            items.append(item)
        return items

    async def _close_document(self, path: Path) -> None:
        uri = path.as_uri()
        if uri not in self._opened:
            return
        await self.notify("textDocument/didClose", {"textDocument": {"uri": uri}})

    async def _reopen_document(self, path: Path) -> None:
        await self._close_document(path)
        if not path.is_file():
            return
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return
        await self.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": path.as_uri(),
                    "languageId": "python",
                    "version": 1,
                    "text": text,
                }
            },
        )

    async def shutdown(self) -> None:
        try:
            if self._process is not None and self._process.returncode is None:
                try:
                    await self.request("shutdown", {}, timeout=5)
                except RefactorError:
                    pass
                try:
                    await self.notify("exit", {})
                except Exception:
                    pass
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except TimeoutError:
                    self._process.kill()
                    await self._process.wait()
        finally:
            if self._reader_task is not None:
                self._reader_task.cancel()
                try:
                    await self._reader_task
                except (asyncio.CancelledError, Exception):
                    pass
            self._process = None
            self._opened.clear()
            self._diagnostics.clear()
            for future in self._pending.values():
                if not future.done():
                    future.cancel()
            self._pending.clear()

    async def _send(self, payload: JsonObject) -> None:
        if self._process is None or self._process.stdin is None:
            raise RefactorError("LSP_PROTOCOL_ERROR", "language server is not running")
        body = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        async with self._lock:
            self._process.stdin.write(header + body)
            await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        stdout = self._process.stdout if self._process else None
        if stdout is None:
            return
        try:
            while True:
                message = await _read_message(stdout)
                if message is None:
                    break
                self._dispatch(message)
        except asyncio.CancelledError:
            raise
        except Exception:
            for future in list(self._pending.values()):
                if not future.done():
                    future.set_exception(
                        RefactorError("LSP_PROTOCOL_ERROR", "language server reader failed")
                    )

    def _dispatch(self, message: JsonObject) -> None:
        method = message.get("method")
        if method == "textDocument/publishDiagnostics":
            params = message.get("params") or {}
            uri = params.get("uri")
            if isinstance(uri, str):
                diagnostics = params.get("diagnostics") or []
                self._diagnostics[uri] = list(diagnostics) if isinstance(diagnostics, list) else []
            return
        if "id" in message and "method" not in message:
            request_id = message["id"]
            future = self._pending.pop(request_id, None)
            if future is None or future.done():
                return
            if "error" in message:
                error = message["error"]
                future.set_exception(
                    RefactorError(
                        "LSP_PROTOCOL_ERROR",
                        str(error.get("message", error)),
                    )
                )
                return
            future.set_result(message.get("result"))


async def _read_message(stream: asyncio.StreamReader) -> JsonObject | None:
    headers: dict[str, str] = {}
    while True:
        line = await stream.readline()
        if not line:
            return None
        if line in {b"\r\n", b"\n"}:
            break
        decoded = line.decode("ascii", errors="replace").strip()
        if ":" not in decoded:
            continue
        key, value = decoded.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = await stream.readexactly(length)
    return json.loads(body.decode("utf-8"))
