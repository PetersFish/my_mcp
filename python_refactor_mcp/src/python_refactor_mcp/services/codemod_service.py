from __future__ import annotations

import time
from pathlib import Path

from python_refactor_mcp.adapters.libcst.adapter import LibCSTCodemodProvider
from python_refactor_mcp.adapters.libcst.registry import CodemodRegistry
from python_refactor_mcp.adapters.pyright.process_manager import default_manager
from python_refactor_mcp.codemods.builtin import default_registry
from python_refactor_mcp.models.codemod import CodemodResult
from python_refactor_mcp.models.errors import RefactorError
from python_refactor_mcp.services.semantic_service import SemanticService
from python_refactor_mcp.utils.paths import resolve_project_root


class CodemodService:
    def __init__(
        self,
        *,
        registry: CodemodRegistry | None = None,
        provider: LibCSTCodemodProvider | None = None,
        semantic_service: SemanticService | None = None,
    ) -> None:
        self._registry = registry or default_registry()
        self._provider = provider or LibCSTCodemodProvider()
        self._semantic = semantic_service

    def preview(
        self,
        project_root: str | Path,
        *,
        codemod: str,
        params: dict[str, object] | None = None,
        paths: list[str] | None = None,
    ) -> CodemodResult:
        return self._execute(
            project_root,
            codemod=codemod,
            params=params,
            paths=paths,
            dry_run=True,
        )

    def apply(
        self,
        project_root: str | Path,
        *,
        codemod: str,
        params: dict[str, object] | None = None,
        paths: list[str] | None = None,
        dry_run: bool = True,
        expected_hashes: dict[str, str] | None = None,
    ) -> CodemodResult:
        return self._execute(
            project_root,
            codemod=codemod,
            params=params,
            paths=paths,
            dry_run=dry_run,
            expected_hashes=expected_hashes,
        )

    def _execute(
        self,
        project_root: str | Path,
        *,
        codemod: str,
        params: dict[str, object] | None,
        paths: list[str] | None,
        dry_run: bool,
        expected_hashes: dict[str, str] | None = None,
    ) -> CodemodResult:
        started = time.perf_counter()
        try:
            root = resolve_project_root(project_root)
            validated = self._registry.validate_params(codemod, params)
            path_list = paths or ["."]
            if dry_run:
                run = self._provider.preview(
                    root,
                    codemod_id=codemod,
                    params=validated,
                    paths=path_list,
                    registry=self._registry,
                )
            else:
                run = self._provider.apply(
                    root,
                    codemod_id=codemod,
                    params=validated,
                    paths=path_list,
                    registry=self._registry,
                    expected_hashes=expected_hashes,
                )
                if run.changed_files:
                    self._refresh_lsp(root, run.changed_files)
        except RefactorError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return CodemodResult(
                status="error",
                codemod=codemod,
                dry_run=dry_run,
                errors=[exc.message],
                error=exc.message,
                code=exc.code,
                summary=f"Codemod {codemod} failed: {exc.code}",
                metrics={"duration_ms": duration_ms, "result_chars": 0},
                details=dict(exc.details),
            )
        except ValueError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return CodemodResult(
                status="error",
                codemod=codemod,
                dry_run=dry_run,
                errors=[str(exc)],
                error=str(exc),
                code="SOURCE_NOT_FOUND",
                summary=f"Codemod {codemod} failed: SOURCE_NOT_FOUND",
                metrics={"duration_ms": duration_ms, "result_chars": 0},
                details={},
            )
        except FileNotFoundError as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return CodemodResult(
                status="error",
                codemod=codemod,
                dry_run=dry_run,
                errors=[str(exc)],
                error=str(exc),
                code="PROJECT_NOT_FOUND",
                summary=f"Codemod {codemod} failed: PROJECT_NOT_FOUND",
                metrics={"duration_ms": duration_ms, "result_chars": 0},
                details={},
            )

        duration_ms = int((time.perf_counter() - started) * 1000)
        files_changed = 0 if dry_run else run.files_changed
        metrics = {
            "duration_ms": duration_ms,
            "files_changed": files_changed,
            "transform_count": run.transform_count,
            "files_scanned": run.files_scanned,
            "files_matched": run.files_matched,
        }
        details: dict[str, object] = {}
        if dry_run:
            details["preview_hashes"] = {
                item.relative: item.content_hash for item in run.transforms
            }
        result = CodemodResult(
            status="success",
            codemod=codemod,
            dry_run=dry_run,
            files_scanned=run.files_scanned,
            files_matched=run.files_matched,
            files_changed=files_changed,
            transform_count=run.transform_count,
            changed_files=list(run.changed_files),
            warnings=list(run.warnings),
            errors=list(run.errors),
            summary=_summary(codemod, dry_run, run.files_matched, run.transform_count),
            metrics=metrics,
            details=details,
        )
        payload = result.model_dump_json()
        result.metrics["result_chars"] = len(payload)
        return result

    def _refresh_lsp(self, root: Path, changed_files: list[str]) -> None:
        service = self._semantic or SemanticService()
        manager = default_manager()
        paths = [root / rel for rel in changed_files]
        try:
            manager.runner.run(
                service.refresh(root, created=None, changed=paths, deleted=None)
            )
        except RefactorError:
            raise
        except Exception as exc:
            raise RefactorError(
                "PYRIGHT_UNAVAILABLE",
                f"LSP refresh after codemod failed: {exc}",
            ) from exc


def _summary(codemod: str, dry_run: bool, matched: int, transforms: int) -> str:
    mode = "Previewed" if dry_run else "Applied"
    return f"{mode} {codemod}: {matched} file(s), {transforms} transform(s)"
