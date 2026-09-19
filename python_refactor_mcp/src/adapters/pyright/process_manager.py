from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from python_refactor_mcp.adapters.pyright.environment_resolver import (
    PythonEnvironmentResolver,
)
from python_refactor_mcp.adapters.pyright.loop_runner import LoopRunner
from python_refactor_mcp.adapters.pyright.runtime import PyrightRuntime
from python_refactor_mcp.adapters.pyright.runtime_resolver import PyrightRuntimeResolver
from python_refactor_mcp.models.errors import RefactorError


class LspSessionClient(Protocol):
    async def start(
        self,
        runtime: PyrightRuntime,
        project_root: Path,
        python_path: Path | None,
    ) -> None: ...

    async def health_check(self) -> bool: ...

    async def refresh(
        self,
        *,
        created: list[Path] | None = None,
        changed: list[Path] | None = None,
        deleted: list[Path] | None = None,
    ) -> None: ...

    async def shutdown(self) -> None: ...


@dataclass
class PyrightSession:
    project_root: Path
    runtime: PyrightRuntime
    client: LspSessionClient
    start_count: int = 1
    python_path: Path | None = None
    extra: dict[str, object] = field(default_factory=dict)


class PyrightProcessManager:
    def __init__(
        self,
        *,
        runtime_factory: Callable[[Path], PyrightRuntime] | None = None,
        client_factory: Callable[[], LspSessionClient] | None = None,
        environment_resolver: PythonEnvironmentResolver | None = None,
    ) -> None:
        self._sessions: dict[Path, PyrightSession] = {}
        self._runtime_factory = runtime_factory or (lambda root: PyrightRuntimeResolver().resolve(root))
        self._client_factory = client_factory
        self._environment_resolver = environment_resolver or PythonEnvironmentResolver()
        self.runner = LoopRunner()

    async def get_or_start(self, project_root: str | Path) -> PyrightSession:
        root = Path(project_root).resolve()
        existing = self._sessions.get(root)
        if existing is not None:
            if await existing.client.health_check():
                return existing
            await existing.client.shutdown()
            del self._sessions[root]
            restarted = await self._start(root)
            restarted.start_count = existing.start_count + 1
            return restarted
        return await self._start(root)

    async def health_check(self, project_root: str | Path) -> bool:
        session = self._sessions.get(Path(project_root).resolve())
        if session is None:
            return False
        return await session.client.health_check()

    async def refresh(
        self,
        project_root: str | Path,
        *,
        created: list[Path] | None = None,
        changed: list[Path] | None = None,
        deleted: list[Path] | None = None,
    ) -> None:
        session = await self.get_or_start(project_root)
        try:
            await session.client.refresh(created=created, changed=changed, deleted=deleted)
        except RefactorError as exc:
            if exc.code not in {"PYRIGHT_TIMEOUT", "LSP_PROTOCOL_ERROR"}:
                raise
            session = await self.restart(project_root)
            await session.client.refresh(created=created, changed=changed, deleted=deleted)

    async def restart(self, project_root: str | Path) -> PyrightSession:
        root = Path(project_root).resolve()
        existing = self._sessions.pop(root, None)
        if existing is not None:
            await existing.client.shutdown()
        session = await self._start(root)
        if existing is not None:
            session.start_count = existing.start_count + 1
        return session

    async def shutdown(self, project_root: str | Path | None = None) -> None:
        if project_root is None:
            roots = list(self._sessions)
        else:
            roots = [Path(project_root).resolve()]
        for root in roots:
            session = self._sessions.pop(root, None)
            if session is not None:
                await session.client.shutdown()

    async def _start(self, root: Path) -> PyrightSession:
        runtime = self._runtime_factory(root)
        python_path = self._environment_resolver.resolve(root).executable
        client = self._new_client()
        await client.start(runtime, root, python_path)
        session = PyrightSession(
            project_root=root,
            runtime=runtime,
            client=client,
            python_path=python_path,
        )
        self._sessions[root] = session
        return session

    def _new_client(self) -> LspSessionClient:
        if self._client_factory is not None:
            return self._client_factory()
        from python_refactor_mcp.adapters.pyright.lsp_client import PyrightLspClient

        return PyrightLspClient()


_DEFAULT_MANAGER: PyrightProcessManager | None = None


def default_manager() -> PyrightProcessManager:
    global _DEFAULT_MANAGER
    if _DEFAULT_MANAGER is None:
        _DEFAULT_MANAGER = PyrightProcessManager()
    return _DEFAULT_MANAGER
