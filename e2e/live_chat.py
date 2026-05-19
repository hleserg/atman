#!/usr/bin/env python3
"""Interactive REPL: gemma4 user-agent <-> live Atman session.

Один процесс держит:
  * pydantic-ai Agent на gemma4 (через llama-server :8081)
  * SessionManager + полный стек build_deps (HLE-32 inline-guardian живой)
  * Пять тулзов агента: record_key_moment, restart_session,
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
import logging
import os
import sys
import warnings
from dataclasses import replace
from pathlib import Path
from uuid import UUID, uuid4

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
# Suppress noisy HF / transformers download warnings that clutter Rich panels.
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
warnings.filterwarnings("ignore", category=FutureWarning, module="transformers")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("FlagEmbedding").setLevel(logging.ERROR)
logging.getLogger("gliner").setLevel(logging.ERROR)
# Suppress XLMRoberta LOAD REPORT printed by gliner's model loader.
logging.getLogger("spacy").setLevel(logging.ERROR)
for _noisy in ("filelock", "urllib3", "requests", "tqdm"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from atman.adapters.agent.config import AgentConfig, ModelConfig
from atman.adapters.agent.factory import build_deps
from atman.adapters.agent.preflight import PreflightError, run_cli_preflight
from atman.adapters.agent.instructions import build_instructions
from atman.adapters.agent.tools import (
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

# Persistent workspace — survives across sessions. Override with ATMAN_AGENT_WORKSPACE.
AGENT_WORKSPACE = Path(
    os.getenv("ATMAN_AGENT_WORKSPACE", Path.home() / ".atman" / "dev-agent")
)

TOOLS = (
    record_key_moment,
    restart_session,
    wait_session,
    resolve_pending_review,
    request_reflection,
)


_rc = Console(highlight=False, markup=True)  # Rich console for Atman internals

# Fixed-path session log — Claude (or any tail -f consumer) can watch this file
# to see the full conversation + all Atman internal events in real time.
_SESSION_LOG = Path("/tmp/atman-live-session.jsonl")

import json as _json
from datetime import UTC, datetime as _dt


def _log(event_type: str, **kwargs) -> None:
    """Append one JSONL line to the live session log."""
    try:
        entry = {"ts": _dt.now(UTC).isoformat(), "type": event_type, **kwargs}
        with _SESSION_LOG.open("a") as fh:
            fh.write(_json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _S(s: str) -> str:
    """Replace lone surrogates so the string is safe for UTF-8 encoding."""
    return s.encode("utf-8", "replace").decode("utf-8")


# ── Session debug log display (ATMAN_SESSION_LOG=1) ───────────────────────────
# When ATMAN_SESSION_LOG is set, every slog() event is injected into the
# current AtmanConsole so it appears in the info panels alongside other events.
# Set _slog_con[0] = con at the start of each turn to update the target.
# Remove: delete this block + all _slog_con references + the session_log import.

_slog_con: list["AtmanConsole"] = []  # mutable ref to current turn's console


def _fmt_slog_event(event: str, d: dict) -> tuple[str, str, str] | None:
    """Map a slog event to (icon, label, value) for AtmanConsole.add(), or None to skip."""
    def _s(key: str, n: int = 80) -> str:
        return str(d.get(key, ""))[:n]

    if event == "session_started":
        return ("🚀", "session", f"[cyan]{_s('session_id', 8)}[/cyan] agent={_s('agent_id', 8)}")
    if event == "session_finished":
        return ("🏁", "session done", f"[dim]{_s('close_reason')}[/dim]  moments={_s('key_moments')}")
    if event == "key_moment_appended":
        return ("💎", "key_moment", f"[dim]{_s('what_happened', 70)}[/dim]")
    if event == "job_start":
        return ("⚙", "job start", f"[cyan dim]{_s('job_name')}[/cyan dim]  {_s('agent_id', 8)}")
    if event == "job_done":
        result = d.get("result") or {}
        summary = "  ".join(f"{k}={v}" for k, v in list(result.items())[:3]) if result else ""
        return ("✓", "job done",
                f"[green dim]{_s('job_name')}[/green dim]  {_s('elapsed_ms')}ms"
                + (f"  [dim]{summary[:60]}[/dim]" if summary else ""))
    if event == "job_failed":
        return ("✗", "job FAILED",
                f"[red]{_s('job_name')}[/red]  [dim red]{_s('error', 80)}[/dim red]")
    if event == "entity_resolved":
        m = _s("method")
        color = "green" if m == "L3_new" else "cyan"
        return ("🏷", "entity",
                f'[dim]"{_s("text", 30)}"[/dim] → [{color}]{m}[/{color}]'
                f'  [dim]id={_s("entity_id", 8)}[/dim]')
    if event == "fact_added":
        return ("📝", "fact added", f"[dim]{_s('content', 70)}[/dim]")
    if event == "fact_entity_link_scheduled":
        return ("⏱", "fact_link sched", f"[dim]{_s('fact_id', 8)}[/dim]")
    if event == "fact_entity_links_saved":
        return ("🔗", "fact_entity_links", f"[green]{_s('count')} links[/green]  {_s('entities', 60)}")
    if event == "km_entity_links_saved":
        return ("🔗", "km_entity_links", f"[green]{_s('count')} links[/green]  {_s('entities', 60)}")
    if event == "ambient_injection":
        return ("🔍", "ambient",
                f'[dim]"{_s("query", 40)}"[/dim] → [cyan]{_s("items_total")} items[/cyan]'
                f'  {_s("tokens_used")} tok  {_s("by_kind", 50)}')
    if event == "moment_accessed":
        return ("👁", "accessed", f"[dim]{_s('moment_id', 8)}[/dim]")
    if event == "decay_pass":
        return ("📉", "decay", f"[cyan]{_s('updated')} moments[/cyan]  cutoff={_s('cutoff', 20)}")
    return None  # unknown events are silently skipped


def _slog_to_con(event: str, data: dict) -> None:
    if not _slog_con:
        return
    fmt = _fmt_slog_event(event, data)
    if fmt:
        _slog_con[0].add(*fmt)


from atman.core.session_log import set_display_hook as _set_slog_hook
_set_slog_hook(_slog_to_con)


def _get_or_create_agent_id() -> UUID:
    """Load persisted agent_id or mint and save a new one."""
    AGENT_WORKSPACE.mkdir(parents=True, exist_ok=True)
    id_file = AGENT_WORKSPACE / "agent_id.txt"
    if id_file.exists():
        try:
            return UUID(id_file.read_text().strip())
        except Exception:
            pass
    new_id = uuid4()
    id_file.write_text(str(new_id))
    return new_id


def _surface_passive_context(user_text: str, deps, con: AtmanConsole) -> object:
    """Call PassiveMemoryInjector and return updated deps with injected_context set."""
    if deps.passive_memory_injector is None:
        return deps
    try:
        from atman.core.services.passive_memory_injector import build_rag_context
        items = deps.passive_memory_injector.surface_for_context(user_text)
        if not items:
            return deps
        rag = build_rag_context(items, budget=1500)
        if not rag.items:
            return deps
        lines = []
        for item in rag.items:
            payload = item.payload
            text = (
                getattr(payload, "content", None)
                or getattr(payload, "what_happened", None)
                or str(payload)[:120]
            )
            lines.append(f"- [{item.kind}] {_S(str(text))[:150]}")
        ctx_str = "## Из памяти (релевантное)\n" + "\n".join(lines)
        con.add("💾", "passive RAG", f"[dim]{len(rag.items)} items  {rag.tokens_used}tok[/dim]")
        _log("passive_rag", n_items=len(rag.items), tokens_used=rag.tokens_used)
        return replace(deps, injected_context=ctx_str)
    except Exception as e:  # noqa: BLE001
        con.add("💾", "passive RAG", f"[dim red]{e}[/dim red]")
        return deps


async def _analyze_agent_response(
    text: str,
    deps,
    sm,
    session_id,
    con: AtmanConsole,
) -> None:
    """Post-turn pipeline: analyze agent response (point A), register entities, auto-record moments."""
    if deps.ambient_memory is None:
        return
    try:
        analysis = deps.ambient_memory._analyzer.analyze_agent_message(text)
    except Exception as e:  # noqa: BLE001
        _log("agent_analysis_error", error=str(e))
        return

    # 1. Register entities from agent response (background — LLM call already done)
    async def _bg_register_agent_entities() -> None:
        for ent in analysis.message_entities:
            if len(ent.text) < 2:
                continue
            try:
                await asyncio.to_thread(
                    deps.entity_registry.resolve_or_create,
                    deps.agent_id, _S(ent.text), ent.entity_type,
                )
            except Exception:  # noqa: BLE001
                pass

    asyncio.ensure_future(_bg_register_agent_entities())

    # 2. Log + display point A classification results
    _log(
        "agent_analysis",
        boundary_markers=analysis.boundary_markers,
        divergence=analysis.divergence_signals,
        entities=[_S(e.text) for e in analysis.message_entities],
        stance=analysis.stance,
        cognitive_mode=analysis.cognitive_mode,
        primary_emotion=analysis.primary_emotion,
        cognitive_load_label=analysis.cognitive_load_label,
        spans=[{"text": _S(s.text), "label": s.label} for s in analysis.message_spans[:5]],
    )
    a_cls = " ".join(filter(None, [
        f"[cyan]{analysis.stance}[/cyan]" if analysis.stance else "",
        f"[dim]{analysis.primary_emotion}[/dim]" if analysis.primary_emotion else "",
        f"[dim]{analysis.cognitive_mode}[/dim]" if analysis.cognitive_mode else "",
    ]))
    con.add(
        "🧠", "agent analysis",
        f"boundary={'[green]yes[/green]' if analysis.boundary_markers else '[dim]no[/dim]'}"
        f"  div={len(analysis.divergence_signals)}"
        f"  ent={len(analysis.message_entities)}"
        + (f"  {a_cls}" if a_cls else ""),
    )
    if analysis.message_spans:
        spans_str = "  ".join(
            f"[dim]{_S(s.text)[:20]}[/dim]·[yellow]{s.label}[/yellow]"
            for s in analysis.message_spans[:4]
        )
        con.add("📎", "point-A NER", spans_str)

    # 3. Auto-record key moment on boundary event, with point-A structured_markers
    if analysis.boundary_markers and session_id is not None:
        try:
            from atman.core.models.session import KeyMomentInput
            markers_str = ", ".join(analysis.boundary_markers[:3])
            kmi = KeyMomentInput(
                what_happened=_S(text[:300]),
                why_it_matters=f"Boundary event detected: {markers_str}",
                emotional_valence=0.0,
                emotional_intensity=0.0,
                incomplete_coloring=True,
            )
            moment = kmi.to_key_moment()

            # Enrich with point-A structured_markers (namespace "a")
            a_markers: dict = {
                "a": {
                    "stance": analysis.stance,
                    "cognitive_mode": analysis.cognitive_mode,
                    "self_orientation": analysis.self_orientation,
                    "primary_emotion": analysis.primary_emotion,
                    "cognitive_load_label": analysis.cognitive_load_label,
                    "boundary_markers": analysis.boundary_markers,
                    "divergence_signals": analysis.divergence_signals,
                    "spans": [{"text": _S(s.text), "label": s.label} for s in analysis.message_spans],
                }
            }
            moment.structured_markers = a_markers
            moment.structured_markers_version = "2.0"

            sm.append_key_moment(session_id, moment)
            con.add("📌", "auto key moment", f"[green]written+A[/green]  [{markers_str[:60]}]")
            _log("auto_key_moment", markers=analysis.boundary_markers,
                 a_markers=a_markers["a"], text_preview=_S(text[:100]))
        except Exception as e:  # noqa: BLE001
            con.add("📌", "auto key moment", f"[dim red]{e}[/dim red]")

    # 4. Write identity facts (name/gender from agent self-description)
    if analysis.boundary_markers and deps.passive_memory_injector is not None:
        _write_identity_facts(text, analysis, deps, con)


# ── Atman dev console ─────────────────────────────────────────────────────────


class AtmanConsole:
    """Collects per-turn Atman internals and displays them with Rich formatting.

    Call ``add()`` to queue events, ``flush()`` to render and clear.
    Output goes to stdout via the shared Rich console — visually distinct from
    the plain-text conversation via color and border, but never injected into
    the agent context.
    """

    _SEVERITY_COLOR = {"LOW": "dim yellow", "MEDIUM": "yellow", "HIGH": "red bold"}

    def __init__(self) -> None:
        self._events: list[tuple[str, str, str]] = []  # (icon, label, value)

    def add(self, icon: str, label: str, value: str = "") -> None:
        self._events.append((icon, label, value))

    def flush(self, title: str = "atman") -> None:
        if not self._events:
            return
        # Build markup string so Rich renders [dim], [cyan], etc. in values.
        lines = "\n".join(
            f"  {icon} [cyan dim]{label:<18}[/cyan dim]{value}"
            for icon, label, value in self._events
        )
        _rc.print(
            Panel(lines, title=f"[dim cyan]{title}[/dim cyan]",
                  border_style="steel_blue1 dim", padding=(0, 0)),
        )
        self._events.clear()

    def rule(self, title: str = "") -> None:
        _rc.print(Rule(title, style="steel_blue1 dim"))

    def ok(self, msg: str) -> None:
        _rc.print(f"  [green]✓[/green] [dim]{msg}[/dim]")

    def warn(self, msg: str) -> None:
        _rc.print(f"  [yellow]⚠[/yellow]  {msg}")

    def err(self, msg: str) -> None:
        _rc.print(f"  [red]✗[/red]  {msg}")

    def finding(self, severity: str, ftype: str, desc: str) -> None:
        color = self._SEVERITY_COLOR.get(severity.upper(), "white")
        _rc.print(f"  [dim]finding[/dim]  [{color}]{severity}[/{color}]"
                  f"  [dim]{ftype}:[/dim]  {desc[:120]}")


# ── helpers ───────────────────────────────────────────────────────────────────


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


def _register_entities(text: str, deps, con: AtmanConsole) -> None:
    """Extract entities from user message, display them, and enqueue DB registration."""
    if deps.ambient_memory is None or deps.entity_registry is None:
        return
    try:
        analysis = deps.ambient_memory._analyzer.analyze_user_message(text)
        entities = analysis.entities or []
        if entities:
            parts = "  ".join(
                f"[bold]{_S(e.text)}[/bold][dim]·{e.entity_type.value}[/dim]"
                for e in entities
            )
            con.add("🔍", "entities", parts)
            _log("entities", entities=[{"text": _S(e.text), "type": e.entity_type.value} for e in entities])
        else:
            con.add("🔍", "entities", "[dim]none detected[/dim]")
            _log("entities", entities=[])

        # DB writes are background — GLiNER analysis done, LLM call can start now.
        async def _bg_register() -> None:
            for entity in entities:
                try:
                    await asyncio.to_thread(
                        deps.entity_registry.resolve_or_create,
                        deps.agent_id,
                        _S(entity.text),
                        entity.entity_type,
                    )
                except Exception:  # noqa: BLE001
                    pass

        asyncio.ensure_future(_bg_register())
    except Exception as exc:  # noqa: BLE001
        con.add("🔍", "entities", "[dim red]analysis error[/dim red]")
        _log("entities_error", error=str(exc))


def _ambient_snapshot(text: str, deps, con: AtmanConsole) -> None:
    """Call compose_injection for diagnostic display only — NOT injected into agent."""
    if deps.ambient_memory is None:
        return
    try:
        result = deps.ambient_memory.compose_injection(text, agent_id=deps.agent_id)
        items = result.items
        _log("ambient_rag", n_items=len(items), tokens_used=result.tokens_used,
             items=[{"kind": it.kind, "anchor": it.anchor_text, "score": round(it.score, 3)}
                    for it in items])
        if not items:
            con.add("🧭", "ambient RAG", f"[dim]0 items  tokens={result.tokens_used}[/dim]")
        else:
            summary = "  ".join(
                f"[dim]{it.kind}[/dim] [cyan]{(it.anchor_text or '')[:20]}[/cyan]"
                f"[dim] s={it.score:.2f}[/dim]"
                for it in items[:5]
            )
            tail = f"[dim]  +{len(items)-5} more[/dim]" if len(items) > 5 else ""
            con.add("🧭", "ambient RAG", f"{summary}{tail}  [dim]tokens={result.tokens_used}[/dim]")
    except Exception as e:  # noqa: BLE001
        con.add("🧭", "ambient RAG", f"[dim red]{e}[/dim red]")
        _log("ambient_rag_error", error=str(e))


def _write_identity_facts(text: str, analysis, deps, con: AtmanConsole) -> None:
    """Write facts for agent self-description (name, gender) to FactualMemory."""
    try:
        factual_memory = deps.passive_memory_injector.factual_memory
    except AttributeError:
        return
    if factual_memory is None:
        return

    from atman.core.models.fact import FactRecord

    identity_markers = {
        "я принимаю", "я выбираю", "моё имя", "меня зовут", "я решила", "я решил",
    }
    marker_text = " ".join(analysis.boundary_markers).lower()
    if not any(m in marker_text for m in identity_markers):
        return

    # Extract person entities as potential self-name
    person_entities = [
        _S(e.text) for e in analysis.message_entities
        if e.entity_type.value == "person" and len(e.text) >= 2
    ]

    facts_written = 0
    for name in person_entities[:2]:
        try:
            record = FactRecord(
                agent_id=deps.agent_id,
                content=f"Агент называет себя: {name}",
                source="agent_boundary_event",
                tags=["identity", "agent_name", "self_description"],
            )
            factual_memory.add_fact(record)
            facts_written += 1
            _log("identity_fact", content=record.content)
        except Exception:  # noqa: BLE001
            pass

    # Also write the full statement as a fact
    try:
        record = FactRecord(
            agent_id=deps.agent_id,
            content=_S(f"Агент о себе: {text[:200]}"),
            source="agent_boundary_event",
            tags=["identity", "self_description"],
        )
        factual_memory.add_fact(record)
        facts_written += 1
        _log("identity_fact", content=record.content[:100])
    except Exception:  # noqa: BLE001
        pass

    if facts_written:
        con.add("💡", "identity facts", f"[green]{facts_written} written[/green]")


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
    _rc.rule(f"[bold cyan]Atman LIVE CHAT[/bold cyan]  [dim]{model} @ {AGENT_BASE_URL}[/dim]",
             style="cyan")
    _rc.print(f"  [dim]agent   [/dim][cyan]{agent_id}[/cyan]")
    _rc.print(f"  [dim]workspace[/dim] {workspace}")
    _rc.print(f"  [dim]tools   [/dim][dim]{', '.join(t.__name__ for t in TOOLS)}[/dim]")
    _rc.print("  [dim]/quit  /exit  /history  /tools  /workspace[/dim]")
    _rc.rule(style="cyan dim")


async def amain() -> int:
    workspace = AGENT_WORKSPACE
    workspace.mkdir(parents=True, exist_ok=True)
    agent_id = _get_or_create_agent_id()

    try:
        run_cli_preflight(print_fn=_rc.print)
    except PreflightError as exc:
        _rc.print(f"\n[red bold]Preflight failed — session aborted.[/red bold]\n{exc}")
        return 1

    config = AgentConfig(model=ModelConfig(model=AGENT_MODEL, context_limit=4096))
    deps, sm, store = build_deps(workspace, agent_id, config)

    # Wire PostgresEntityRegistry for cross-session entity persistence
    if os.getenv("DATABASE_URL") and deps.entity_registry is not None:
        try:
            from atman.adapters.memory.postgres_entity_registry import PostgresEntityRegistry
            pg_registry = PostgresEntityRegistry(os.environ["DATABASE_URL"])
            deps = replace(deps, entity_registry=pg_registry)
            _rc.print("  [dim]entity registry → postgres[/dim]")
        except Exception as e:  # noqa: BLE001
            _rc.print(f"  [dim yellow]postgres entity registry unavailable: {e}[/dim yellow]")

    # Bootstrap only on first run (no identity stored yet)
    if not (workspace / "identity.json").exists():
        bootstrap_minimal_agent(store, agent_id)

    # Truncate the live log at session start so previous sessions don't confuse tail -f.
    _SESSION_LOG.write_text("")
    _log("session_start", agent_id=str(agent_id), model=AGENT_MODEL, base_url=AGENT_BASE_URL)

    print_banner(AGENT_MODEL, workspace, agent_id)

    llm = build_llm()
    ctx = sm.start_session(agent_id)
    session_id = ctx.session_id
    deps = replace(deps, session_id=session_id)
    _log("session_id", session_id=str(session_id), workspace=str(workspace))
    _rc.print(f"  [dim]session  [/dim][cyan]{session_id}[/cyan]\n")

    agent = Agent(
        llm,
        deps_type=type(deps),
        instructions=lambda c: _S(build_instructions(c.deps)),
        tools=TOOLS,
    )

    con = AtmanConsole()
    _slog_con.clear()
    _slog_con.append(con)
    history: list[ModelMessage] = []
    close_reason: str | None = None
    # Keep ~4 recent turns to stay under model context limit.
    # Gemma4 via llama-server defaults to n_ctx=8192; system prompt alone is ~1.5k tokens.
    _MAX_HISTORY = 8

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
                    for p in getattr(m, "parts", []):
                        text = getattr(p, "content", None) or getattr(p, "text", None)
                        if text:
                            _rc.print(f"  [dim]{type(p).__name__}[/dim]  {str(text)[:200]}")
                continue
            if low == "/tools":
                for t in TOOLS:
                    doc = (t.__doc__ or "").strip().splitlines()[0] if t.__doc__ else ""
                    _rc.print(f"  [cyan]{t.__name__}[/cyan]  [dim]{doc}[/dim]")
                continue
            if low == "/workspace":
                _rc.print(f"  {workspace}")
                continue

            user_text = _S(user_text)
            _log("user_msg", text=user_text)

            # ── Atman pre-turn: entity registration + ambient snapshot ─────────
            _register_entities(user_text, deps, con)
            _ambient_snapshot(user_text, deps, con)
            deps = _surface_passive_context(user_text, deps, con)
            con.flush("atman ▶ pre")

            # ── Agent run ──────────────────────────────────────────────────────
            trimmed = history[-_MAX_HISTORY:] if len(history) > _MAX_HISTORY else history
            if len(history) > _MAX_HISTORY:
                con.warn(f"History trimmed {len(history)} → {len(trimmed)} messages")
            try:
                result = await agent.run(
                    user_text,
                    deps=deps,
                    message_history=trimmed if trimmed else None,
                )
            except UnicodeEncodeError:
                con.warn("Surrogate chars in history — sanitizing and retrying")
                history = _sanitize_history(history)
                trimmed = history[-_MAX_HISTORY:] if len(history) > _MAX_HISTORY else history
                try:
                    result = await agent.run(
                        user_text,
                        deps=deps,
                        message_history=trimmed if trimmed else None,
                    )
                except Exception as e2:  # noqa: BLE001
                    con.err(f"agent.run {type(e2).__name__}: {e2}")
                    history.clear()
                    continue
            except Exception as e:  # noqa: BLE001
                con.err(f"agent.run {type(e).__name__}: {e}")
                con.flush("atman ✗")
                continue

            new_messages = _sanitize_history(list(result.all_messages()))
            history.extend(new_messages)

            # ── Atman post-turn: tool calls ────────────────────────────────────
            for msg in result.new_messages():
                for part in getattr(msg, "parts", []):
                    if hasattr(part, "tool_name"):
                        raw_args = getattr(part, "args", {})
                        _log("tool_call", tool=part.tool_name,
                             args=raw_args if isinstance(raw_args, dict) else str(raw_args)[:200])
                        if isinstance(raw_args, dict):
                            kv = "  ".join(
                                f"[dim]{k}[/dim]=[yellow]{str(v)[:40]!r}[/yellow]"
                                for k, v in list(raw_args.items())[:2]
                            )
                            extra = f"[dim] +{len(raw_args)-2} more[/dim]" if len(raw_args) > 2 else ""
                        else:
                            kv = f"[yellow]{str(raw_args)[:80]}[/yellow]"
                            extra = ""
                        con.add("🔧", part.tool_name, f"{kv}{extra}")
            con.flush("atman ◀ tools")

            # ── Agent response ─────────────────────────────────────────────────
            import re
            output = str(result.output or "").strip()
            clean = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL).strip()
            clean = clean.encode("utf-8", "replace").decode("utf-8")
            _log("agent_response", text=clean)
            print(f"agent> {clean}\n")

            # ── Atman post-turn: analyze agent response ────────────────────────
            await _analyze_agent_response(clean, deps, sm, session_id, con)
            con.flush("atman ◀ agent")

    finally:
        _rc.rule(style="cyan dim")
        # finish_session
        try:
            sm.finish_session(
                session_id,
                overall_emotional_tone=0.0,
                key_insight="REPL session",
                alignment_check=True,
                close_reason=close_reason,
            )
            con.ok(f"finish_session  close_reason={close_reason}")
        except ValueError as exc:
            if "Cannot finish session without key moments" in str(exc):
                from atman.adapters.agent.runner import _force_finish

                _force_finish(sm, session_id, close_reason or "completed")
                con.warn("force_finish (no key moments recorded)")
            else:
                raise

        # Micro-reflection: update narrative with session key moments.
        # This is the primary cross-session memory mechanism — without it
        # the agent has no recall of names, events, or choices made in
        # earlier sessions.
        try:
            event = deps.micro_reflection.reflect(session_id, agent_id=agent_id)
            _log("micro_reflection", outcome=event.key_insight[:80] if event.key_insight else "")
            con.add("🪞", "micro-reflection", f"[dim]{(event.key_insight or '')[:80]}[/dim]")
        except Exception as e:  # noqa: BLE001
            con.add("🪞", "micro-reflection", f"[dim red]failed: {e}[/dim red]")
            _log("micro_reflection_error", error=str(e))

        # Drain maintenance queue
        if deps.maintenance_worker is not None:
            try:
                done = deps.maintenance_worker.run_once(batch_size=50)
                _log("maintenance", jobs_drained=done)
                if done:
                    con.add("📋", "maintenance", f"[dim]{done} job(s) drained[/dim]")
            except Exception as e:  # noqa: BLE001
                con.add("📋", "maintenance", f"[dim red]{e}[/dim red]")
                _log("maintenance_error", error=str(e))

        # Validation findings
        if deps.memory_guardian is not None:
            try:
                findings = deps.memory_guardian.get_unresolved(agent_id)
                for f in findings:
                    _log("validation_finding", severity=f.severity,
                         finding_type=f.finding_type, description=f.description)
                    con.add("⚠", f"finding [{f.severity}]",
                            f"[dim]{f.finding_type}:[/dim] {f.description[:100]}")
            except Exception:  # noqa: BLE001
                pass

        _log("session_end", close_reason=close_reason)

        con.flush("atman session end")
        _rc.print(f"\n  [dim]workspace: {workspace}[/dim]")
    return 0


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    sys.exit(main())
