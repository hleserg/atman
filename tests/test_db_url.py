"""Tests for atman.db_url helpers (Sonar S2115)."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

import pytest

from atman.db_url import (
    DEFAULT_DEV_DATABASE_URL,
    DEFAULT_TEST_DATABASE_URL,
    require_password_in_database_url,
    resolve_database_url,
    with_password_if_missing,
)


def _url_without_password(source: str) -> str:
    parsed = urlparse(source)
    host = parsed.hostname or "localhost"
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{parsed.username or 'atman'}@{host}{port}"
    return urlunparse(parsed._replace(netloc=netloc))


def test_default_urls_include_password() -> None:
    assert urlparse(DEFAULT_DEV_DATABASE_URL).password is not None
    assert urlparse(DEFAULT_TEST_DATABASE_URL).password is not None


def test_resolve_database_url_prefers_explicit() -> None:
    url = resolve_database_url("postgresql://u:secret@db.example/test")
    assert url == "postgresql://u:secret@db.example/test"


def test_require_password_rejects_missing_password() -> None:
    no_password_url = _url_without_password(DEFAULT_DEV_DATABASE_URL)
    with pytest.raises(ValueError, match="password"):
        require_password_in_database_url(no_password_url)  # NOSONAR python:S2115 — negative test


def test_resolve_database_url_injects_password_when_missing() -> None:
    url = resolve_database_url(_url_without_password(DEFAULT_DEV_DATABASE_URL))
    assert urlparse(url).password == urlparse(DEFAULT_DEV_DATABASE_URL).password
    url = with_password_if_missing(_url_without_password(DEFAULT_DEV_DATABASE_URL))
    assert urlparse(url).password == urlparse(DEFAULT_DEV_DATABASE_URL).password
