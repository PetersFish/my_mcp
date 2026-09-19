from __future__ import annotations

import hashlib
from pathlib import Path


def content_hash(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()
