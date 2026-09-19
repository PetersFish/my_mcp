from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OperationContext:
    operation_id: str
    project_root: Path
    operation_type: str
    changed_files: list[Path] = field(default_factory=list)
    created_files: list[Path] = field(default_factory=list)
    deleted_files: list[Path] = field(default_factory=list)
    semantic_status: str = "uninitialized"
    verification_status: str = "uninitialized"
    warnings: list[str] = field(default_factory=list)
