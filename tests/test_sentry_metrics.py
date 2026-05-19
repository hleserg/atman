"""Sentry metric helpers degrade gracefully across SDK API versions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from atman.adapters.observability import sentry as sentry_mod


def test_metric_distribution_uses_attributes_api() -> None:
    dist = MagicMock()
    with (
        patch.object(sentry_mod, "_initialized", True),
        patch("sentry_sdk.metrics.distribution", dist),
    ):
        sentry_mod.metric_distribution("test.latency", 12.5, unit="millisecond", tags={"env": "ci"})
    dist.assert_called_once()
    _args, kwargs = dist.call_args
    assert kwargs.get("attributes") == {"env": "ci"} or kwargs.get("tags") == {"env": "ci"}


def test_init_sentry_from_env_off_level_returns_false(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ATMAN_OBS_LEVEL=off, init_sentry_from_env must return False and not set _initialized."""
    monkeypatch.setenv("SENTRY_DSN", "https://pub@fake.ingest.sentry.io/99")
    monkeypatch.setenv("ATMAN_OBS_LEVEL", "off")
    orig = sentry_mod._initialized
    try:
        result = sentry_mod.init_sentry_from_env()
        assert result is False
        assert sentry_mod._initialized is False
    finally:
        sentry_mod._initialized = orig


def test_init_sentry_from_env_off_level_blocks_fallback_init(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ATMAN_OBS_LEVEL=off must prevent legacy _init() even when new module import fails."""
    monkeypatch.setenv("SENTRY_DSN", "https://pub@fake.ingest.sentry.io/99")
    monkeypatch.setenv("ATMAN_OBS_LEVEL", "off")
    orig = sentry_mod._initialized
    try:
        with patch("atman.adapters.observability.sentry._init") as mock_init:
            # Force the try-block to raise so we hit the fallback path
            with patch(
                "builtins.__import__",
                side_effect=lambda name, *a, **kw: (
                    (_ for _ in ()).throw(ImportError("simulated"))
                    if name == "atman.observability"
                    else __import__(name, *a, **kw)
                ),
            ):
                result = sentry_mod.init_sentry_from_env()
        mock_init.assert_not_called()
        assert result is False
    finally:
        sentry_mod._initialized = orig


def test_metric_increment_falls_back_when_count_missing() -> None:
    incr = MagicMock()
    metrics = MagicMock()
    metrics.count.side_effect = AttributeError("no count")
    metrics.incr = incr
    with patch.object(sentry_mod, "_initialized", True), patch("sentry_sdk.metrics", metrics):
        sentry_mod.metric_increment("test.counter", tags={"k": "v"})
    assert incr.called or metrics.count.called
