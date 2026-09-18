from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Operation = Literal["move_module", "rename_module", "rename_symbol", "move_symbol"]
VerifyStep = Literal["residual", "ruff", "pyright", "pytest"]
ResultStatus = Literal["success", "error", "conflict"]


class RefactorRequest(BaseModel):
    operation: Operation
    project_root: str
    source: str | None = None
    target: str | None = None
    module: str | None = None
    symbol: str | None = None
    new_name: str | None = None
    dry_run: bool = False
    verify: list[VerifyStep] = Field(default_factory=lambda: ["residual"])
    pytest_args: list[str] | None = None
    source_root: str | None = None

    @field_validator("project_root")
    @classmethod
    def project_root_must_be_absolute_dir(cls, value: str) -> str:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("project_root must be an absolute path")
        if not path.exists():
            raise ValueError("project_root must exist")
        if not path.is_dir():
            raise ValueError("project_root must be a directory")
        return str(path)

    @model_validator(mode="after")
    def validate_operation_fields(self) -> RefactorRequest:
        if self.symbol is not None and self.symbol.count(".") > 1:
            raise ValueError("symbol may be Name or Class.method only")

        if self.operation == "move_module":
            if not self.source or not self.target:
                raise ValueError("move_module requires source and target")
        elif self.operation == "rename_module":
            if not self.source or not self.new_name:
                raise ValueError("rename_module requires source and new_name")
            if "." in self.new_name:
                raise ValueError(
                    "rename_module new_name must be a single identifier; "
                    "use move_module to change package"
                )
        elif self.operation == "rename_symbol":
            if not self.module or not self.symbol or not self.new_name:
                raise ValueError("rename_symbol requires module, symbol, and new_name")
            if "." in self.new_name:
                raise ValueError("new_name must be a single identifier")
        elif self.operation == "move_symbol":
            if not self.module or not self.symbol or not self.target:
                raise ValueError("move_symbol requires module, symbol, and target")
        return self


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
    conflicts: list[str] = Field(default_factory=list)
    git_dirty_before: bool = False
    verification: dict[str, str] = Field(default_factory=dict)
    error: str | None = None
