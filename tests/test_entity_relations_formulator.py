"""Tests for :mod:`atman.core.services.entity_relations_formulator` (R9)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from atman.adapters.memory.in_memory_entity_registry import InMemoryEntityRegistry
from atman.adapters.memory.in_memory_entity_relation_store import (
    InMemoryEntityRelationStore,
)
from atman.adapters.reflection.mock_reflection_model import MockReflectionModel
from atman.adapters.storage.in_memory_state_store import InMemoryStateStore
from atman.core.models.entity import Entity, EntityType
from atman.core.models.experience import EmotionalDepth, FeltSense, KeyMoment
from atman.core.models.reflection import EntityRelationFormulationOutput
from atman.core.services.entity_relations_formulator import (
    DEFAULT_MIN_COOCCURRENCES,
    LEARNED_BY_REFLECTION,
    EntityRelationsFormulator,
)

AGENT_ID = UUID("00000000-0000-4000-8000-00000000aa11")


class _RelModel(MockReflectionModel):
    def __init__(
        self,
        *,
        relation_type: str = "colleague_of",
        confidence: float = 0.8,
    ) -> None:
        super().__init__()
        self.calls: list[tuple[UUID, UUID, int]] = []
        self._rel = relation_type
        self._conf = confidence

    def formulate_entity_relation(self, entity_a, entity_b, shared_moments):
        self.calls.append((entity_a.id, entity_b.id, len(shared_moments)))
        return EntityRelationFormulationOutput(relation_type=self._rel, confidence=self._conf)


class _RegistryStub(InMemoryEntityRegistry):
    def __init__(self, entities: list[Entity]):
        super().__init__()
        for e in entities:
            self._entities[e.id] = e  # type: ignore[attr-defined]


class _StateStoreStub(InMemoryStateStore):
    """InMemoryStateStore + an entity→[moment] index for the test."""

    def __init__(self) -> None:
        super().__init__()
        self._by_entity: dict[UUID, list[KeyMoment]] = {}

    def add(self, entity_id: UUID, moment: KeyMoment) -> None:
        self._by_entity.setdefault(entity_id, []).append(moment)

    def find_moments_by_entity(self, entity_id: UUID, *, limit: int = 20) -> list[KeyMoment]:
        return list(self._by_entity.get(entity_id, []))[:limit]


def _moment(when: datetime) -> KeyMoment:
    return KeyMoment(
        session_id=uuid4(),
        what_happened="e",
        when=when,
        how_i_felt=FeltSense(
            emotional_valence=0.0,
            emotional_intensity=0.5,
            depth=EmotionalDepth.MEANINGFUL,
        ),
        why_it_matters="t",
    )


def _make_pair_with_cooccurrences(state: _StateStoreStub, n: int) -> tuple[Entity, Entity]:
    base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    a = Entity(agent_id=AGENT_ID, canonical_name="Alice", entity_type=EntityType.person)
    b = Entity(agent_id=AGENT_ID, canonical_name="Bob", entity_type=EntityType.person)
    for i in range(n):
        m = _moment(base + timedelta(hours=i))
        state.add(a.id, m)
        state.add(b.id, m)
    return a, b


# ---------------------------------------------------------------------------
# Threshold logic
# ---------------------------------------------------------------------------


def test_below_cooccurrence_threshold_skips():
    state = _StateStoreStub()
    relations = InMemoryEntityRelationStore()
    model = _RelModel()
    a, b = _make_pair_with_cooccurrences(state, DEFAULT_MIN_COOCCURRENCES - 1)
    registry = _RegistryStub([a, b])
    fmt = EntityRelationsFormulator(state, registry, relations, model)  # type: ignore[arg-type]

    outcome = fmt.run(AGENT_ID)

    assert outcome.formulated == 0
    assert outcome.pairs_considered == 0
    assert model.calls == []
    assert relations.list_for_agent(AGENT_ID) == []


def test_at_threshold_persists_relation_as_learned_by_reflection():
    state = _StateStoreStub()
    relations = InMemoryEntityRelationStore()
    model = _RelModel()
    a, b = _make_pair_with_cooccurrences(state, DEFAULT_MIN_COOCCURRENCES)
    registry = _RegistryStub([a, b])
    fmt = EntityRelationsFormulator(state, registry, relations, model)  # type: ignore[arg-type]

    outcome = fmt.run(AGENT_ID)

    assert outcome.pairs_considered == 1
    assert outcome.formulated == 1
    rels = relations.list_for_agent(AGENT_ID)
    assert len(rels) == 1
    r = rels[0]
    assert r.learned_by == LEARNED_BY_REFLECTION
    assert r.relation_type == "colleague_of"
    # Pair stored in canonical-sorted order (sorted by str(uuid))
    expected_pair = tuple(sorted([a.id, b.id], key=str))
    assert (r.from_entity_id, r.to_entity_id) == expected_pair


# ---------------------------------------------------------------------------
# Confidence threshold
# ---------------------------------------------------------------------------


def test_low_confidence_is_skipped():
    state = _StateStoreStub()
    relations = InMemoryEntityRelationStore()
    model = _RelModel(confidence=0.5)  # below default 0.7
    a, b = _make_pair_with_cooccurrences(state, DEFAULT_MIN_COOCCURRENCES)
    registry = _RegistryStub([a, b])
    fmt = EntityRelationsFormulator(state, registry, relations, model)  # type: ignore[arg-type]

    outcome = fmt.run(AGENT_ID)

    assert outcome.pairs_considered == 1
    assert outcome.formulated == 0
    assert outcome.skipped == 1
    assert relations.list_for_agent(AGENT_ID) == []


def test_empty_relation_type_is_skipped():
    state = _StateStoreStub()
    relations = InMemoryEntityRelationStore()

    class _SilentModel(MockReflectionModel):
        def formulate_entity_relation(self, entity_a, entity_b, shared_moments):
            return EntityRelationFormulationOutput(relation_type="", confidence=0.95)

    a, b = _make_pair_with_cooccurrences(state, DEFAULT_MIN_COOCCURRENCES)
    registry = _RegistryStub([a, b])
    fmt = EntityRelationsFormulator(state, registry, relations, _SilentModel())  # type: ignore[arg-type]

    outcome = fmt.run(AGENT_ID)

    assert outcome.formulated == 0
    assert outcome.skipped == 1
    assert relations.list_for_agent(AGENT_ID) == []


# ---------------------------------------------------------------------------
# Idempotency / coexistence
# ---------------------------------------------------------------------------


def test_second_run_does_not_duplicate_relation():
    state = _StateStoreStub()
    relations = InMemoryEntityRelationStore()
    model = _RelModel()
    a, b = _make_pair_with_cooccurrences(state, DEFAULT_MIN_COOCCURRENCES)
    registry = _RegistryStub([a, b])
    fmt = EntityRelationsFormulator(state, registry, relations, model)  # type: ignore[arg-type]

    fmt.run(AGENT_ID)
    fmt.run(AGENT_ID)

    rels = relations.list_for_agent(AGENT_ID)
    assert len(rels) == 1  # dedup by (pair, type, learned_by)


def test_coexists_with_mrebel_relation_for_same_pair_and_type():
    state = _StateStoreStub()
    relations = InMemoryEntityRelationStore()
    a, b = _make_pair_with_cooccurrences(state, DEFAULT_MIN_COOCCURRENCES)
    expected_pair = tuple(sorted([a.id, b.id], key=str))

    # Pre-existing real-time extraction (mREBEL).
    from atman.core.models.entity import EntityRelation

    relations.add_relation(
        EntityRelation(
            agent_id=AGENT_ID,
            from_entity_id=expected_pair[0],
            to_entity_id=expected_pair[1],
            relation_type="colleague_of",
            confidence=0.95,
            learned_by="mrebel",
        )
    )
    model = _RelModel(confidence=0.8)
    registry = _RegistryStub([a, b])
    fmt = EntityRelationsFormulator(state, registry, relations, model)  # type: ignore[arg-type]

    fmt.run(AGENT_ID)

    # Two rows: one mrebel (untouched), one reflection (new).
    rels = relations.list_for_agent(AGENT_ID)
    learned_by_set = {r.learned_by for r in rels}
    assert learned_by_set == {"mrebel", LEARNED_BY_REFLECTION}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_fewer_than_two_entities_returns_zero():
    state = _StateStoreStub()
    relations = InMemoryEntityRelationStore()
    fmt = EntityRelationsFormulator(state, _RegistryStub([]), relations, _RelModel())  # type: ignore[arg-type]
    outcome = fmt.run(AGENT_ID)
    assert outcome.formulated == 0
    assert outcome.pairs_considered == 0


def test_default_reflection_model_returns_empty_relation():
    out = MockReflectionModel().formulate_entity_relation(
        Entity(agent_id=AGENT_ID, canonical_name="A", entity_type=EntityType.person),
        Entity(agent_id=AGENT_ID, canonical_name="B", entity_type=EntityType.person),
        [],
    )
    assert isinstance(out, EntityRelationFormulationOutput)
    assert out.relation_type == ""


def test_three_way_cooccurrence_emits_three_pairs():
    state = _StateStoreStub()
    relations = InMemoryEntityRelationStore()
    base = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    a = Entity(agent_id=AGENT_ID, canonical_name="A", entity_type=EntityType.person)
    b = Entity(agent_id=AGENT_ID, canonical_name="B", entity_type=EntityType.person)
    c = Entity(agent_id=AGENT_ID, canonical_name="C", entity_type=EntityType.person)
    for i in range(DEFAULT_MIN_COOCCURRENCES):
        m = _moment(base + timedelta(hours=i))
        state.add(a.id, m)
        state.add(b.id, m)
        state.add(c.id, m)
    model = _RelModel()
    fmt = EntityRelationsFormulator(state, _RegistryStub([a, b, c]), relations, model)  # type: ignore[arg-type]

    outcome = fmt.run(AGENT_ID)
    assert outcome.pairs_considered == 3  # AB, AC, BC
    assert outcome.formulated == 3


# ---------------------------------------------------------------------------
# `since` field propagation (Fix: was silently discarded)
# ---------------------------------------------------------------------------


def test_since_field_is_persisted_when_valid_iso_date():
    state = _StateStoreStub()
    relations = InMemoryEntityRelationStore()

    class _RelModelWithSince(MockReflectionModel):
        def formulate_entity_relation(self, entity_a, entity_b, shared_moments):
            return EntityRelationFormulationOutput(
                relation_type="colleague_of", confidence=0.8, since="2024-03-15"
            )

    a, b = _make_pair_with_cooccurrences(state, DEFAULT_MIN_COOCCURRENCES)
    fmt = EntityRelationsFormulator(state, _RegistryStub([a, b]), relations, _RelModelWithSince())  # type: ignore[arg-type]

    fmt.run(AGENT_ID)

    rels = relations.list_for_agent(AGENT_ID)
    assert len(rels) == 1
    from datetime import date

    assert rels[0].since == date(2024, 3, 15)


def test_invalid_since_field_is_ignored_relation_still_persisted():
    state = _StateStoreStub()
    relations = InMemoryEntityRelationStore()

    class _RelModelBadSince(MockReflectionModel):
        def formulate_entity_relation(self, entity_a, entity_b, shared_moments):
            return EntityRelationFormulationOutput(
                relation_type="colleague_of", confidence=0.8, since="not-a-date"
            )

    a, b = _make_pair_with_cooccurrences(state, DEFAULT_MIN_COOCCURRENCES)
    fmt = EntityRelationsFormulator(state, _RegistryStub([a, b]), relations, _RelModelBadSince())  # type: ignore[arg-type]

    outcome = fmt.run(AGENT_ID)

    assert outcome.formulated == 1
    rels = relations.list_for_agent(AGENT_ID)
    assert len(rels) == 1
    assert rels[0].since is None  # invalid date gracefully dropped


# ---------------------------------------------------------------------------
# Single-pass fetch optimization (Fix: double fetch eliminated)
# ---------------------------------------------------------------------------


def test_single_pass_fetch_calls_find_moments_by_entity_once_per_entity():
    """_index_entities_by_moment now returns both by_moment and moment_lookup
    in one pass; run() must not issue a second find_moments_by_entity loop."""
    call_counts: dict[UUID, int] = {}

    class _CountingStateStore(_StateStoreStub):
        def find_moments_by_entity(self, entity_id: UUID, *, limit: int = 20) -> list[KeyMoment]:
            call_counts[entity_id] = call_counts.get(entity_id, 0) + 1
            return super().find_moments_by_entity(entity_id, limit=limit)

    state = _CountingStateStore()
    relations = InMemoryEntityRelationStore()
    model = _RelModel()
    a, b = _make_pair_with_cooccurrences(state, DEFAULT_MIN_COOCCURRENCES)
    registry = _RegistryStub([a, b])
    fmt = EntityRelationsFormulator(state, registry, relations, model)  # type: ignore[arg-type]

    fmt.run(AGENT_ID)

    # Each entity must be queried exactly once (not twice as before).
    assert call_counts[a.id] == 1
    assert call_counts[b.id] == 1
