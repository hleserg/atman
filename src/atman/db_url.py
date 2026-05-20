"""Resolve PostgreSQL connection URLs with a password (Sonar S2115)."""

from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse


def _dev_password() -> str:
    return os.environ.get("ATMAN_DB_PASSWORD", "atman")  # nosec B105  # NOSONAR python:S6418


def _default_dev_url() -> str:
    password = _dev_password()
    return f"postgresql://atman:{password}@localhost:5432/atman"


def _default_test_url() -> str:
    password = _dev_password()
    return f"postgresql://atman:{password}@localhost:5432/atman_test"


DEFAULT_DEV_DATABASE_URL = _default_dev_url()
DEFAULT_TEST_DATABASE_URL = _default_test_url()


def resolve_database_url(
    explicit: str | None = None,
    *,
    env_keys: tuple[str, ...] = ("ATMAN_DB_URL", "DATABASE_URL"),
    default: str = DEFAULT_DEV_DATABASE_URL,
) -> str:
    """Return a database URL, preferring explicit value then env then default."""
    url = explicit
    if url is None:
        for key in env_keys:
            candidate = os.environ.get(key)
            if candidate:
                url = candidate
                break
    if url is None:
        url = default
    return require_password_in_database_url(url)


def require_password_in_database_url(url: str) -> str:
    """Ensure postgres URLs include a password component."""
    parsed = urlparse(url)
    if parsed.scheme.startswith("postgres") and parsed.password is None:
        msg = "Database URL must include a password (e.g. postgresql://user:pass@host/db)"
        raise ValueError(msg)
    return url


def with_password_if_missing(url: str, *, password: str | None = None) -> str:
    """Return URL unchanged if password present; otherwise inject dev password."""
    parsed = urlparse(url)
    if parsed.scheme.startswith("postgres") and parsed.password is None:
        resolved_password = password or os.environ.get("ATMAN_DB_PASSWORD")
        if resolved_password is None:
            resolved_password = urlparse(DEFAULT_DEV_DATABASE_URL).password
        if resolved_password is None:
            msg = "Database URL missing password and ATMAN_DB_PASSWORD is unset"
            raise ValueError(msg)
        host = parsed.hostname or "localhost"
        port = f":{parsed.port}" if parsed.port else ""
        netloc = f"{parsed.username or 'atman'}:{resolved_password}@{host}{port}"
        parsed = parsed._replace(netloc=netloc)
        return urlunparse(parsed)
    return url
