from __future__ import annotations

import os

import pytest

os.environ.setdefault("INSPECT_DISPLAY", "none")


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("INSPECT_CACHE_DIR", str(tmp_path / "inspect-cache"))
