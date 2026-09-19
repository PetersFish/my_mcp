from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Operation = Literal["move_module", "rename_module", "rename_symbol", "move_symbol"]
VerifyStep = Literal["residual", "ruff", "pyright", "pytest"]
ResultStatus = Literal["success", "error", "conflict"]
SemanticMode = Literal["best_effort", "required"]


@dataclass(frozen=True)
class SourcePosition:
    path: Path
    line: int
    character: int
