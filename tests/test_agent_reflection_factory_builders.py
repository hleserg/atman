"""Tests for Daily/Deep reflection service builders in agent factory."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from atman.adapters.agent.factory import (
    _build_reflection_model,
    _MockReflectionModel,
    _StateStoreIdentityRepo,
    _StateStoreNarrativeRepo,
    build_daily_reflection_service,
    build_deep_reflection_service,
)
from atman.adapters.reflection.mock_reflection_model import MockReflectionModel
from atman.adapters.storage.file_state_store import FileStateStore
from atman.cli_reflection import (
    _bootstrap_live_workspace,
    _parse_live_date_end,
    _parse_live_date_start,
)
from atman.core.models import LayerType, NarrativeDocument, NarrativeLayer
from atman.core.models.identity import Identity
from atman.core.models.reflection import ReflectionLevel
from atman.core.services.reflection_service import DailyReflectionService, DeepReflectionService


@pytest.fixture
def file_store_with_identity(tmp_path: Path) -> tuple:
    agent_id = uuid4()
    store = FileStateStore(tmp_path / "ws")
    identity = Identity(id=agent_id, self_description="e2e agent")
    store.save_identity(identity)
    return agent_id, store


def test_build_daily_reflection_service_reflects_empty_day(
    file_store_with_identity: tuple,
) -> None:
    agent_id, store = file_store_with_identity
    service = build_daily_reflection_service(agent_id, store)
    assert isinstance(service, DailyReflectionService)

    event = service.reflect(datetime.now(UTC))
    assert event.reflection_level == ReflectionLevel.DAILY


def test_build_daily_reflection_service_survives_embedding_failure(
    monkeypatch: pytest.MonkeyPatch,
    file_store_with_identity: tuple,
) -> None:
    def _raise() -> None:
        raise RuntimeError("embedding backend unavailable")

    monkeypatch.setattr("atman.config.build_embedding_adapter", _raise)

    agent_id, store = file_store_with_identity
    service = build_daily_reflection_service(agent_id, store)
    assert isinstance(service, DailyReflectionService)


def test_build_daily_reflection_service_falls_back_when_postgres_entity_adapters_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from atman.adapters.state.postgres_state_store import PostgresStateStore

    agent_id = uuid4()
    store = MagicMock(spec=PostgresStateStore)
    store.load_identity.return_value = None
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("postgres unavailable")

    monkeypatch.setattr(
        "atman.adapters.memory.postgres_entity_registry.PostgresEntityRegistry",
        _raise,
    )

    service = build_daily_reflection_service(agent_id, store)
    event = service.reflect(datetime.now(UTC))
    assert event.reflection_level == ReflectionLevel.DAILY


def test_build_daily_reflection_service_uses_postgres_entity_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from atman.adapters.state.postgres_state_store import PostgresStateStore

    agent_id = uuid4()
    store = MagicMock(spec=PostgresStateStore)
    store.load_identity.return_value = None
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")

    class _FakeRegistry:
        def __init__(self, db_url: str) -> None:
            self.db_url = db_url

    class _FakeStance:
        def __init__(self, db_url: str) -> None:
            self.db_url = db_url

    monkeypatch.setattr(
        "atman.adapters.memory.postgres_entity_registry.PostgresEntityRegistry",
        _FakeRegistry,
    )
    monkeypatch.setattr(
        "atman.adapters.memory.postgres_entity_stance.PostgresEntityStanceStore",
        _FakeStance,
    )

    service = build_daily_reflection_service(agent_id, store)
    event = service.reflect(datetime.now(UTC))
    assert event.reflection_level == ReflectionLevel.DAILY


def test_build_deep_reflection_service_reflects_empty_range(
    file_store_with_identity: tuple,
) -> None:
    agent_id, store = file_store_with_identity
    service = build_deep_reflection_service(agent_id, store)
    assert isinstance(service, DeepReflectionService)

    now = datetime.now(UTC)
    since = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    event = service.reflect(since, now)
    assert event.reflection_level == ReflectionLevel.DEEP


def test_build_reflection_model_defaults_to_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATMAN_LLM_BASE_URL", raising=False)
    model = _build_reflection_model()
    assert isinstance(model, _MockReflectionModel)


def test_build_reflection_model_honors_override() -> None:
    override = MockReflectionModel()
    model = _build_reflection_model(override)
    assert model is override


def test_build_reflection_model_falls_back_when_openai_init_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATMAN_LLM_BASE_URL", "http://localhost:11434/v1")

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("unavailable")

    monkeypatch.setattr(
        "atman.adapters.reflection.openai_reflection_model.OpenAIReflectionModel",
        _raise,
    )
    model = _build_reflection_model()
    assert isinstance(model, _MockReflectionModel)


def test_build_reflection_model_uses_openai_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ATMAN_LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("ATMAN_LLM_API_KEY", "test-key")

    class _FakeOpenAIModel:
        def __init__(self, config: object) -> None:
            self.config = config

    monkeypatch.setattr(
        "atman.adapters.reflection.openai_reflection_model.OpenAIReflectionModel",
        _FakeOpenAIModel,
    )
    model = _build_reflection_model()
    assert isinstance(model, _FakeOpenAIModel)


def test_build_daily_reflection_service_accepts_model_override(
    file_store_with_identity: tuple,
) -> None:
    agent_id, store = file_store_with_identity
    override = MockReflectionModel()
    service = build_daily_reflection_service(agent_id, store, reflection_model=override)
    assert service.reflection_model is override


def test_state_store_identity_repo_roundtrip(file_store_with_identity: tuple) -> None:
    agent_id, store = file_store_with_identity
    repo = _StateStoreIdentityRepo(store, agent_id)
    current = repo.get_current()
    assert current is not None
    assert current.id == agent_id
    repo.update(current.model_copy(update={"self_description": "updated"}))
    again = repo.get_current()
    assert again is not None
    assert again.self_description == "updated"
    snap = repo.create_snapshot(again, "checkpoint", "smoke test")
    assert snap.identity_id == agent_id
    history = repo.get_history()
    assert len(history) == 1
    assert history[0].description == "checkpoint"
    assert repo.get_snapshot(snap.id) == snap
    assert repo.get_snapshot(uuid4()) is None


def test_state_store_narrative_repo_save_and_load(file_store_with_identity: tuple) -> None:
    agent_id, store = file_store_with_identity
    repo = _StateStoreNarrativeRepo(store, agent_id)
    assert repo.get_current() is None
    doc = NarrativeDocument(
        identity_id=agent_id,
        core_layer=NarrativeLayer(layer_type=LayerType.CORE, content="core"),
        recent_layer=NarrativeLayer(layer_type=LayerType.RECENT, content="recent"),
    )
    repo.update(doc)
    loaded = repo.get_current()
    assert loaded is not None
    assert loaded.recent_layer.content == "recent"
    assert repo.get_history() == []


def test_bootstrap_live_workspace_creates_identity_and_narrative(tmp_path: Path) -> None:
    agent_id = uuid4()
    store = FileStateStore(tmp_path / "bootstrap")
    _bootstrap_live_workspace(store, agent_id)
    identity = store.load_identity(agent_id)
    assert identity is not None
    assert store.load_narrative(identity.id) is not None


def test_parse_live_date_start_date_only() -> None:
    dt = _parse_live_date_start("2026-05-15")
    assert dt.tzinfo == UTC
    assert dt.hour == 0 and dt.minute == 0


def test_parse_live_date_start_converts_timezone() -> None:
    dt = _parse_live_date_start("2026-05-15T10:00:00+03:00")
    assert dt.tzinfo == UTC
    assert dt.hour == 7


def test_parse_live_date_end_date_only() -> None:
    dt = _parse_live_date_end("2026-05-15")
    assert dt.tzinfo == UTC
    assert dt == datetime.combine(datetime.fromisoformat("2026-05-15").date(), time.max, tzinfo=UTC)


def test_parse_live_date_end_converts_timezone() -> None:
    dt = _parse_live_date_end("2026-05-15T22:00:00+03:00")
    assert dt.tzinfo == UTC
    assert dt.hour == 19
