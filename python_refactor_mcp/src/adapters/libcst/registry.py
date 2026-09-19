from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from python_refactor_mcp.models.errors import RefactorError

TransformerFactory = Callable[[BaseModel], Any]


@dataclass(frozen=True)
class CodemodEntry:
    id: str
    description: str
    params_model: type[BaseModel]
    factory: TransformerFactory


class CodemodRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, CodemodEntry] = {}

    def register(
        self,
        codemod_id: str,
        factory: TransformerFactory,
        params_model: type[BaseModel],
        *,
        description: str = "",
    ) -> None:
        self._entries[codemod_id] = CodemodEntry(
            id=codemod_id,
            description=description,
            params_model=params_model,
            factory=factory,
        )

    def get(self, codemod_id: str) -> CodemodEntry:
        entry = self._entries.get(codemod_id)
        if entry is None:
            raise RefactorError("CODEMOD_NOT_FOUND", f"unknown codemod: {codemod_id}")
        return entry

    def list_ids(self) -> list[str]:
        return sorted(self._entries)

    def validate_params(self, codemod_id: str, params: dict[str, object] | None) -> BaseModel:
        entry = self.get(codemod_id)
        try:
            return entry.params_model.model_validate(params or {})
        except ValidationError as exc:
            raise RefactorError(
                "CODEMOD_VALIDATION_ERROR",
                f"invalid params for {codemod_id}: {exc.error_count()} error(s)",
                errors=exc.errors(),
            ) from exc
