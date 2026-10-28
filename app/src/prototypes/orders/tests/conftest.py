"""Shared fixtures: the invented company, and a cache that holds its mirrored site."""
from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import pytest

OWNER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(OWNER))
FIXTURES = Path(__file__).resolve().parent / "fixtures"

from pipeline import common  # noqa: E402


@pytest.fixture
def companies(tmp_path: Path) -> Path:
    """A companies folder with one invented company."""
    folder = tmp_path / "companies"
    (folder / "example-steel").mkdir(parents=True)
    for name in ("company.json", "mapping.py"):
        shutil.copy(FIXTURES / "example-steel" / name, folder / "example-steel" / name)
    return folder


@pytest.fixture
def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A cache outside the repository holding that company's mirror and a stand-in three.js."""
    root = tmp_path / "cache"
    shutil.copytree(FIXTURES / "example-steel" / "site", root / "example-steel" / "site")
    stand_in = b"/* three.js stand-in for tests */\n"
    (root / "_vendor").mkdir()
    (root / "_vendor" / "three.min.js").write_bytes(stand_in)
    monkeypatch.setenv(common.CACHE_ENV, str(root))
    monkeypatch.setattr(common, "THREE_SHA256", hashlib.sha256(stand_in).hexdigest())
    return root


@pytest.fixture
def example(companies: Path, cache: Path) -> dict:
    return common.company("example-steel", companies / "example-steel")
