"""DB-free unit tests for PostgresStateStore serialization helpers."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from atman.adapters.state.postgres_state_store import _parse_key_moment
from atman.core.models import EmotionalDepth, FeltSense, KeyMoment


@pytest.fixture
def sample_key_moment() -> KeyMoment:
    """Create a representative key moment payload."""
    return KeyMoment(
        id=uuid4(),
        what_happened="Persisted JSONB payload",
        when=datetime(2026, 5, 12, 10, 30, 0, tzinfo=UTC),
        how_i_felt=FeltSense(
            emotional_valence=0.2,
            emotional_intensity=0.7,
            depth=EmotionalDepth.MEANINGFUL,
        ),
        why_it_matters="Parser coverage without a live PostgreSQL instance",
        values_touched=["reliability"],
        principles_confirmed=["test_storage_boundaries"],
        fact_refs=[uuid4()],
    )


def test_parse_key_moment_accepts_jsonb_dict_payload(sample_key_moment: KeyMoment) -> None:
    """Rows returned as decoded JSONB dicts round-trip into KeyMoment models."""
    row = {"data": sample_key_moment.model_dump(mode="json")}

    parsed = _parse_key_moment(row)

    assert parsed == sample_key_moment


def test_parse_key_moment_accepts_json_string_payload(sample_key_moment: KeyMoment) -> None:
    """Rows returned as JSON strings are decoded before model validation."""
    row = {"data": json.dumps(sample_key_moment.model_dump(mode="json"))}

    parsed = _parse_key_moment(row)

    assert parsed == sample_key_moment


def test_parse_key_moment_rejects_invalid_payload_shape() -> None:
    """Malformed persisted data fails loudly instead of producing partial moments."""
    row = {"data": {"id": str(uuid4()), "what_happened": "missing required fields"}}

    with pytest.raises(ValidationError):
        _parse_key_moment(row)
