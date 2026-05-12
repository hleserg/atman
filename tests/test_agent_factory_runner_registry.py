"""Unit tests for agent factory, runner lifecycle, and AgentsRegistry (mocked DB)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from atman.adapters.agent.config import AgentConfig, ModelConfig
from atman.adapters.agent.factory import build_deps
from atman.adapters.agent.runner import (
    AtmanRunner,
    _extract_thinking,
    _finalize_open_session,
)
from atman.agents_registry import AgentsRegistry


def test_build_deps_returns_wired_container(tmp_path) -> None:
    agent_id = uuid4()
    deps, session_manager, state_store = build_deps(tmp_path / "agws", agent_id, AgentConfig())
    assert deps.state_store is state_store
    assert deps.session_manager is session_manager
    assert deps.identity_service is not None


@pytest.mark.asyncio
async def test_atman_runner_run_session_with_test_model(tmp_path) -> None:
    agent_id = uuid4()
    runner = AtmanRunner(
        tmp_path / "w",
        agent_id,
        AgentConfig(model=ModelConfig(model="test")),
    )
    runner.ensure_identity()
    replies = await runner.run_session(["hello"])
    assert len(replies) == 1
    assert isinstance(replies[0], str)


@pytest.mark.asyncio
async def test_run_session_finally_closes_on_agent_error(tmp_path) -> None:
    agent_id = uuid4()
    runner = AtmanRunner(
        tmp_path / "w2",
        agent_id,
        AgentConfig(model=ModelConfig(model="test")),
    )
    runner.ensure_identity()

    async def _boom(*_a, **_kw):
        raise RuntimeError("simulated model failure")

    runner._agent = SimpleNamespace(run=_boom)  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="simulated model failure"):
        await runner.run_session(["x"])

    assert runner._session_manager.list_active_sessions() == []


def test_finalize_open_session_closes_empty_session(tmp_path) -> None:
    agent_id = uuid4()
    deps, session_manager, _state = build_deps(tmp_path / "w3", agent_id, AgentConfig())
    deps.identity_service.bootstrap_identity(agent_id)
    from atman.core.models import LayerType, NarrativeDocument, NarrativeLayer

    narrative = NarrativeDocument(
        id=uuid4(),
        identity_id=agent_id,
        core_layer=NarrativeLayer(layer_type=LayerType.CORE, content="core"),
        recent_layer=NarrativeLayer(layer_type=LayerType.RECENT, content="recent"),
    )
    deps.state_store.save_narrative(narrative)

    ctx = session_manager.start_session(agent_id)
    session_id = ctx.session_id
    _finalize_open_session(
        session_manager,
        deps.micro_reflection,
        session_id,
        key_insight="cleanup",
    )
    assert session_manager.get_active_session(session_id) is None


def test_extract_thinking_swallows_malformed_result() -> None:
    class Bad:
        def all_messages(self):
            raise AttributeError("nope")

    assert _extract_thinking(Bad()) is None


def test_agents_registry_get_by_serial_none() -> None:
    with patch("atman.agents_registry.psycopg.connect") as connect:
        conn = MagicMock()
        connect.return_value.__enter__.return_value = conn
        conn.execute.return_value.fetchone.return_value = None
        reg = AgentsRegistry("postgresql://app/db")
        assert reg.get_by_serial(99) is None


def test_agents_registry_create_returns_record() -> None:
    uid = uuid4()
    created = datetime.now(UTC)
    row = (3, uid, "nm", "desc", created)

    with patch("atman.agents_registry.psycopg.connect") as connect:
        conn = MagicMock()
        connect.return_value.__enter__.return_value = conn
        cur = MagicMock()
        cur.fetchone.return_value = row
        conn.execute.return_value = cur

        reg = AgentsRegistry("postgresql://app/db", admin_url="postgresql://admin/db")
        rec = reg.create(description="d", name="n")

    assert rec.serial_id == 3
    assert rec.uuid == uid
    assert rec.name == "nm"
    assert conn.execute.call_count >= 2
