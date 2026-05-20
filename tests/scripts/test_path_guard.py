"""Tests for scripts.codemap.path_guard."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.codemap.path_guard import resolve_under_root, write_text_under_root


def test_resolve_under_root_rejects_escape(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    with pytest.raises(ValueError, match="escapes trusted root"):
        resolve_under_root(outside, root=root)


def test_write_text_under_root_writes_inside_repo(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    target = root / "nested" / "file.txt"
    write_text_under_root(target, "hello", root=root)
    assert target.read_text(encoding="utf-8") == "hello"
