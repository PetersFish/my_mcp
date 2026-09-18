from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from python_refactor_mcp.adapters.pyright.runtime import PyrightRuntime
from python_refactor_mcp.models.errors import RefactorError

JsonObject = dict[str, Any]


class PyrightLspClient:
    def __init__(self) -> None:
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def start(
        self,
        runtime: PyrightRuntime,
        project_root: Path,
        python_path: Path | None,
    ) -> None:
        root = project_root.resolve()
        self._process = await asyncio.create_subprocess_exec(
            str(runtime.language_server),
            "--stdio",
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

    async def health_check(self) -> bool:
        process = self._process
        return process is not None and process.returncode is None

    async def refresh(self, changed_files: list[Path]) -> None:
        changes = []
        for path in changed_files:
            resolved = path.resolve()
            exists = resolved.exists()
            changes.append(
                {
                    "uri": resolved.as_uri(),
                    "type": 1 if exists and path.suffix else (2 if exists else 3),
                }
            )
        if changes:
            await self.notify("workspace/didChangeWatchedFiles", {"changes": changes})

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
