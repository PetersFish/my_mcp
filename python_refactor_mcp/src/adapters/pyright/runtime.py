from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


@dataclass(frozen=True)
class PyrightRuntime:
    cli: Path | None
    language_server: Path
    type_server: Path | None
    version: str
    source: Literal["explicit", "project", "mcp_fallback"]
