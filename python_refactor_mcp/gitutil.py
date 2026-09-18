from __future__ import annotations

import subprocess
from pathlib import Path


def snapshot_porcelain(project_root: str | Path) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]
