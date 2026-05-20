"""Unit tests for before_send operational-signal filtering."""

from __future__ import annotations

import sys

from atman.observability.scrubbing import (
    _REFLECTION_OVERLOAD_LOGGER,
    _make_before_send,
    _should_drop_operational_signal,
)


def _before_send(level: str = "minimal"):
    return _make_before_send(level)


def test_before_send_drops_reflection_overload_logger():
    event = {
        "logger": _REFLECTION_OVERLOAD_LOGGER,
        "level": "critical",
        "logentry": {"formatted": "reflection overload: daily cap exceeded"},
    }
    assert _before_send()(event, {}) is None


def test_before_send_drops_tests_stack_frame_unix():
    event = {
        "level": "error",
        "exception": {
            "values": [
                {
                    "stacktrace": {
                        "frames": [
                            {"abs_path": "/repo/src/atman/foo.py", "filename": "foo.py"},
                            {"abs_path": "/repo/tests/test_foo.py", "filename": "test_foo.py"},
                        ]
                    }
                }
            ]
        },
    }
    assert _before_send()(event, {}) is None


def test_before_send_drops_tests_stack_frame_windows():
    event = {
        "level": "error",
        "exception": {
            "values": [
                {
                    "stacktrace": {
                        "frames": [
                            {
                                "abs_path": r"C:\projects\atman\tests\test_bar.py",
                                "filename": "test_bar.py",
                            }
                        ]
                    }
                }
            ]
        },
    }
    assert _before_send()(event, {}) is None


def test_before_send_drops_tests_stack_from_hint_exc_info():
    try:
        raise RuntimeError("pytest noise")
    except RuntimeError:
        exc_info = sys.exc_info()
    event: dict = {"level": "error"}
    assert _before_send()(event, {"exc_info": exc_info}) is None


def test_before_send_drops_post_write_scheduler_error_message():
    event = {
        "level": "error",
        "logentry": {
            "formatted": "post-write scheduler raised for moment abc — continuing",
        },
    }
    assert _before_send()(event, {}) is None


def test_before_send_drops_failed_to_enqueue_error_message():
    event = {
        "level": "error",
        "logentry": {
            "formatted": "Failed to enqueue fact_entity_link for fact xyz — continuing",
        },
    }
    assert _before_send()(event, {}) is None


def test_before_send_keeps_operational_markers_at_warning():
    event = {
        "level": "warning",
        "logentry": {"formatted": "post-write scheduler raised for moment abc — continuing"},
    }
    result = _before_send()(event, {})
    assert result is event


def test_before_send_keeps_unrelated_error():
    event = {
        "level": "error",
        "logger": "atman.core.services.session_manager",
        "logentry": {"formatted": "unexpected persistence failure"},
        "exception": {
            "values": [
                {
                    "stacktrace": {
                        "frames": [
                            {"abs_path": "/repo/src/atman/core/services/session_manager.py"},
                        ]
                    }
                }
            ]
        },
    }
    result = _before_send()(event, {})
    assert result is event


def test_should_drop_operational_signal_direct():
    assert _should_drop_operational_signal({"logger": _REFLECTION_OVERLOAD_LOGGER}, {}) is True
    assert (
        _should_drop_operational_signal(
            {
                "level": "error",
                "exception": {
                    "values": [{"stacktrace": {"frames": [{"filename": "tests/test_x.py"}]}}]
                },
            },
            {},
        )
        is True
    )
    assert (
        _should_drop_operational_signal(
            {"level": "warning", "logentry": {"formatted": "Failed to enqueue x"}},
            {},
        )
        is False
    )
