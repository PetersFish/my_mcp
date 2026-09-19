from __future__ import annotations

from libcst.metadata import (
    ParentNodeProvider,
    PositionProvider,
    QualifiedNameProvider,
    ScopeProvider,
)

PREFERRED_PROVIDERS = (
    PositionProvider,
    ScopeProvider,
    QualifiedNameProvider,
    ParentNodeProvider,
)
