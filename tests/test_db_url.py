"""Tests for atman.db_url helpers (Sonar S2115)."""

from __future__ import annotations

import pytest

from atman.db_url import (
    DEFAULT_DEV_DATABASE_URL,
    DEFAULT_TEST_DATABASE_URL,
    require_password_in_database_url,
    resolve_database_url,
    with_password_if_missing,
)


def test_default_urls_include_password() -> None:
    assert ":atman@" in DEFAULT_DEV_DATABASE_URL
    assert ":atman@" in DEFAULT_TEST_DATABASE_URL


def test_resolve_database_url_prefers_explicit() -> None:
    url = resolve_database_url("postgresql://u:secret@db.example/test")
    assert url == "postgresql://u:secret@db.example/test"


def test_require_password_rejects_missing_password() -> None:
    with pytest.raises(ValueError, match="password"):
        require_password_in_database_url("postgresql://atman@localhost/atman")


def test_with_password_if_missing_injects_dev_default() -> None:
    url = with_password_if_missing("postgresql://atman@localhost:5432/atman")
    assert url == "postgresql://atman:atman@localhost:5432/atman"
