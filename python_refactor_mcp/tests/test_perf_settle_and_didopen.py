from __future__ import annotations

import asyncio
import time
from pathlib import Path

from python_refactor_mcp.adapters.pyright.lsp_client import (
    DIAGNOSTICS_SETTLE_SECONDS,
    PyrightLspClient,
)


class _FakeClient(PyrightLspClient):
    """Client that records sends and can inject publishDiagnostics."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[dict] = []
        self.sleep_calls: list[float] = []

    async def _send(self, payload: dict) -> None:
        self.sent.append(payload)
        method = payload.get("method")
        if method == "textDocument/didOpen":
            uri = (payload.get("params") or {}).get("textDocument", {}).get("uri")
            if isinstance(uri, str):
                self._opened.add(uri)
        elif method == "textDocument/didClose":
            uri = (payload.get("params") or {}).get("textDocument", {}).get("uri")
            if isinstance(uri, str):
                self._opened.discard(uri)

    async def _wait_for_diagnostics(self, uris: set[str], settle_timeout: float) -> None:
        # Faster poll for unit tests; still event-driven on injected diags.
        loop = asyncio.get_running_loop()
        deadline = loop.time() + settle_timeout
        while loop.time() < deadline:
            if all(uri in self._diagnostics for uri in uris):
                return
            await asyncio.sleep(0.01)


def test_refresh_settles_early_on_publish_diagnostics(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    client = _FakeClient()
    uri = target.resolve().as_uri()

    async def _run() -> float:
        async def _inject() -> None:
            await asyncio.sleep(0.05)
            client._dispatch(
                {
                    "method": "textDocument/publishDiagnostics",
                    "params": {"uri": uri, "diagnostics": []},
                }
            )

        task = asyncio.create_task(_inject())
        t0 = time.perf_counter()
        await client.refresh(changed=[target], settle_timeout=DIAGNOSTICS_SETTLE_SECONDS)
        elapsed = time.perf_counter() - t0
        await task
        return elapsed

    elapsed = asyncio.run(_run())
    assert elapsed < 0.25, f"expected early settle, took {elapsed:.3f}s"
    assert uri in client._diagnostics


def test_refresh_caps_at_settle_timeout_without_publish(tmp_path: Path) -> None:
    target = tmp_path / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8")
    client = _FakeClient()

    async def _run() -> float:
        t0 = time.perf_counter()
        await client.refresh(changed=[target], settle_timeout=0.12)
        return time.perf_counter() - t0

    elapsed = asyncio.run(_run())
    assert 0.10 <= elapsed < 0.35


def test_did_open_skipped_when_already_opened(tmp_path: Path) -> None:
    target = tmp_path / "a.py"
    target.write_text("x = 1\n", encoding="utf-8")
    client = _FakeClient()
    uri = target.resolve().as_uri()
    client._opened.add(uri)

    async def _run() -> None:
        await client.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": "python",
                    "version": 1,
                    "text": "x = 1\n",
                }
            },
        )

    asyncio.run(_run())
    assert not any(msg.get("method") == "textDocument/didOpen" for msg in client.sent)
