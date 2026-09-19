from __future__ import annotations

from pydantic import BaseModel, Field

from python_refactor_mcp.models.common import Operation, ResultStatus


class RefactorResult(BaseModel):
    status: ResultStatus
    operation: Operation
    dry_run: bool
    source: str | None = None
    target: str | None = None
    files_changed: int = 0
    files_created: int = 0
    files_deleted: int = 0
    changed_files: list[str] = Field(default_factory=list)
    changed_files_truncated: bool = False
    remaining_old_references: int = 0
    leftover_samples: list[str] = Field(default_factory=list)
    leftover_replace_from: str | None = None
    leftover_replace_to: str | None = None
    next_action: str = ""
    empty_packages: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    git_dirty_before: bool = False
    verification: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
    summary: str | None = None
    metrics: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    details: dict[str, object] = Field(default_factory=dict)
    semantic_status: str | None = None
