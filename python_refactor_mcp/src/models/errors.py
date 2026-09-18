from __future__ import annotations

from typing import Literal

ErrorCode = Literal[
    "PROJECT_NOT_FOUND",
    "SOURCE_NOT_FOUND",
    "SYMBOL_NOT_FOUND",
    "AMBIGUOUS_SYMBOL",
    "TARGET_CONFLICT",
    "PYRIGHT_NOT_FOUND",
    "PYRIGHT_UNAVAILABLE",
    "PYRIGHT_TIMEOUT",
    "LSP_PROTOCOL_ERROR",
    "TSP_PROTOCOL_ERROR",
    "ROPE_ERROR",
    "CODEMOD_NOT_FOUND",
    "CODEMOD_PARSE_ERROR",
    "CODEMOD_VALIDATION_ERROR",
    "CONCURRENT_MODIFICATION",
    "RUFF_UNAVAILABLE",
    "PYTEST_UNAVAILABLE",
    "VERIFICATION_FAILED",
]


class RefactorError(Exception):
    def __init__(self, code: ErrorCode, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": "error",
            "code": self.code,
            "message": self.message,
        }
        payload.update(self.details)
        return payload
