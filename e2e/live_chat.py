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
import logging
import os
import sys
import tempfile
import warnings
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

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


_rc = Console(highlight=False, markup=True)  # Rich console for Atman internals

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
    """Extract entities from user message and register them in the shared registry."""
    if deps.ambient_memory is None or deps.entity_registry is None:
        return
    try:
        analysis = deps.ambient_memory._analyzer.analyze_user_message(text)
        entities = analysis.entities or []
        if entities:
            parts = "  ".join(
                f"[bold]{e.text}[/bold][dim]·{e.entity_type.value}[/dim]"
                for e in entities
            )
            con.add("🔍", "entities", parts)
        else:
            con.add("🔍", "entities", "[dim]none detected[/dim]")
        for entity in entities:
            deps.entity_registry.resolve_or_create(
                deps.agent_id,
                entity.text,
                entity.entity_type,
            )
    except Exception:  # noqa: BLE001
        con.add("🔍", "entities", "[dim red]analysis error[/dim red]")


def _ambient_snapshot(text: str, deps, con: AtmanConsole) -> None:
    """Call compose_injection for diagnostic display only — NOT injected into agent."""
    if deps.ambient_memory is None:
        return
    try:
        result = deps.ambient_memory.compose_injection(text, agent_id=deps.agent_id)
        items = result.items
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
    _rc.print(f"  [dim]session  [/dim][cyan]{session_id}[/cyan]\n")

    agent = Agent(
        llm,
        deps_type=type(deps),
        instructions=lambda c: build_instructions(c.deps),
        tools=TOOLS,
    )

    con = AtmanConsole()
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

            # ── Atman pre-turn: entity registration + ambient snapshot ─────────
            _register_entities(user_text, deps, con)
            _ambient_snapshot(user_text, deps, con)
            con.flush("atman ▶ pre")

            # ── Agent run ──────────────────────────────────────────────────────
            try:
                result = await agent.run(
                    user_text,
                    deps=deps,
                    message_history=history if history else None,
                )
            except UnicodeEncodeError:
                con.warn("Surrogate chars in history — clearing context and retrying")
                history.clear()
                try:
                    result = await agent.run(user_text, deps=deps)
                except Exception as e2:  # noqa: BLE001
                    con.err(f"agent.run {type(e2).__name__}: {e2}")
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
                        # Pretty-print first 2 key=value pairs
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
            print(f"agent> {clean}\n")

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

        # Drain maintenance queue
        if deps.maintenance_worker is not None:
            try:
                done = deps.maintenance_worker.run_once(batch_size=50)
                if done:
                    con.add("📋", "maintenance", f"[dim]{done} job(s) drained[/dim]")
            except Exception as e:  # noqa: BLE001
                con.add("📋", "maintenance", f"[dim red]{e}[/dim red]")

        # Validation findings
        if deps.memory_guardian is not None:
            try:
                findings = deps.memory_guardian.get_unresolved(agent_id)
                for f in findings:
                    con.add("⚠", f"finding [{f.severity}]",
                            f"[dim]{f.finding_type}:[/dim] {f.description[:100]}")
            except Exception:  # noqa: BLE001
                pass

        con.flush("atman session end")
        _rc.print(f"\n  [dim]workspace: {workspace}[/dim]")
    return 0


def main() -> int:
    return asyncio.run(amain())


if __name__ == "__main__":
    sys.exit(main())
