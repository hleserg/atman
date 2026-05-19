"""Unit tests for session preflight helpers (no subprocess / network by default)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from atman.adapters.agent.preflight import (
    PreflightError,
    _pg_url,
    _repo_root,
    check_llm,
    check_nlp_packages,
    check_postgres,
    is_warmup_needed,
)


def test_preflight_error_is_exception() -> None:
    with pytest.raises(PreflightError, match="db down"):
        raise PreflightError("db down")


def test_pg_url_built_from_postgres_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_USER", "atman")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")
    monkeypatch.setenv("POSTGRES_HOST", "db.local")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "atman_db")
    url = _pg_url()
    assert url == "postgresql://atman:secret@db.local:5433/atman_db"


def test_pg_url_falls_back_to_atman_db_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("POSTGRES_USER", raising=False)
    monkeypatch.setenv("ATMAN_DB_URL", "postgresql://fallback/db")
    assert _pg_url() == "postgresql://fallback/db"


def test_repo_root_points_at_workspace() -> None:
    root = Path(_repo_root())
    assert (root / "pyproject.toml").is_file()


def test_check_nlp_packages_reports_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(
        name: str,
        globals: dict[str, object] | None = None,
        locals: dict[str, object] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> object:
        if name in ("gliner", "FlagEmbedding"):
            raise ImportError(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    missing = check_nlp_packages()
    assert set(missing) == {"gliner", "FlagEmbedding"}


def test_check_postgres_empty_url() -> None:
    ok, detail = check_postgres("")
    assert ok is False
    assert "No DB URL" in detail


def test_check_postgres_success(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = MagicMock()
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = False
    mock_psycopg = MagicMock()
    mock_psycopg.connect.return_value = conn
    monkeypatch.setitem(__import__("sys").modules, "psycopg", mock_psycopg)

    ok, detail = check_postgres("postgresql://u:p@localhost/db")
    assert ok is True
    assert detail == ""


def test_check_llm_success(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = MagicMock()
    resp.status_code = 200
    mock_httpx = MagicMock()
    mock_httpx.get.return_value = resp
    monkeypatch.setitem(__import__("sys").modules, "httpx", mock_httpx)

    ok, detail = check_llm("http://llm.local/v1")
    assert ok is True
    assert detail == ""


def test_is_warmup_needed_when_cache_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    assert is_warmup_needed() is True


def test_is_warmup_needed_when_model_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hub = tmp_path / "hub" / "models--BAAI--bge-m3"
    hub.mkdir(parents=True)
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    assert is_warmup_needed() is False
