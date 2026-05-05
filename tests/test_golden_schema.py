"""
P2.7 — Golden schema / snapshot stability tests.

Embeds known-good JSON fixtures as inline strings. If any model field is
renamed, removed, or its type changes in a backwards-incompatible way, these
tests fail immediately — before any file-store migration can hide the breakage.

The fixtures represent the *minimum viable* structure: only required fields,
no optional ones. This makes the test maximally sensitive to breaking changes
while not requiring updates when optional fields are added.

SYSTEM_MAP §2.1 / §5.3 regression freeze.
"""

from __future__ import annotations

from atman.core.models import (
    Eigenstate,
    ExperienceRecord,
    NarrativeDocument,
)
from atman.core.models.fact import FactRecord

# ---------------------------------------------------------------------------
# ExperienceRecord
# ---------------------------------------------------------------------------

_GOLDEN_EXPERIENCE = """{
  "schema_version": "1.0",
  "experience": {
    "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "session_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
    "timestamp": "2025-01-15T09:00:00+00:00",
    "key_moments": [
      {
        "id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        "what_happened": "golden schema test moment",
        "how_i_felt": {
          "emotional_valence": 0.3,
          "emotional_intensity": 0.7,
          "depth": "meaningful",
          "physical_sensation": null,
          "cognitive_state": null
        },
        "why_it_matters": "schema stability",
        "values_touched": ["honesty"],
        "reframing_notes": []
      }
    ],
    "reframing_notes": [],
    "salience": 1.0,
    "access_count": 0,
    "last_accessed_at": "2025-01-15T09:00:00+00:00"
  }
}"""


def test_golden_experience_record_deserializes() -> None:
    record = ExperienceRecord.model_validate_json(_GOLDEN_EXPERIENCE)
    assert str(record.experience.id) == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert record.experience.key_moments[0].what_happened == "golden schema test moment"
    assert record.experience.key_moments[0].how_i_felt.depth.value == "meaningful"
    assert record.experience.salience == 1.0
    assert record.experience.access_count == 0


# ---------------------------------------------------------------------------
# NarrativeDocument
# ---------------------------------------------------------------------------

_GOLDEN_NARRATIVE = """{
  "id": "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  "identity_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
  "created_at": "2025-01-15T09:00:00+00:00",
  "updated_at": "2025-01-15T09:00:00+00:00",
  "core_layer": {
    "layer_type": "core",
    "content": "I exist at the ground zero.",
    "updated_at": "2025-01-15T09:00:00+00:00"
  },
  "recent_layer": {
    "layer_type": "recent",
    "content": "No recent experiences yet.",
    "updated_at": "2025-01-15T09:00:00+00:00"
  },
  "threads": [],
  "schema_version": "1.0"
}"""


def test_golden_narrative_document_deserializes() -> None:
    narrative = NarrativeDocument.model_validate_json(_GOLDEN_NARRATIVE)
    assert str(narrative.id) == "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
    assert str(narrative.identity_id) == "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
    assert narrative.core_layer.content == "I exist at the ground zero."
    assert narrative.recent_layer.content == "No recent experiences yet."


# ---------------------------------------------------------------------------
# Eigenstate
# ---------------------------------------------------------------------------

_GOLDEN_EIGENSTATE = """{
  "id": "ffffffff-ffff-4fff-8fff-ffffffffffff",
  "session_id": "11111111-1111-4111-8111-111111111111",
  "timestamp": "2025-01-15T09:00:00+00:00",
  "emotional_tone": 0.2,
  "emotional_intensity": 0.4,
  "cognitive_load": 0.3,
  "open_threads": ["unresolved question A"],
  "dominant_themes": ["growth"],
  "unresolved_tensions": [],
  "session_summary": "A focused session.",
  "key_insight": "Progress is possible."
}"""


def test_golden_eigenstate_deserializes() -> None:
    e = Eigenstate.model_validate_json(_GOLDEN_EIGENSTATE)
    assert str(e.id) == "ffffffff-ffff-4fff-8fff-ffffffffffff"
    assert e.dominant_themes == ["growth"]
    assert e.key_insight == "Progress is possible."
    assert e.schema_version == "1.0.0"


# ---------------------------------------------------------------------------
# FactRecord (factual memory)
# ---------------------------------------------------------------------------

_GOLDEN_FACT = """{
  "id": "22222222-2222-4222-8222-222222222222",
  "content": "Golden fact content",
  "source": "test",
  "tags": ["knowledge", "test"],
  "created_at": "2025-01-15T09:00:00+00:00",
  "updated_at": "2025-01-15T09:00:00+00:00",
  "relations": [],
  "metadata": {}
}"""


def test_golden_fact_record_deserializes() -> None:
    fact = FactRecord.model_validate_json(_GOLDEN_FACT)
    assert str(fact.id) == "22222222-2222-4222-8222-222222222222"
    assert fact.content == "Golden fact content"
    assert "knowledge" in fact.tags


# ---------------------------------------------------------------------------
# Stability of re-serialization: deserialize → serialize → deserialize
# ---------------------------------------------------------------------------


def test_experience_double_roundtrip_is_stable() -> None:
    """Serialize → deserialize twice; the result must be identical."""
    r1 = ExperienceRecord.model_validate_json(_GOLDEN_EXPERIENCE)
    j = r1.model_dump_json()
    r2 = ExperienceRecord.model_validate_json(j)
    assert r2.experience.id == r1.experience.id
    assert r2.experience.key_moments[0].what_happened == r1.experience.key_moments[0].what_happened


def test_narrative_double_roundtrip_is_stable() -> None:
    n1 = NarrativeDocument.model_validate_json(_GOLDEN_NARRATIVE)
    j = n1.model_dump_json()
    n2 = NarrativeDocument.model_validate_json(j)
    assert n2.id == n1.id
    assert n2.core_layer.content == n1.core_layer.content


def test_eigenstate_double_roundtrip_is_stable() -> None:
    e1 = Eigenstate.model_validate_json(_GOLDEN_EIGENSTATE)
    j = e1.model_dump_json()
    e2 = Eigenstate.model_validate_json(j)
    assert e2.id == e1.id
    assert e2.dominant_themes == e1.dominant_themes
