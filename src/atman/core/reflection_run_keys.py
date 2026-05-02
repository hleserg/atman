"""Deterministic reflection job keys and stable UUID derivation."""

from __future__ import annotations

import hashlib
from datetime import datetime
from uuid import UUID, uuid5

from atman.core.clock_impl import ensure_utc

# DNS namespace is arbitrary but stable for uuid5 derivation.
_REFLECTION_UUID_NS = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
_PATTERN_UUID_NS = UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")
_HEALTH_UUID_NS = UUID("6ba7b812-9dad-11d1-80b4-00c04fd430c8")


def _calendar_day_utc(dt: datetime) -> str:
    d = ensure_utc(dt).date()
    return d.isoformat()


def daily_reflection_run_key_empty_day(calendar_anchor: datetime) -> str:
    """Run key when the day has no experiences to analyze."""
    return f"daily|v1|{_calendar_day_utc(calendar_anchor)}|empty"


def daily_reflection_run_key_no_identity(
    calendar_anchor: datetime, experience_ids: list[UUID]
) -> str:
    """Run key when reflection is skipped because identity is missing."""
    digest = hashlib.sha256(
        "|".join(sorted(str(i) for i in experience_ids)).encode("utf-8")
    ).hexdigest()[:24]
    return f"daily|v1|{_calendar_day_utc(calendar_anchor)}|no_identity|{digest}"


def daily_reflection_run_key_for_identity(calendar_anchor: datetime, identity_id: UUID) -> str:
    """Run key for a normal daily reflection tied to a calendar day and identity."""
    return f"daily|v1|{_calendar_day_utc(calendar_anchor)}|identity|{identity_id}"


def deep_reflection_run_key_empty(since: datetime, until: datetime) -> str:
    """Run key when the deep window has no experiences."""
    s, u = ensure_utc(since).isoformat(), ensure_utc(until).isoformat()
    return f"deep|v1|empty|{s}|{u}"


def deep_reflection_run_key_no_identity(
    since: datetime, until: datetime, experience_ids: list[UUID]
) -> str:
    """Run key when deep reflection is skipped (no identity)."""
    s, u = ensure_utc(since).isoformat(), ensure_utc(until).isoformat()
    digest = hashlib.sha256(
        "|".join(sorted(str(i) for i in experience_ids)).encode("utf-8")
    ).hexdigest()[:24]
    return f"deep|v1|no_identity|{s}|{u}|{digest}"


def deep_reflection_run_key_for_identity(
    since: datetime, until: datetime, identity_id: UUID
) -> str:
    """Run key for deep reflection over a window and identity."""
    s, u = ensure_utc(since).isoformat(), ensure_utc(until).isoformat()
    return f"deep|v1|identity|{identity_id}|{s}|{u}"


def reflection_event_id_for_run_key(run_key: str) -> UUID:
    """Stable event id so upserts and retries address the same row."""
    return uuid5(_REFLECTION_UUID_NS, run_key)


def pattern_id_for_detection_key(detection_key: str) -> UUID:
    """Stable pattern id for idempotent pattern detection."""
    return uuid5(_PATTERN_UUID_NS, detection_key)


def health_assessment_id_for_run_key(run_key: str) -> UUID:
    """Stable health assessment id for the same deep reflection job."""
    return uuid5(_HEALTH_UUID_NS, run_key)


def daily_pattern_detection_key(run_key: str, pattern_type_value: str) -> str:
    """Fingerprint for a single daily pattern slot."""
    return f"pattern|daily|{run_key}|{pattern_type_value}"


def deep_pattern_detection_key(run_key: str, pattern_type_value: str) -> str:
    """Fingerprint for a deep pattern slot (one per pattern type)."""
    return f"pattern|deep|{run_key}|{pattern_type_value}"


def reframing_trigger_key(run_key: str, experience_id: UUID) -> str:
    """Stable ``triggered_by`` for deduplicating reframing per job and experience."""
    return f"reflection|{run_key}|reframe|{experience_id}"
