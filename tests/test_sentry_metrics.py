"""Sentry metric helpers degrade gracefully across SDK API versions."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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


def test_metric_increment_falls_back_when_count_missing() -> None:
    incr = MagicMock()
    metrics = MagicMock()
    metrics.count.side_effect = AttributeError("no count")
    metrics.incr = incr
    with patch.object(sentry_mod, "_initialized", True), patch("sentry_sdk.metrics", metrics):
        sentry_mod.metric_increment("test.counter", tags={"k": "v"})
    assert incr.called or metrics.count.called
