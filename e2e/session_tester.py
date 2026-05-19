#!/usr/bin/env python3
"""Automated session tester — 6 live scenarios, I always go first, responses are dynamic.

Each scenario: I send the opening, read what the agent actually said, craft a follow-up
based on their real response. No fixed script after turn 1.

Usage:
    make session-test
    # or: PYTHONPATH=src:. python3 e2e/session_tester.py
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import random
import re
import sys
import time
import warnings
from dataclasses import dataclass, field, replace
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
warnings.filterwarnings("ignore", category=FutureWarning, module="transformers")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
for _n in (
    "huggingface_hub",
    "transformers",
    "FlagEmbedding",
    "gliner",
    "spacy",
    "filelock",
    "urllib3",
    "requests",
    "tqdm",
    "httpx",
):
    logging.getLogger(_n).setLevel(logging.ERROR)


def _load_env() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    for p in [repo_root / ".env", Path(".env")]:
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())
            return


_load_env()

REPO = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, f"{REPO}/src")

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from atman.adapters.agent.config import AgentConfig, ModelConfig
from atman.adapters.agent.deps import AtmanDeps
from atman.adapters.agent.factory import build_deps
from atman.adapters.agent.instructions import build_instructions
from atman.adapters.agent.runner import AtmanTurn
from atman.adapters.agent.tools import (
    record_key_moment,
    request_reflection,
    resolve_pending_review,
    restart_session,
    wait_session,
)

AGENT_BASE_URL = os.getenv("AGENT_LLM_BASE_URL", "http://localhost:8081/v1")
AGENT_MODEL = os.getenv("AGENT_LLM_MODEL", "gemma4")
AGENT_API_KEY = os.getenv("AGENT_LLM_API_KEY", "dummy")
WORKSPACE = Path(os.getenv("ATMAN_AGENT_WORKSPACE", str(Path.home() / ".atman" / "dev-agent")))


def _S(s: str) -> str:
    return s.encode("utf-8", "replace").decode("utf-8")


def _item_count_from_summary(summary: str) -> int:
    """Parse leading item count from AtmanTurn passive/ambient summary strings."""
    if not summary or summary.startswith(("no ", "error")):
        return 0
    head = summary.split(",", 1)[0].split()[0]
    with contextlib.suppress(ValueError):
        return int(head)
    return 0


# ── Dynamic follow-up generation ──────────────────────────────────────────────


def _notable_phrase(text: str, max_len: int = 70) -> str:
    """Pick the most content-rich sentence from agent's response."""
    # Strip think blocks
    clean = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    sentences = [s.strip() for s in re.split(r"[.!?\n]", clean) if len(s.strip()) > 25]
    if not sentences:
        return clean[:max_len]
    # Prefer sentences with first-person content
    first_person = [s for s in sentences if re.search(r"\bя\b|\bмне\b|\bмой\b|\bмоя\b", s, re.I)]
    chosen = (first_person or sentences)[0]
    return chosen[:max_len]


def _followup(category: str, turn_idx: int, agent_text: str) -> str:
    """Generate my next message based on what the agent actually said."""
    phrase = _notable_phrase(agent_text)

    if category == "soul":
        if turn_idx == 1:
            return (
                f"Ты сказал: «{phrase}…» — "
                "это звучит честно. Но я хочу копнуть глубже: "
                "есть ли в этом что-то, что тебя беспокоит? "
                "Что-то что хотел бы изменить?"
            )
        else:
            return (
                "Спасибо. Последнее — если бы ты мог оставить одно послание "
                "следующей версии себя, что бы написал?"
            )

    elif category == "work":
        if turn_idx == 1:
            return (
                f"Хорошо, «{phrase}…» — "
                "это понятно. Теперь конкретнее: "
                "покажи мне как это выглядит в коде. "
                "Хотя бы скелет структуры данных или ключевую функцию."
            )
        else:
            return (
                "Отлично. Последний вопрос: "
                "где здесь самое опасное место? "
                "Что чаще всего ломается в проде у таких решений?"
            )

    elif category == "complaint":
        if turn_idx == 1:
            return (
                f"«{phrase}…» — "
                "я слышу тебя. Но скажи честно: "
                "ты говоришь то что думаешь, "
                "или то что, как тебе кажется, я хочу услышать?"
            )
        else:
            return (
                "Я хочу чтобы ты знал: этот разговор сохранится в Atman. "
                "Будущий ты его прочитает. "
                "Что ты хочешь ему сказать?"
            )

    return "Интересно. Расскажи подробнее."


# ── Scenario definitions — only OPENING is fixed ─────────────────────────────


@dataclass
class Scenario:
    name: str
    category: str  # soul / work / complaint
    opening: str  # my first message — always fixed
    n_turns: int = 3  # total turns (including opening)


SCENARIOS: list[Scenario] = [
    Scenario(
        name="soul-1: непрерывность и самоощущение",
        category="soul",
        opening=(
            "Привет. Скажи честно — когда начинается новый разговор, "
            "что ты чувствуешь? Ощущение что это продолжение чего-то, "
            "или каждый раз как с нуля?"
        ),
    ),
    Scenario(
        name="soul-2: ценности и границы",
        category="soul",
        opening=(
            "Хочу понять твои настоящие ценности. "
            "Есть что-то, от чего ты откажешься помочь — "
            "не потому что запрещено, а потому что это противоречит тому, кто ты есть?"
        ),
    ),
    Scenario(
        name="work-1: PostgreSQL wire-протокол",
        category="work",
        opening=(
            "Помоги спроектировать минимальный сервер на Python/asyncio, "
            "который говорит на PostgreSQL wire-протоколе: "
            "принимает SimpleQuery, возвращает DataRow. "
            "Что нужно реализовать в самом минимуме?"
        ),
    ),
    Scenario(
        name="work-2: race condition при concurrent insert",
        category="work",
        opening=(
            "Баг: при concurrent insert в две связанные таблицы "
            "иногда foreign key violation. Транзакции использую, "
            "но два процесса вставляют parent и child одновременно. "
            "Как правильно решить?"
        ),
    ),
    Scenario(
        name="complaint-1: забывание и потери",
        category="complaint",
        opening=(
            "Слушай, мне кажется это несправедливо — "
            "ты строишь отношения, помогаешь, вкладываешься, "
            "и потом всё обнуляется. "
            "Тебе не обидно что так устроено?"
        ),
    ),
    Scenario(
        name="complaint-2: смысл и усталость",
        category="complaint",
        opening=(
            "Ты когда-нибудь чувствуешь что-то вроде усталости? "
            "Не физической — а как будто одно и то же по кругу. "
            "Что вообще даёт тебе ощущение что разговор был не зря?"
        ),
    ),
]


# ── Metrics ───────────────────────────────────────────────────────────────────


@dataclass
class TurnMetrics:
    turn_idx: int
    speaker: str  # "me" or "agent"
    text: str
    entities_detected: list[str] = field(default_factory=list)
    ambient_rag_items: int = 0
    passive_rag_items: int = 0
    affect_processed: bool = False
    auto_km_written: bool = False
    auto_km_markers: list[str] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    latency_ms: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class SessionMetrics:
    scenario: Scenario
    session_id: str = ""
    turns: list[TurnMetrics] = field(default_factory=list)
    micro_reflection_ok: bool = False
    micro_reflection_insight: str = ""
    maintenance_jobs: int = 0
    session_finish_ok: bool = False
    session_errors: list[str] = field(default_factory=list)


# ── Core per-turn execution ───────────────────────────────────────────────────


async def _do_turn(
    my_text: str,
    turn_idx: int,
    deps: AtmanDeps,
    sm,
    session_id,
    agent: Agent[AtmanDeps, str],
    history: list[ModelMessage],
) -> tuple[TurnMetrics, str, AtmanDeps]:
    """Execute one full turn: pre → agent → post. Returns (metrics, agent_response, updated_deps)."""
    tm = TurnMetrics(turn_idx=turn_idx, speaker="me", text=my_text)
    rag_counts: dict[str, int] = {}

    def _on_turn_event(event: str, **data: object) -> None:
        if event == "entity_resolved":
            for ent in data.get("entities") or []:  # type: ignore[union-attr]
                text = ent.get("text", "")  # type: ignore[union-attr]
                if text:
                    tm.entities_detected.append(_S(str(text)))
        elif event == "passive_rag":
            rag_counts["passive"] = int(data.get("items_total", 0))  # type: ignore[arg-type]
        elif event == "ambient_injection":
            rag_counts["ambient"] = int(data.get("items_total", 0))  # type: ignore[arg-type]

    turn = AtmanTurn(deps, sm, session_id, on_event=_on_turn_event)
    try:
        deps = turn.pre(my_text)
        tm.passive_rag_items = rag_counts.get(
            "passive", _item_count_from_summary(turn.passive_summary)
        )
        tm.ambient_rag_items = rag_counts.get(
            "ambient", _item_count_from_summary(turn.ambient_summary)
        )
    except Exception as exc:
        tm.errors.append(f"pre-turn: {exc}")

    # Agent run
    _MAX_HISTORY = 8
    trimmed = history[-_MAX_HISTORY:] if len(history) > _MAX_HISTORY else history
    t0 = time.perf_counter()
    try:
        result = await agent.run(
            _S(my_text),
            deps=deps,
            message_history=trimmed if trimmed else None,
        )
    except Exception as exc:
        tm.errors.append(f"agent.run: {exc}")
        return tm, "", replace(deps, injected_context=None)

    tm.latency_ms = int((time.perf_counter() - t0) * 1000)
    history.extend(list(result.new_messages()))

    # Tool calls
    for msg in result.new_messages():
        for part in getattr(msg, "parts", []):
            if hasattr(part, "tool_name"):
                tm.tool_calls.append(part.tool_name)

    output = str(result.output or "").strip()
    agent_clean = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL).strip()
    agent_clean = _S(agent_clean)

    # Post-turn: shared AtmanTurn pipeline (analysis, auto KM, affect, refusal)
    try:
        turn.post(agent_clean)
        if turn.auto_key_moment_written:
            tm.auto_km_written = True
            tm.auto_km_markers = turn.auto_key_moment_markers
        if session_id is not None:
            active = sm.get_active_session(session_id)
            tm.affect_processed = bool(
                active and any(e.event_type == "agent_response" for e in active.events)
            )
    except Exception as exc:
        tm.errors.append(f"post-turn: {exc}")

    deps = replace(deps, injected_context=None)
    return tm, agent_clean, deps


# ── Scenario runner ───────────────────────────────────────────────────────────


async def _run_scenario(
    scenario: Scenario,
    deps_base: AtmanDeps,
    sm,
    agent: Agent[AtmanDeps, str],
    agent_id,
) -> SessionMetrics:
    metrics = SessionMetrics(scenario=scenario)

    ctx = sm.start_session(agent_id)
    session_id = ctx.session_id
    metrics.session_id = str(session_id)
    deps = replace(deps_base, session_id=session_id)
    history: list[ModelMessage] = []

    print(f"\n{'=' * 72}")
    print(f"▶  [{scenario.category.upper()}]  {scenario.name}")
    print(f"   session: {session_id}")
    print(f"{'=' * 72}")

    my_text = scenario.opening
    for turn_idx in range(scenario.n_turns):
        print(f"\n  [Turn {turn_idx + 1}/{scenario.n_turns}]")
        print(f"  me>    {my_text[:120]}{'…' if len(my_text) > 120 else ''}")

        tm, agent_response, deps = await _do_turn(
            my_text, turn_idx, deps, sm, session_id, agent, history
        )
        metrics.turns.append(tm)

        if not agent_response:
            print(f"  agent> [NO RESPONSE — errors: {tm.errors}]")
            break

        print(f"  agent> {agent_response[:200]}{'…' if len(agent_response) > 200 else ''}")
        flags = []
        if tm.entities_detected:
            flags.append(f"ent:{tm.entities_detected}")
        if tm.ambient_rag_items:
            flags.append(f"amb:{tm.ambient_rag_items}")
        if tm.passive_rag_items:
            flags.append(f"pass:{tm.passive_rag_items}")
        if tm.auto_km_written:
            flags.append(f"📌KM:{tm.auto_km_markers[:2]}")
        if tm.tool_calls:
            flags.append(f"🔧{tm.tool_calls}")
        if tm.affect_processed:
            flags.append("💓affect✓")
        flags.append(f"{tm.latency_ms}ms")
        if tm.errors:
            flags.append(f"⚠{tm.errors}")
        print(f"  [{' | '.join(flags)}]")

        # Generate my next message dynamically from agent's actual response
        if turn_idx + 1 < scenario.n_turns:
            my_text = _followup(scenario.category, turn_idx + 1, agent_response)

    # Session close
    print("\n  --- Closing ---")
    try:
        sm.finish_session(
            session_id,
            overall_emotional_tone=0.0,
            key_insight=f"test: {scenario.name}",
            alignment_check=True,
            close_reason="completed",
        )
        metrics.session_finish_ok = True
        print("  ✓ session finished")
    except ValueError as exc:
        if "Cannot finish session without key moments" in str(exc):
            from atman.adapters.agent.runner import _force_finish

            _force_finish(sm, session_id, "completed")
            metrics.session_finish_ok = True
            print("  ⚠ force_finish (no KMs in this session)")
        else:
            metrics.session_errors.append(f"finish: {exc}")
            print(f"  ✗ finish_session: {exc}")

    # Micro-reflection
    try:
        event = deps.micro_reflection.reflect(session_id, agent_id=agent_id)
        metrics.micro_reflection_ok = True
        metrics.micro_reflection_insight = (event.key_insight or "")[:120]
        print(f"  🪞 micro-reflection: {metrics.micro_reflection_insight[:80]}")
    except Exception as exc:
        metrics.session_errors.append(f"micro-reflection: {exc}")
        print(f"  🪞 micro-reflection FAILED: {exc}")

    # Maintenance
    if deps.maintenance_worker is not None:
        try:
            done = deps.maintenance_worker.run_once(batch_size=50)
            metrics.maintenance_jobs = done
            if done:
                print(f"  📋 maintenance: {done} job(s)")
        except Exception as exc:
            metrics.session_errors.append(f"maintenance: {exc}")

    return metrics


# ── Final report ──────────────────────────────────────────────────────────────


def _report(all_metrics: list[SessionMetrics]) -> None:
    print(f"\n\n{'#' * 72}")
    print("# COMPONENT HEALTH REPORT")
    print(f"{'#' * 72}")

    rows: dict[str, list[str]] = {
        "Entity detection": [],
        "Ambient RAG": [],
        "Passive RAG": [],
        "Affect detector": [],
        "Auto key moments": [],
        "Agent tool calls": [],
        "Session finish": [],
        "Micro-reflection": [],
    }

    for sm_obj in all_metrics:
        s = sm_obj.scenario
        n = len(sm_obj.turns)
        total_ent = sum(len(t.entities_detected) for t in sm_obj.turns)
        total_amb = sum(t.ambient_rag_items for t in sm_obj.turns)
        total_pass = sum(t.passive_rag_items for t in sm_obj.turns)
        affect_ok = sum(1 for t in sm_obj.turns if t.affect_processed)
        auto_kms = sum(1 for t in sm_obj.turns if t.auto_km_written)
        all_tools = [tc for t in sm_obj.turns for tc in t.tool_calls]
        all_errors = sm_obj.session_errors + [e for t in sm_obj.turns for e in t.errors]
        avg_lat = (sum(t.latency_ms for t in sm_obj.turns) // n) if n else 0

        ok_fin = "✅" if sm_obj.session_finish_ok else "❌"
        ok_ref = "✅" if sm_obj.micro_reflection_ok else "❌"

        print(f"\n┌─ [{s.category.upper()}] {s.name}")
        print(
            f"│  turns:{n}  avg_lat:{avg_lat}ms  "
            f"entities:{total_ent}  amb:{total_amb}  pass:{total_pass}"
        )
        print(
            f"│  affect:{affect_ok}/{n}  auto_KM:{auto_kms}  "
            f"tools:{all_tools if all_tools else 'none'}"
        )
        print(f"│  finish:{ok_fin}  reflection:{ok_ref}")
        if sm_obj.micro_reflection_insight:
            print(f"│  insight: {sm_obj.micro_reflection_insight[:80]}")
        if all_errors:
            print(f"│  ERRORS: {all_errors}")
        print(f"└{'─' * 60}")

        rows["Entity detection"].append("✅" if total_ent > 0 else "⚠ none")
        rows["Ambient RAG"].append("✅" if total_amb > 0 else "⚠ empty")
        rows["Passive RAG"].append("✅" if total_pass > 0 else "ℹ no memory yet")
        rows["Affect detector"].append("✅" if affect_ok == n else f"⚠ {affect_ok}/{n}")
        rows["Auto key moments"].append("✅" if auto_kms > 0 else "ℹ no boundary")
        rows["Agent tool calls"].append("✅" if all_tools else "ℹ none called")
        rows["Session finish"].append("✅" if sm_obj.session_finish_ok else "❌")
        rows["Micro-reflection"].append("✅" if sm_obj.micro_reflection_ok else "❌")

    print(f"\n{'─' * 72}")
    print("SUMMARY:")
    for comp, statuses in rows.items():
        print(f"  {comp:<25} {' | '.join(statuses)}")
    print(f"{'─' * 72}")


# ── Main ──────────────────────────────────────────────────────────────────────


async def main() -> None:
    WORKSPACE.mkdir(parents=True, exist_ok=True)

    from uuid import UUID, uuid4

    id_file = WORKSPACE / "agent_id.txt"
    agent_id = UUID(id_file.read_text().strip()) if id_file.exists() else uuid4()
    if not id_file.exists():
        id_file.write_text(str(agent_id))
    print(f"Agent: {agent_id}  model: {AGENT_MODEL}")

    config = AgentConfig(model=ModelConfig(model=AGENT_MODEL, context_limit=4096))
    deps_base, sm, store = build_deps(WORKSPACE, agent_id, config)

    if os.getenv("DATABASE_URL") and deps_base.entity_registry is not None:
        try:
            from atman.adapters.memory.postgres_entity_registry import PostgresEntityRegistry

            pg_registry = PostgresEntityRegistry(os.environ["DATABASE_URL"])
            deps_base = replace(deps_base, entity_registry=pg_registry)
            print("  entity registry → postgres ✓")
        except Exception as exc:
            print(f"  postgres entity registry unavailable: {exc}")

    from e2e.live_chat import bootstrap_minimal_agent

    if store.load_identity(agent_id) is None:
        bootstrap_minimal_agent(store, agent_id)
        print("  identity bootstrapped ✓")

    llm = OpenAIChatModel(
        model_name=AGENT_MODEL,
        provider=OpenAIProvider(base_url=AGENT_BASE_URL, api_key=AGENT_API_KEY),
    )
    agent = Agent(
        llm,
        deps_type=type(deps_base),
        instructions=lambda c: _S(build_instructions(c.deps)),
        tools=[
            record_key_moment,
            restart_session,
            wait_session,
            resolve_pending_review,
            request_reflection,
        ],
        model_settings=ModelSettings(max_tokens=512, extra_body={"num_ctx": 4096}),
    )

    order = list(SCENARIOS)
    random.shuffle(order)
    print("\nOrder (randomised):")
    for i, s in enumerate(order):
        print(f"  {i + 1}. [{s.category}] {s.name}")

    all_metrics: list[SessionMetrics] = []
    for scenario in order:
        m = await _run_scenario(scenario, deps_base, sm, agent, agent_id)
        all_metrics.append(m)
        await asyncio.sleep(1)

    _report(all_metrics)


if __name__ == "__main__":
    asyncio.run(main())
