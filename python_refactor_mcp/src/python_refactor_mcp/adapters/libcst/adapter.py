from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import libcst as cst
from libcst.metadata import MetadataWrapper
from pydantic import BaseModel

from python_refactor_mcp.adapters.libcst.metadata import PREFERRED_PROVIDERS
from python_refactor_mcp.adapters.libcst.registry import CodemodRegistry
from python_refactor_mcp.models.errors import RefactorError
from python_refactor_mcp.services.verification_service import SKIP_DIRS
from python_refactor_mcp.utils.hashing import content_hash
from python_refactor_mcp.utils.paths import ensure_inside_project, resolve_project_root


@dataclass
class FileTransform:
    path: Path
    relative: str
    content_hash: str
    original: str
    transformed: str
    transform_count: int


@dataclass
class CodemodRunResult:
    files_scanned: int = 0
    files_matched: int = 0
    files_changed: int = 0
    transform_count: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    transforms: list[FileTransform] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)


class LibCSTCodemodProvider:
    def preview(
        self,
        project_root: str | Path,
        *,
        codemod_id: str,
        params: BaseModel,
        paths: list[str],
        registry: CodemodRegistry,
    ) -> CodemodRunResult:
        return self._run(
            project_root,
            codemod_id=codemod_id,
            params=params,
            paths=paths,
            registry=registry,
            write=False,
            expected_hashes=None,
        )

    def apply(
        self,
        project_root: str | Path,
        *,
        codemod_id: str,
        params: BaseModel,
        paths: list[str],
        registry: CodemodRegistry,
        expected_hashes: dict[str, str] | None = None,
    ) -> CodemodRunResult:
        return self._run(
            project_root,
            codemod_id=codemod_id,
            params=params,
            paths=paths,
            registry=registry,
            write=True,
            expected_hashes=expected_hashes,
        )

    def _run(
        self,
        project_root: str | Path,
        *,
        codemod_id: str,
        params: BaseModel,
        paths: list[str],
        registry: CodemodRegistry,
        write: bool,
        expected_hashes: dict[str, str] | None,
    ) -> CodemodRunResult:
        root = resolve_project_root(project_root)
        entry = registry.get(codemod_id)
        py_files = self._collect_python_files(root, paths)
        result = CodemodRunResult(files_scanned=len(py_files))
        planned: list[FileTransform] = []

        for path in py_files:
            try:
                source = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                raise RefactorError(
                    "CODEMOD_PARSE_ERROR",
                    f"cannot read {path.relative_to(root).as_posix()}: {exc}",
                ) from exc
            file_hash = content_hash(path)
            rel = path.relative_to(root).as_posix()
            if expected_hashes is not None and rel in expected_hashes:
                if expected_hashes[rel] != file_hash:
                    raise RefactorError(
                        "CONCURRENT_MODIFICATION",
                        f"file changed since preview: {rel}",
                        path=rel,
                    )
            try:
                module = cst.parse_module(source)
            except cst.ParserSyntaxError as exc:
                raise RefactorError(
                    "CODEMOD_PARSE_ERROR",
                    f"parse error in {rel}: {exc}",
                    path=rel,
                ) from exc

            transformer = entry.factory(params)
            try:
                wrapper = MetadataWrapper(module)
                # Ensure preferred providers are resolved when transformers declare them.
                _ = PREFERRED_PROVIDERS
                transformed_module = wrapper.visit(transformer)
            except Exception as exc:
                raise RefactorError(
                    "CODEMOD_PARSE_ERROR",
                    f"transform failed in {rel}: {exc}",
                    path=rel,
                ) from exc

            new_source = transformed_module.code
            count = int(getattr(transformer, "transform_count", 0) or 0)
            if new_source != source:
                if count == 0:
                    count = 1
                planned.append(
                    FileTransform(
                        path=path,
                        relative=rel,
                        content_hash=file_hash,
                        original=source,
                        transformed=new_source,
                        transform_count=count,
                    )
                )

        result.files_matched = len(planned)
        result.transform_count = sum(item.transform_count for item in planned)
        result.transforms = planned
        result.changed_files = [item.relative for item in planned]
        result.files_changed = len(planned) if write else 0

        if write and planned:
            self._atomic_write_all(planned)
            result.files_changed = len(planned)
        return result

    def _collect_python_files(self, root: Path, paths: list[str]) -> list[Path]:
        collected: list[Path] = []
        seen: set[Path] = set()
        for raw in paths or ["."]:
            try:
                target = ensure_inside_project(root, raw)
            except ValueError as exc:
                raise RefactorError("SOURCE_NOT_FOUND", str(exc)) from exc
            if target.is_file():
                if target.suffix == ".py" and target not in seen:
                    collected.append(target)
                    seen.add(target)
                continue
            if not target.exists():
                raise RefactorError("SOURCE_NOT_FOUND", f"path not found: {raw}")
            for path in sorted(target.rglob("*.py")):
                if any(part in SKIP_DIRS for part in path.parts):
                    continue
                try:
                    ensure_inside_project(root, path)
                except ValueError as exc:
                    raise RefactorError("SOURCE_NOT_FOUND", str(exc)) from exc
                if path not in seen:
                    collected.append(path)
                    seen.add(path)
        return collected

    def _atomic_write_all(self, planned: list[FileTransform]) -> None:
        written: list[tuple[Path, Path]] = []
        try:
            for item in planned:
                directory = item.path.parent
                fd, tmp_name = tempfile.mkstemp(
                    prefix=f".{item.path.name}.",
                    suffix=".tmp",
                    dir=directory,
                )
                tmp_path = Path(tmp_name)
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as handle:
                        handle.write(item.transformed)
                        handle.flush()
                        os.fsync(handle.fileno())
                    os.replace(tmp_path, item.path)
                    written.append((item.path, tmp_path))
                except Exception:
                    if tmp_path.exists():
                        tmp_path.unlink(missing_ok=True)
                    raise
        except Exception as exc:
            raise RefactorError(
                "CODEMOD_PARSE_ERROR",
                f"atomic write failed: {exc}",
            ) from exc
