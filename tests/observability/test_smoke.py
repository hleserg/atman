"""Smoke tests for all 4 obs levels × all 3 init entrypoints (HLE-244).

Entrypoints tested:
  1. init_observability()  — atman.observability (new canonical)
  2. init_sentry_from_env() — atman.adapters.observability.sentry (legacy)

Levels: off | minimal | debug | verbose

Each combination verifies:
  - No crash
  - off: sentry_sdk.init never called, is_enabled() → False
  - non-off without DSN: graceful no-op, is_enabled() → False
  - non-off with DSN: sentry_sdk.init called once, is_enabled() → True
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

import atman.observability.sentry_init as _new_mod
from atman.adapters.observability import sentry as _legacy_mod
from atman.observability import init_observability, is_enabled

_FAKE_DSN = "https://pub@fake.ingest.sentry.io/99"
_ALL_LEVELS = ("off", "minimal", "debug", "verbose")
_NON_OFF = ("minimal", "debug", "verbose")


@pytest.fixture(autouse=True)
def _reset_state():
    orig_new = _new_mod._initialized
    orig_legacy = _legacy_mod._initialized
    yield
    _new_mod._initialized = orig_new
    _legacy_mod._initialized = orig_legacy


# ---------------------------------------------------------------------------
# Entrypoint 1: init_observability() — canonical
# ---------------------------------------------------------------------------


class TestNewEntrypointAllLevels:
    @pytest.mark.parametrize("level", _ALL_LEVELS)
    def test_does_not_raise(self, level: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", _FAKE_DSN)
        with patch("sentry_sdk.init", MagicMock()):
            init_observability(level)

    def test_off_never_calls_sdk_init(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", _FAKE_DSN)
        with patch("sentry_sdk.init") as mock_init:
            init_observability("off")
        mock_init.assert_not_called()

    def test_off_is_enabled_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", _FAKE_DSN)
        init_observability("off")
        assert not is_enabled()

    @pytest.mark.parametrize("level", _NON_OFF)
    def test_non_off_no_dsn_graceful(self, level: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", "")
        init_observability(level)
        assert not is_enabled()

    @pytest.mark.parametrize("level", _NON_OFF)
    def test_non_off_with_dsn_calls_sdk_init(
        self, level: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SENTRY_DSN", _FAKE_DSN)
        with patch("sentry_sdk.init", MagicMock()) as mock_init:
            init_observability(level)
        mock_init.assert_called_once()

    @pytest.mark.parametrize("level", _NON_OFF)
    def test_non_off_with_dsn_is_enabled(self, level: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", _FAKE_DSN)
        with patch("sentry_sdk.init", MagicMock()):
            init_observability(level)
        assert is_enabled()

    def test_off_level_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", _FAKE_DSN)
        with patch("sentry_sdk.init") as mock_init:
            init_observability("OFF")
        mock_init.assert_not_called()
        assert not is_enabled()

    def test_off_level_with_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", _FAKE_DSN)
        with patch("sentry_sdk.init") as mock_init:
            init_observability("  off  ")
        mock_init.assert_not_called()

    def test_off_via_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", _FAKE_DSN)
        monkeypatch.setenv("ATMAN_OBS_LEVEL", "off")
        with patch("sentry_sdk.init") as mock_init:
            init_observability()
        mock_init.assert_not_called()

    def test_idempotent_second_call_no_reinit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", _FAKE_DSN)
        with patch("sentry_sdk.init", MagicMock()) as mock_init:
            init_observability("minimal")
            init_observability("minimal")
        mock_init.assert_called_once()


# ---------------------------------------------------------------------------
# Entrypoint 2: init_sentry_from_env() — legacy adapter
# ---------------------------------------------------------------------------


class TestLegacyEntrypointAllLevels:
    @pytest.mark.parametrize("level", _ALL_LEVELS)
    def test_does_not_raise(self, level: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", _FAKE_DSN)
        monkeypatch.setenv("ATMAN_OBS_LEVEL", level)
        with patch("sentry_sdk.init", MagicMock()):
            _legacy_mod.init_sentry_from_env()

    def test_off_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", _FAKE_DSN)
        monkeypatch.setenv("ATMAN_OBS_LEVEL", "off")
        result = _legacy_mod.init_sentry_from_env()
        assert result is False

    def test_off_legacy_initialized_stays_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", _FAKE_DSN)
        monkeypatch.setenv("ATMAN_OBS_LEVEL", "off")
        _legacy_mod.init_sentry_from_env()
        assert _legacy_mod._initialized is False

    def test_no_dsn_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", "")
        monkeypatch.setenv("ATMAN_OBS_LEVEL", "minimal")
        result = _legacy_mod.init_sentry_from_env()
        assert result is False

    def test_with_dsn_non_off_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SENTRY_DSN", _FAKE_DSN)
        monkeypatch.setenv("ATMAN_OBS_LEVEL", "minimal")
        with patch("sentry_sdk.init", MagicMock()):
            result = _legacy_mod.init_sentry_from_env()
        assert result is True


# ---------------------------------------------------------------------------
# Cross-entrypoint: off level never imports sentry_sdk
# ---------------------------------------------------------------------------


def test_off_level_does_not_import_sentry_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies the true no-op guarantee: sentry_sdk is not imported at off level."""
    monkeypatch.setenv("SENTRY_DSN", _FAKE_DSN)
    # Evict sentry_sdk from sys.modules to detect a fresh import
    sentry_keys = [k for k in sys.modules if k.startswith("sentry_sdk")]
    saved = {k: sys.modules.pop(k) for k in sentry_keys}
    try:
        init_observability("off")
        assert "sentry_sdk" not in sys.modules
    finally:
        sys.modules.update(saved)
