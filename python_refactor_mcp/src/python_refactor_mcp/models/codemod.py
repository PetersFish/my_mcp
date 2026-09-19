from __future__ import annotations

from pydantic import BaseModel, Field

from python_refactor_mcp.models.common import ResultStatus


class FileHashRecord(BaseModel):
    path: str
    content_hash: str


class CodemodResult(BaseModel):
    status: ResultStatus
    codemod: str
    dry_run: bool
    files_scanned: int = 0
    files_matched: int = 0
    files_changed: int = 0
    transform_count: int = 0
    changed_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    summary: str | None = None
    metrics: dict[str, int] = Field(default_factory=dict)
    details: dict[str, object] = Field(default_factory=dict)
    error: str | None = None
    code: str | None = None
