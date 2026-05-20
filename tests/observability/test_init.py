"""Tests for init_observability() — HLE-240 P1.2 acceptance criteria."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

import atman.observability.sentry_init as mod
from atman.observability import init_observability, is_enabled


@pytest.fixture(autouse=True)
def reset_state():
    """Reset module-level flag between tests."""
    original = mod._initialized
    mod._initialized = False
    yield
    mod._initialized = original


# ---------------------------------------------------------------------------
# AC-2: off level must not import sentry_sdk
# ---------------------------------------------------------------------------


def test_off_level_is_noop():
    """off level returns immediately without touching sentry_sdk."""
    # Remove sentry_sdk from sys.modules to detect fresh import
    sentry_keys = [k for k in sys.modules if k.startswith("sentry_sdk")]
    saved = {k: sys.modules.pop(k) for k in sentry_keys}
    try:
        init_observability("off")
        # sentry_sdk must not have been (re)imported
        assert "sentry_sdk" not in sys.modules
    finally:
        sys.modules.update(saved)


def test_off_level_does_not_enable():
    init_observability("off")
    assert not is_enabled()


def test_off_level_env_var(monkeypatch):
    monkeypatch.setenv("ATMAN_OBS_LEVEL", "off")
    init_observability()
    assert not is_enabled()


def test_off_level_env_var_case_insensitive(monkeypatch):
    monkeypatch.setenv("ATMAN_OBS_LEVEL", " OFF ")
    init_observability()
    assert not is_enabled()


# ---------------------------------------------------------------------------
# Invalid level falls back to minimal (with warning)
# ---------------------------------------------------------------------------


def test_invalid_level_logs_warning(monkeypatch, caplog):
    monkeypatch.setenv("SENTRY_DSN", "")
    import logging

    with caplog.at_level(logging.WARNING, logger="atman.observability.sentry_init"):
        init_observability("bogus")
    assert any("bogus" in r.message for r in caplog.records)


def test_invalid_level_does_not_raise(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "")
    init_observability("bad_value")  # must not raise


# ---------------------------------------------------------------------------
# No DSN → no init (graceful no-op)
# ---------------------------------------------------------------------------


def test_no_dsn_is_noop(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "")
    init_observability("minimal")
    assert not is_enabled()


# ---------------------------------------------------------------------------
# Helper: run init with a fake DSN and mocked sentry_sdk.init
# ---------------------------------------------------------------------------


def _run_init_mocked(level: str, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setenv("SENTRY_DSN", "https://pub@fake.ingest.sentry.io/99")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "test")
    mock_init = MagicMock()
    with patch("sentry_sdk.init", mock_init):
        init_observability(level)
    return mock_init


# ---------------------------------------------------------------------------
# AC-3: verbose level sets debug=True
# ---------------------------------------------------------------------------


def test_verbose_debug_flag(monkeypatch):
    mock = _run_init_mocked("verbose", monkeypatch)
    mock.assert_called_once()
    _, kwargs = mock.call_args
    assert kwargs.get("debug") is True


# ---------------------------------------------------------------------------
# AC-4: debug level integrations include AsyncioIntegration
# ---------------------------------------------------------------------------


def test_debug_includes_asyncio_integration(monkeypatch):
    from sentry_sdk.integrations.asyncio import AsyncioIntegration

    mock = _run_init_mocked("debug", monkeypatch)
    mock.assert_called_once()
    _, kwargs = mock.call_args
    integrations = kwargs.get("integrations", [])
    assert any(isinstance(i, AsyncioIntegration) for i in integrations)


def test_verbose_includes_asyncio_integration(monkeypatch):
    from sentry_sdk.integrations.asyncio import AsyncioIntegration

    mock = _run_init_mocked("verbose", monkeypatch)
    _, kwargs = mock.call_args
    integrations = kwargs.get("integrations", [])
    assert any(isinstance(i, AsyncioIntegration) for i in integrations)


def test_minimal_includes_asyncio_integration(monkeypatch):
    from sentry_sdk.integrations.asyncio import AsyncioIntegration

    mock = _run_init_mocked("minimal", monkeypatch)
    _, kwargs = mock.call_args
    integrations = kwargs.get("integrations", [])
    assert any(isinstance(i, AsyncioIntegration) for i in integrations)


def test_minimal_includes_traces_sampler(monkeypatch):
    """minimal must include traces_sampler so AI ops are boosted to 1.0 in prod."""
    from atman.observability.sampling import _traces_sampler

    mock = _run_init_mocked("minimal", monkeypatch)
    _, kwargs = mock.call_args
    assert kwargs.get("traces_sampler") is _traces_sampler
    assert "traces_sample_rate" not in kwargs


def test_debug_uses_full_sample_rate(monkeypatch):
    """debug level must use traces_sample_rate=1.0 (100% tracing for full dev waterfall)."""
    mock = _run_init_mocked("debug", monkeypatch)
    _, kwargs = mock.call_args
    assert kwargs.get("traces_sample_rate") == pytest.approx(1.0)
    assert "traces_sampler" not in kwargs


def test_verbose_uses_full_sample_rate(monkeypatch):
    """verbose level must use traces_sample_rate=1.0 (100% tracing)."""
    mock = _run_init_mocked("verbose", monkeypatch)
    _, kwargs = mock.call_args
    assert kwargs.get("traces_sample_rate") == pytest.approx(1.0)
    assert "traces_sampler" not in kwargs


def test_enable_logs_is_always_set(monkeypatch):
    """enable_logs=True must be passed to sentry_sdk.init for structured logging."""
    for level in ("minimal", "debug", "verbose"):
        mock = _run_init_mocked(level, monkeypatch)
        _, kwargs = mock.call_args
        assert kwargs.get("enable_logs") is True, f"enable_logs missing for level={level}"
        mod._initialized = False  # reset for next iteration


# ---------------------------------------------------------------------------
# AC-5: before_send_transaction drops /health
# ---------------------------------------------------------------------------


def test_before_send_transaction_drops_health(monkeypatch):
    mock = _run_init_mocked("minimal", monkeypatch)
    _, kwargs = mock.call_args
    bst = kwargs.get("before_send_transaction")
    assert bst is not None

    health_event = {"transaction": "/health", "type": "transaction"}
    assert bst(health_event, {}) is None

    healthz_event = {"transaction": "/healthz", "type": "transaction"}
    assert bst(healthz_event, {}) is None

    real_event = {"transaction": "/api/agent", "type": "transaction"}
    result = bst(real_event, {})
    assert result == real_event  # Sonar S5796; hook returns same dict
    assert result is real_event


def test_before_send_transaction_passes_normal(monkeypatch):
    mock = _run_init_mocked("debug", monkeypatch)
    _, kwargs = mock.call_args
    bst = kwargs.get("before_send_transaction")
    event = {"transaction": "/api/memory", "type": "transaction"}
    result = bst(event, {})
    assert result == event  # Sonar S5796; hook returns same dict
    assert result is event


# ---------------------------------------------------------------------------
# AC-6: _traces_sampler returns 1.0 for gen_ai ops
# ---------------------------------------------------------------------------


def test_traces_sampler_boosts_gen_ai():
    from atman.observability.sampling import _traces_sampler

    # SDK 2.x: custom_sampling_context items are spread into the root dict
    ctx = {"gen_ai.operation.name": "chat"}
    assert _traces_sampler(ctx) == pytest.approx(1.0)


def test_traces_sampler_boosts_ai_route():
    from atman.observability.sampling import _traces_sampler

    # SDK 2.x: transaction name lives under span_context.name
    ctx = {"span_context": {"name": "/api/agent/start"}}
    assert _traces_sampler(ctx) == pytest.approx(1.0)


def test_traces_sampler_default():
    from atman.observability.sampling import _traces_sampler

    ctx: dict = {}
    assert _traces_sampler(ctx) == pytest.approx(0.1)


def test_traces_sampler_inherits_parent_true():
    from atman.observability.sampling import _traces_sampler

    # SDK 2.x: parent_sampled lives under span_context.parent_sampled
    ctx = {"span_context": {"parent_sampled": True}}
    assert _traces_sampler(ctx) == pytest.approx(1.0)


def test_traces_sampler_inherits_parent_false():
    from atman.observability.sampling import _traces_sampler

    ctx = {"span_context": {"parent_sampled": False}}
    assert _traces_sampler(ctx) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Idempotency: second call is a no-op
# ---------------------------------------------------------------------------


def test_init_is_idempotent(monkeypatch):
    mock = _run_init_mocked("minimal", monkeypatch)
    assert mock.call_count == 1
    # Second call: _initialized is True now, so sentry_sdk.init not called again
    with patch("sentry_sdk.init") as mock2:
        init_observability("minimal")
    mock2.assert_not_called()


# ---------------------------------------------------------------------------
# is_enabled() state
# ---------------------------------------------------------------------------


def test_is_enabled_after_init(monkeypatch):
    _run_init_mocked("minimal", monkeypatch)
    assert is_enabled()


def test_is_enabled_false_when_not_init():
    assert not is_enabled()
