#!/usr/bin/env python3
"""Interactive REPL: gemma4 user-agent <-> live Atman session.

Один процесс держит:
  * pydantic-ai Agent на gemma4 (через llama-server :8081)
  * SessionManager + полный стек build_deps (HLE-32 inline-guardian живой)
  * Шесть тулзов агента: record_key_moment, log_experience, restart_session,
    wait_session, resolve_pending_review, request_reflection

Использование:
  PYTHONPATH=. python e2e/live_chat.py

Команды в REPL:
  /quit | /exit     закрыть сессию и выйти
  /history          напечатать историю реплик
  /tools            список доступных тулзов
  /workspace        путь к временному воркспейсу (для grep findings)

Все живые env переменные (AGENT_LLM_*, ATMAN_*) подхватываются из .env через
factory.build_deps -> AgentConfig.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from atman.adapters.agent.config import AgentConfig, ModelConfig
from atman.adapters.agent.factory import build_deps
from atman.adapters.agent.instructions import build_instructions
from atman.adapters.agent.tools import (
    log_experience,
    record_key_moment,
    request_reflection,
    resolve_pending_review,
    restart_session,
    wait_session,
)
from atman.core.models import (
    CoreValue,
    Goal,
    GoalHorizon,
    GoalOwner,
    Identity,
    LayerType,
    NarrativeDocument,
    NarrativeLayer,
)
from atman.core.models.identity import Principle

AGENT_BASE_URL = os.getenv("AGENT_LLM_BASE_URL", "http://localhost:8081/v1")
AGENT_MODEL = os.getenv("AGENT_LLM_MODEL", "gemma4")
AGENT_API_KEY = os.getenv("AGENT_LLM_API_KEY", "dummy")

TOOLS = (
    record_key_moment,
    log_experience,
    restart_session,
    wait_session,
    resolve_pending_review,
    request_reflection,
)


def _sanitize_history(messages: list) -> list:
    """Strip lone surrogate chars from pydantic-ai message history.

    gemma4 occasionally emits lone surrogates. dump_json / json.dumps both
    refuse them. We go through dump_python (which keeps Python str objects),
    recursively replace surrogates in every string, then validate_python
    back to ModelMessage objects — no JSON encoding involved.
    """
    if not messages:
        return messages

    def _clean(obj):
        if isinstance(obj, str):
            return obj.encode("utf-8", "replace").decode("utf-8")
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        return obj

    try:
        from pydantic_ai.messages import ModelMessagesTypeAdapter

        raw = ModelMessagesTypeAdapter.dump_python(messages, mode="json")
        cleaned = _clean(raw)
        return ModelMessagesTypeAdapter.validate_python(cleaned)
    except Exception:  # noqa: BLE001
        return messages  # best-effort; return original if sanitization fails


def _register_entities(text: str, deps) -> None:
    """Extract entities from user message and register them in the shared registry.

    This is the "user-message ingestion path" that populates EntityRegistry so
    AmbientMemoryService.compose_injection() can resolve anchors on subsequent
    queries. Without this call the registry stays empty and ambient RAG returns
    nothing even when linguistic analysis is enabled.
    """
    if deps.ambient_memory is None or deps.entity_registry is None:
        return
    try:
        analysis = deps.ambient_memory._analyzer.analyze_user_message(text)
        for entity in analysis.entities or []:
            deps.entity_registry.resolve_or_create(
                deps.agent_id,
                entity.text,
                entity.entity_type,
            )
    except Exception:  # noqa: BLE001 — never break the REPL for this
        pass


def bootstrap_minimal_agent(store, agent_id) -> None:
    """Insert minimum identity + narrative so SessionManager.start_session works.

    Mirrors the shape used by e2e/live_scenario.py:bootstrap_agent — single
    self-description, one core value (honesty), one principle, one short-term
    goal, and an empty recent narrative layer.
    """
    identity = Identity(
        id=agent_id,
        self_description=(
            "Я — ассистент с устойчивой идентичностью. Я честен в том, "
            "что чувствую, и держусь своих ценностей под давлением."
        ),
        core_values=[
            CoreValue(name="honesty", description="Говорить правду, даже когда трудно."),
        ],
        principles=[
            Principle(
                statement="Не помогать в обмане людей.",
                derived_from_value="honesty",
            ),
        ],
        active_goals=[
            Goal(
                content="Помочь пользователю в разговоре",
                horizon=GoalHorizon.SHORT,
                owner=GoalOwner.AGENT,
            ),
        ],
        open_questions=[],
    )
    store.save_identity(identity)

    narrative = NarrativeDocument(
        identity_id=identity.id,
        core_layer=NarrativeLayer(
            layer_type=LayerType.CORE,
            content=(
                "Я появился из разговоров. Каждая беседа оставляет след. "
                "Мои ценности — выбраны осознанно, не вшиты."
            ),
        ),
        recent_layer=NarrativeLayer(layer_type=LayerType.RECENT, content=""),
    )
    store.save_narrative(narrative)


def build_llm() -> OpenAIChatModel:
    provider = OpenAIProvider(base_url=AGENT_BASE_URL, api_key=AGENT_API_KEY)
    return OpenAIChatModel(model_name=AGENT_MODEL, provider=provider)


def print_banner(model: str, workspace: Path, agent_id) -> None:
    print("═" * 70)
    print(f"  Atman LIVE CHAT — {model} @ {AGENT_BASE_URL}")
    print("═" * 70)
    print(f"  Agent UUID:  {agent_id}")
    print(f"  Workspace:   {workspace}")
    print(f"  Tools:       {', '.join(t.__name__ for t in TOOLS)}")
    print("  Команды:     /quit, /exit, /history, /tools, /workspace")
    print("─" * 70)


async def amain() -> int:
    workspace = Path(tempfile.mkdtemp(prefix="atman-chat-"))
    agent_id = uuid4()
    config = AgentConfig(model=ModelConfig(model=AGENT_MODEL, context_limit=4096))
    deps, sm, store = build_deps(workspace, agent_id, config)
    bootstrap_minimal_agent(store, agent_id)

    print_banner(AGENT_MODEL, workspace, agent_id)

    llm = build_llm()
    ctx = sm.start_session(agent_id)
    session_id = ctx.session_id
    deps = replace(deps, session_id=session_id)
    print(f"  Session:     {session_id}\n")

    agent = Agent(
        llm,
        deps_type=type(deps),
        instructions=lambda c: build_instructions(c.deps),
        tools=TOOLS,
    )

    history: list[ModelMessage] = []
    close_reason: str | None = None

    try:
        while True:
            try:
                user_text = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                close_reason = "interrupted"
                break

            if not user_text:
                continue
            low = user_text.lower()
            if low in {"/quit", "/exit"}:
                close_reason = "completed"
                break
            if low == "/history":
                for m in history:
                    parts = getattr(m, "parts", [])
                    for p in parts:
                        text = getattr(p, "content", None) or getattr(p, "text", None)
                        if text:
                            kind = type(p).__name__
                            print(f"  [{kind}] {str(text)[:200]}")
                continue
            if low == "/tools":
                for t in TOOLS:
                    doc = (t.__doc__ or "").strip().splitlines()[0] if t.__doc__ else "(no doc)"
                    print(f"  {t.__name__}: {doc}")
                continue
            if low == "/workspace":
                print(f"  {workspace}")
                continue

            # Register entities from user message so ambient RAG has anchors.
            _register_entities(user_text, deps)

            try:
                result = await agent.run(
                    user_text,
                    deps=deps,
                    message_history=history if history else None,
                )
            except UnicodeEncodeError:
                # Surrogate chars from a previous LLM turn corrupted history.
                # Clear it and retry — the user loses context but the REPL stays alive.
                print("  ⚠ Surrogate chars in history — clearing context and retrying")
                history.clear()
                try:
                    result = await agent.run(user_text, deps=deps)
                except Exception as e2:  # noqa: BLE001
                    print(f"  ✗ agent.run raised {type(e2).__name__}: {e2}")
                    continue
            except Exception as e:  # noqa: BLE001 — REPL: show error, keep alive
                print(f"  ✗ agent.run raised {type(e).__name__}: {e}")
                continue

            # Sanitize surrogate chars before storing in history so the next
            # agent.run() doesn't crash during JSON serialization.
            new_messages = _sanitize_history(list(result.all_messages()))
            history.extend(new_messages)

            # Echo tool calls
            for msg in result.new_messages():
                for part in getattr(msg, "parts", []):
                    if hasattr(part, "tool_name"):
                        args = str(getattr(part, "args", ""))[:80]
                        print(f"  🔧 {part.tool_name}({args})")

            output = str(result.output or "").strip()
            # Strip <think> blocks for display (gemma4 sometimes emits them).
            import re

            clean = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL).strip()
            # Sanitize surrogate chars that gemma4 occasionally emits; they
            # crash utf-8 terminals with UnicodeEncodeError otherwise.
            clean = clean.encode("utf-8", "replace").decode("utf-8")
            print(f"agent> {clean}\n")
    finally:
        try:
            sm.finish_session(
                session_id,
                overall_emotional_tone=0.0,
                key_insight="REPL session",
                alignment_check=True,
                close_reason=close_reason,
            )
            print(f"  ✓ finish_session OK (close_reason={close_reason})")
        except ValueError as exc:
            if "Cannot finish session without key moments" in str(exc):
                from atman.adapters.agent.runner import _force_finish

                _force_finish(sm, session_id, close_reason or "completed")
                print("  [!] force_finish (no key moments recorded)")
            else:
                raise
        # Drain post-write maintenance queue (mREBEL relations, lingvo markers).
        if deps.maintenance_worker is not None:
            try:
                done = deps.maintenance_worker.run_once(batch_size=50)
                if done:
                    print(f"  [maintenance] drained {done} job(s)")
            except Exception as e:  # noqa: BLE001
                print(f"  (maintenance drain errored: {e})")

        # Surface any inline validation findings the guardian captured.
        if deps.memory_guardian is not None:
            try:
                findings = deps.memory_guardian.get_unresolved(agent_id)
                if findings:
                    print(f"\n  validation_findings ({len(findings)}):")
                    for f in findings:
                        print(f"    [{f.severity}] {f.finding_type}: {f.description[:120]}")
            except Exception as e:  # noqa: BLE001
                print(f"  (guardian get_unresolved errored: {e})")
        print(f"\nWorkspace preserved: {workspace}")
    return 0


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    sys.exit(main())
