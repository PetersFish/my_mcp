from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "mini_pkg"
SAMPLE_PROJECT_ROOT = Path(__file__).parent / "fixtures" / "sample_project"


@pytest.fixture
def mini_pkg(tmp_path: Path) -> Path:
    dest = tmp_path / "proj"
    shutil.copytree(FIXTURE_ROOT, dest)
    return dest


@pytest.fixture
def sample_project(tmp_path: Path) -> Path:
    dest = tmp_path / "sample"
    shutil.copytree(SAMPLE_PROJECT_ROOT, dest)
    return dest


@pytest.fixture
def mini_pkg(tmp_path: Path) -> Path:
    dest = tmp_path / "proj"
    shutil.copytree(FIXTURE_ROOT, dest)
    return dest
