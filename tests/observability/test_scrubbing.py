"""Tests for PII scrubbing helpers — HLE-240 P1.2."""

from __future__ import annotations

import pytest

from atman.observability.scrubbing import (
    _HEALTH_ROUTES,
    _LLM_IO_KEYS,
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
    result = fn(event, {})
    assert result == event  # Sonar S5796; hook returns same dict (scrubbing.py)
    assert result is event


def test_before_send_drops_reflection_overload_logger():
    fn = _make_before_send("minimal")
    event = {"logger": "atman.reflection.overload", "message": "reflection overload: too deep"}
    assert fn(event, {}) is None


def test_before_send_drops_pytest_stack_frames():
    fn = _make_before_send("minimal")
    event = {
        "exception": {
            "values": [
                {
                    "stacktrace": {
                        "frames": [
                            {"filename": "tests/test_post_write_wiring.py", "lineno": 108},
                        ]
                    }
                }
            ]
        }
    }
    assert fn(event, {}) is None


def test_before_send_transaction_drops_health():
    fn = _make_before_send_transaction("minimal")
    for route in _HEALTH_ROUTES:
        event = {"transaction": route}
        assert fn(event, {}) is None, f"Expected {route} to be dropped"


def test_before_send_transaction_keeps_api():
    fn = _make_before_send_transaction("minimal")
    event = {"transaction": "/api/chat"}
    result = fn(event, {})
    assert result == event  # Sonar S5796; hook returns same dict (scrubbing.py)
    assert result is event


def test_before_send_transaction_keeps_empty():
    fn = _make_before_send_transaction("debug")
    event = {"transaction": ""}
    result = fn(event, {})
    assert result == event  # Sonar S5796; hook returns same dict (scrubbing.py)
    assert result is event


def test_health_routes_set():
    assert "/health" in _HEALTH_ROUTES
    assert "/healthz" in _HEALTH_ROUTES
    assert "/metrics" in _HEALTH_ROUTES
    assert "/livez" in _HEALTH_ROUTES
    assert "/readyz" in _HEALTH_ROUTES


def test_send_prompts_off_by_default(monkeypatch):
    monkeypatch.delenv("ATMAN_SEND_PROMPTS", raising=False)
    scrubber = make_event_scrubber("debug")
    assert "prompt" in scrubber.denylist
    assert "completion" in scrubber.denylist


@pytest.mark.parametrize("level", ["debug", "verbose"])
def test_send_prompts_enabled_removes_llm_keys(monkeypatch, level):
    monkeypatch.setenv("ATMAN_SEND_PROMPTS", "1")
    scrubber = make_event_scrubber(level)
    for key in _LLM_IO_KEYS:
        assert key not in scrubber.denylist, f"Expected {key!r} absent when ATMAN_SEND_PROMPTS=1"


def test_send_prompts_ignored_at_minimal_level(monkeypatch):
    monkeypatch.setenv("ATMAN_SEND_PROMPTS", "1")
    scrubber = make_event_scrubber("minimal")
    assert "prompt" in scrubber.denylist
    assert "completion" in scrubber.denylist


def test_send_prompts_non_llm_keys_always_scrubbed(monkeypatch):
    monkeypatch.setenv("ATMAN_SEND_PROMPTS", "1")
    scrubber = make_event_scrubber("verbose")
    assert "memory_content" in scrubber.denylist
    assert "reflection_text" in scrubber.denylist
    assert "identity_payload" in scrubber.denylist
