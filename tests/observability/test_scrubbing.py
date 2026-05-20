"""Tests for PII scrubbing helpers — HLE-240 P1.2."""

from __future__ import annotations

from atman.observability.scrubbing import (
    _HEALTH_ROUTES,
    ATMAN_EXTRA_KEYS,
    _make_before_send,
    _make_before_send_transaction,
    make_event_scrubber,
)


def test_atman_extra_keys_non_empty():
    assert len(ATMAN_EXTRA_KEYS) > 0
    assert "memory_content" in ATMAN_EXTRA_KEYS
    assert "prompt" in ATMAN_EXTRA_KEYS
    assert "embedding" in ATMAN_EXTRA_KEYS


def test_make_event_scrubber_returns_scrubber():
    scrubber = make_event_scrubber("minimal")
    assert scrubber is not None


def test_make_event_scrubber_debug_level():
    scrubber = make_event_scrubber("debug")
    assert scrubber is not None


def test_make_event_scrubber_verbose_level():
    scrubber = make_event_scrubber("verbose")
    assert scrubber is not None


def test_before_send_passes_event():
    fn = _make_before_send("minimal")
    event = {"message": "test", "level": "error"}
    assert fn(event, {}) is event


def test_before_send_transaction_drops_health():
    fn = _make_before_send_transaction("minimal")
    for route in _HEALTH_ROUTES:
        event = {"transaction": route}
        assert fn(event, {}) is None, f"Expected {route} to be dropped"


def test_before_send_transaction_keeps_api():
    fn = _make_before_send_transaction("minimal")
    event = {"transaction": "/api/chat"}
    assert fn(event, {}) is event


def test_before_send_transaction_keeps_empty():
    fn = _make_before_send_transaction("debug")
    event = {"transaction": ""}
    assert fn(event, {}) is event


def test_health_routes_set():
    assert "/health" in _HEALTH_ROUTES
    assert "/healthz" in _HEALTH_ROUTES
    assert "/metrics" in _HEALTH_ROUTES
    assert "/livez" in _HEALTH_ROUTES
    assert "/readyz" in _HEALTH_ROUTES
