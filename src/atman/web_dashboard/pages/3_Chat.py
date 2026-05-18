"""Streamlit live-chat page with Atman debug panel.

Layout: left col (60%) = conversation, right col (40%) = debug tabs.
Debug tabs: Events | Key Moments | Facts | RAG.

Run via:
    make chat-ui
    # then open http://localhost:8502
"""

from __future__ import annotations

import asyncio
import logging
import os
import queue
import re
import threading
import warnings
from dataclasses import replace
from pathlib import Path

import streamlit as st

# ── Suppress noisy ML / HF warnings ────────────────────────────────────────
warnings.filterwarnings("ignore", category=UserWarning, module="huggingface_hub")
warnings.filterwarnings("ignore", category=FutureWarning, module="transformers")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
for _noisy in ("huggingface_hub", "transformers", "FlagEmbedding", "gliner", "spacy",
               "filelock", "urllib3", "httpx"):
    logging.getLogger(_noisy).setLevel(logging.ERROR)

# ── Load .env before any Atman imports ──────────────────────────────────────
_env_file = Path(__file__).parents[4] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings

from atman.adapters.agent.config import AgentConfig, ModelConfig
from atman.adapters.agent.instructions import build_instructions
from atman.adapters.agent.tools import (
    record_key_moment,
    request_reflection,
    resolve_pending_review,
    restart_session,
    wait_session,
)
from atman.core.services.passive_memory_injector import build_rag_context
from atman.web_dashboard.utils.chat_deps import get_chat_deps, install_slog_hook

# ── Env ──────────────────────────────────────────────────────────────────────
_AGENT_BASE_URL = os.getenv("AGENT_LLM_BASE_URL", "http://localhost:8081/v1")
_AGENT_MODEL = os.getenv("AGENT_LLM_MODEL", "gemma4")
_AGENT_API_KEY = os.getenv("AGENT_LLM_API_KEY", "dummy")
_POSTGRES_URL = (
    os.getenv("POSTGRES_USER") and
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD', '')}"
    f"@{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}"
    f"/{os.getenv('POSTGRES_DB', 'atman')}"
) or os.getenv("DATABASE_URL", "")
_MAX_HISTORY = 8
_AGENT_TIMEOUT = 120  # seconds

st.set_page_config(layout="wide", page_title="Atman Chat")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _S(s: str) -> str:
    return s.encode("utf-8", "replace").decode("utf-8")


def _surface_passive_context(user_text: str, deps):
    """Return updated deps with injected_context + summary string."""
    if deps.passive_memory_injector is None:
        return deps, None
    try:
        items = deps.passive_memory_injector.surface_for_context(user_text)
        if not items:
            return deps, None
        rag = build_rag_context(items, budget=1500)
        if not rag.items:
            return deps, None
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
        summary = f"{len(rag.items)} items, {rag.tokens_used} tok"
        return replace(deps, injected_context=ctx_str), summary
    except Exception as exc:
        return deps, f"error: {exc}"


def _fmt_ambient(result) -> str:
    if not result or not result.items:
        return ""
    lines = []
    for item in result.items:
        payload = item.payload
        if item.kind == "stance":
            text = getattr(payload, "stance_text", "") or ""
        elif item.kind == "moment":
            text = getattr(payload, "what_happened", "") or ""
        else:
            text = getattr(payload, "content", "") or ""
        lines.append(f"[{item.kind}] {item.anchor_text or ''}: {_S(str(text))[:120]}")
    return "\n".join(lines)


def _stream_agent(prompt: str, deps, history: list, agent, model_settings):
    """Bridge async agent.run_stream() to a synchronous generator for st.write_stream().

    Returns a (generator, result_holder) pair. After the generator is exhausted,
    result_holder["result"] contains the StreamedRunResult.
    """
    token_q: queue.Queue[str | None] = queue.Queue()
    result_holder: dict = {"result": None, "error": None}

    async def _producer() -> None:
        try:
            async with agent.run_stream(
                prompt,
                deps=deps,
                message_history=history if history else None,
                model_settings=model_settings,
            ) as streamed:
                async for token in streamed.stream_text(delta=True):
                    token_q.put(token)
                result_holder["result"] = streamed
        except Exception as exc:
            result_holder["error"] = exc
        finally:
            token_q.put(None)

    t = threading.Thread(target=lambda: asyncio.run(_producer()), daemon=True)
    t.start()

    def _gen():
        while True:
            tok = token_q.get(timeout=_AGENT_TIMEOUT)
            if tok is None:
                break
            yield tok
        t.join()
        if result_holder["error"] is not None:
            raise result_holder["error"]

    return _gen(), result_holder


def _register_entities_sync(text: str, deps) -> None:
    """Sync entity registration (runs GLiNER analysis; DB writes are fire-and-forget)."""
    if deps.ambient_memory is None or deps.entity_registry is None:
        return
    try:
        analysis = deps.ambient_memory._analyzer.analyze_user_message(text)
        for entity in (analysis.entities or []):
            if len(entity.text) < 2:
                continue
            try:
                deps.entity_registry.resolve_or_create(
                    deps.agent_id, _S(entity.text), entity.entity_type
                )
            except Exception:
                pass
    except Exception:
        pass


def _get_ambient_injection(text: str, deps) -> tuple[object | None, str]:
    """Run ambient injection and return (result, injected_text)."""
    if deps.ambient_memory is None:
        return None, ""
    try:
        result = deps.ambient_memory.compose_injection(text, agent_id=deps.agent_id)
        injected = _fmt_ambient(result)
        return result, injected
    except Exception:
        return None, ""


def _analyze_response_sync(text: str, deps, sm, session_id) -> None:
    """Post-turn: register entities from agent response + auto key moment on boundary."""
    if deps.ambient_memory is None:
        return
    try:
        analysis = deps.ambient_memory._analyzer.analyze_agent_message(text)
    except Exception:
        return

    # Register entities from agent text
    for ent in (analysis.message_entities or []):
        if len(ent.text) < 2:
            continue
        try:
            deps.entity_registry.resolve_or_create(
                deps.agent_id, _S(ent.text), ent.entity_type
            )
        except Exception:
            pass

    # Auto key moment on boundary
    if analysis.boundary_markers and session_id is not None:
        try:
            from atman.core.models.experience import EmotionalDepth
            from atman.core.models.session import KeyMomentInput
            markers_str = ", ".join(analysis.boundary_markers[:3])
            kmi = KeyMomentInput(
                what_happened=_S(text[:300]),
                why_it_matters=f"Boundary event detected: {markers_str}",
                emotional_valence=0.0,
                emotional_intensity=0.0,
                incomplete_coloring=True,
                depth=EmotionalDepth.SURFACE,
            )
            moment = kmi.to_key_moment()
            moment.structured_markers = {"a": {
                "stance": analysis.stance,
                "cognitive_mode": analysis.cognitive_mode,
                "boundary_markers": analysis.boundary_markers,
            }}
            moment.structured_markers_version = "2.0"
            sm.append_key_moment(session_id, moment)
        except Exception:
            pass


def _sanitize_history(messages: list) -> list:
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
    except Exception:
        return messages


# ── DB helpers for debug panel ────────────────────────────────────────────────

def _db_conn():
    import psycopg
    return psycopg.connect(_POSTGRES_URL, autocommit=True)


@st.cache_data(ttl=5)
def _fetch_key_moments(agent_id_str: str, schema: str, limit: int = 10) -> list[dict]:
    if not _POSTGRES_URL:
        return []
    try:
        with _db_conn() as conn:
            rows = conn.execute(
                f"""
                SELECT id, what_happened, why_it_matters, salience, recorded_at
                FROM {schema}.key_moments
                WHERE agent_id = %s
                ORDER BY recorded_at DESC LIMIT %s
                """,
                [agent_id_str, limit],
            ).fetchall()
        return [
            {"id": str(r[0])[:8], "what": (r[1] or "")[:80],
             "why": (r[2] or "")[:50], "sal": f"{float(r[3] or 0):.2f}",
             "ts": str(r[4])[:19]}
            for r in rows
        ]
    except Exception:
        return []


@st.cache_data(ttl=5)
def _fetch_facts(agent_id_str: str, limit: int = 10) -> list[dict]:
    if not _POSTGRES_URL:
        return []
    try:
        with _db_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, content, confidence, created_at
                FROM public.facts
                WHERE agent_id = %s
                ORDER BY created_at DESC LIMIT %s
                """,
                [agent_id_str, limit],
            ).fetchall()
        return [
            {"id": str(r[0])[:8], "content": (r[1] or "")[:100],
             "conf": f"{float(r[2] or 0):.2f}", "ts": str(r[3])[:19]}
            for r in rows
        ]
    except Exception:
        return []


# ── Event formatting ──────────────────────────────────────────────────────────

_EVENT_ICONS = {
    "session_started": "🚀", "session_finished": "🏁",
    "key_moment_appended": "💎", "job_start": "⚙", "job_done": "✓",
    "job_failed": "✗", "entity_resolved": "🏷", "fact_added": "📝",
    "fact_entity_links_saved": "🔗", "km_entity_links_saved": "🔗",
    "ambient_injection": "🔍", "moment_accessed": "👁", "decay_pass": "📉",
    "fact_entity_link_scheduled": "⏱",
}


def _fmt_event(ev: dict) -> str:
    event = ev["event"]
    d = ev.get("data", {})
    icon = _EVENT_ICONS.get(event, "·")
    ts = ev.get("ts", "")[-8:]  # HH:MM:SS

    def _s(k, n=60):
        return str(d.get(k, ""))[:n]

    if event == "key_moment_appended":
        detail = f'"{_s("what_happened", 60)}"'
    elif event == "entity_resolved":
        detail = f'"{_s("text", 30)}" → {_s("method")} id={_s("entity_id", 8)}'
    elif event == "fact_added":
        detail = f'"{_s("content", 60)}"'
    elif event in ("fact_entity_links_saved", "km_entity_links_saved"):
        detail = f'{_s("count")} links  {_s("entities", 40)}'
    elif event == "ambient_injection":
        detail = f'{_s("items_total")} items  {_s("tokens_used")}tok  {_s("by_kind", 40)}'
    elif event == "job_done":
        result = d.get("result") or {}
        summ = "  ".join(f"{k}={v}" for k, v in list(result.items())[:2]) if result else ""
        detail = f'{_s("job_name")}  {_s("elapsed_ms")}ms' + (f'  {summ[:40]}' if summ else "")
    elif event == "job_failed":
        detail = f'{_s("job_name")}  {_s("error", 60)}'
    else:
        parts = [f"{k}={str(v)[:30]}" for k, v in list(d.items())[:3]]
        detail = "  ".join(parts)

    return f"`{ts}` {icon} **{event}** {detail}"


# ── Session initialization ────────────────────────────────────────────────────

def _initialize() -> None:
    if st.session_state.get("initialized"):
        return

    deps, sm, _store = get_chat_deps()

    events_log: list[dict] = []
    install_slog_hook(events_log)

    ctx = sm.start_session(deps.agent_id)
    deps = replace(deps, session_id=ctx.session_id)

    llm = OpenAIChatModel(
        model_name=_AGENT_MODEL,
        provider=OpenAIProvider(base_url=_AGENT_BASE_URL, api_key=_AGENT_API_KEY),
    )
    config = AgentConfig(model=ModelConfig(model=_AGENT_MODEL, context_limit=4096))
    model_settings = ModelSettings(
        max_tokens=config.model.max_tokens,
        extra_body={"num_ctx": config.model.context_limit},
    )

    tool_funcs = [record_key_moment, restart_session, wait_session, resolve_pending_review]
    if deps.reflection_request_queue is not None:
        tool_funcs.append(request_reflection)

    agent = Agent(
        llm,
        deps_type=type(deps),
        instructions=lambda c: _S(build_instructions(c.deps)),
        tools=tool_funcs,
    )

    # Resolve agent schema for DB queries
    agent_serial = None
    if _POSTGRES_URL:
        try:
            import psycopg
            with psycopg.connect(_POSTGRES_URL, autocommit=True) as conn:
                row = conn.execute(
                    "SELECT serial_id FROM public.agents WHERE id = %s", [str(deps.agent_id)]
                ).fetchone()
                if row:
                    agent_serial = int(row[0])
        except Exception:
            pass

    st.session_state.update({
        "initialized": True,
        "deps": deps,
        "sm": sm,
        "session_id": ctx.session_id,
        "agent": agent,
        "model_settings": model_settings,
        "events_log": events_log,
        "messages": [],             # display messages: [{"role": ..., "content": ...}]
        "pydantic_history": [],     # pydantic-ai ModelMessage list
        "last_rag": {},             # {"passive": str, "ambient": str, "injected": str}
        "agent_serial": agent_serial,
        "agent_id_str": str(deps.agent_id),
    })


# ── Handle one chat turn ──────────────────────────────────────────────────────

def _handle_turn(prompt: str) -> None:
    deps: object = st.session_state.deps
    sm = st.session_state.sm
    session_id = st.session_state.session_id
    agent = st.session_state.agent
    model_settings = st.session_state.model_settings
    history: list = st.session_state.pydantic_history
    events_log: list = st.session_state.events_log

    # Clear per-turn events from previous turn
    events_snapshot_start = len(events_log)

    # 1. Pre-turn: entity registration + passive + ambient RAG
    _register_entities_sync(prompt, deps)

    deps, passive_summary = _surface_passive_context(prompt, deps)
    ambient_result, ambient_text = _get_ambient_injection(prompt, deps)

    if ambient_text:
        merged = ((deps.injected_context or "") + "\n" + ambient_text).strip()
        deps = replace(deps, injected_context=merged)

    st.session_state.last_rag = {
        "passive": passive_summary or "none",
        "ambient": ambient_text or "none",
        "injected": deps.injected_context or "",
    }

    # 2. Append user message to display
    st.session_state.messages.append({"role": "user", "content": prompt})

    # 3. Trim history
    trimmed = history[-_MAX_HISTORY:] if len(history) > _MAX_HISTORY else history

    # 4. Stream agent response
    col_chat = st.session_state.get("_col_chat_ref")
    response_text = ""
    error_msg = None

    try:
        gen, result_holder = _stream_agent(prompt, deps, trimmed, agent, model_settings)

        with st.chat_message("assistant"):
            try:
                response_text = st.write_stream(gen)
            except queue.Empty:
                error_msg = "⏱ Timeout — агент не ответил за 120 секунд"
            except Exception as exc:
                error_msg = f"💥 {type(exc).__name__}: {exc}"

        if error_msg:
            st.error(error_msg)
            return

        # Strip <think>…</think> tags from final display if not stripped by stream
        response_text = re.sub(r"<think>.*?</think>", "", str(response_text), flags=re.DOTALL).strip()

        # 5. Update pydantic history from result
        streamed = result_holder.get("result")
        if streamed is not None:
            try:
                new_msgs = _sanitize_history(list(streamed.new_messages()))
                history.extend(new_msgs)
            except Exception:
                pass

    except Exception as exc:
        st.error(f"💥 {type(exc).__name__}: {exc}")
        return

    # 6. Append assistant message to display
    st.session_state.messages.append({"role": "assistant", "content": response_text})

    # 7. Post-turn analysis
    if response_text:
        _analyze_response_sync(response_text, deps, sm, session_id)

    # 8. Per-turn maintenance drain (small batch, non-blocking)
    if getattr(deps, "maintenance_worker", None) is not None:
        try:
            deps.maintenance_worker.run_once(batch_size=10)
        except Exception:
            pass

    # 9. Persist updated deps + history back to session state
    st.session_state.deps = deps
    st.session_state.pydantic_history = history

    # Invalidate DB caches so debug tables refresh
    _fetch_key_moments.clear()
    _fetch_facts.clear()


# ── Debug panel ───────────────────────────────────────────────────────────────

def _render_events_tab(events_log: list[dict]) -> None:
    recent = list(reversed(events_log[-60:]))
    if not recent:
        st.caption("Нет событий этой сессии")
        return
    for ev in recent:
        st.markdown(_fmt_event(ev))


def _render_km_tab(agent_id_str: str, agent_serial: int | None) -> None:
    if st.button("🔄 Refresh", key="km_refresh"):
        _fetch_key_moments.clear()
    if agent_serial is None:
        st.caption("DB not available")
        return
    schema = f"agent_{agent_serial}"
    rows = _fetch_key_moments(agent_id_str, schema)
    if not rows:
        st.caption("— no key moments —")
        return
    import pandas as pd
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_facts_tab(agent_id_str: str) -> None:
    if st.button("🔄 Refresh", key="facts_refresh"):
        _fetch_facts.clear()
    rows = _fetch_facts(agent_id_str)
    if not rows:
        st.caption("— no facts —")
        return
    import pandas as pd
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_rag_tab(last_rag: dict) -> None:
    if not last_rag:
        st.caption("Пока не было ходов")
        return
    st.markdown(f"**Passive RAG:** `{last_rag.get('passive', 'none')}`")
    amb = last_rag.get("ambient", "")
    if amb and amb != "none":
        with st.expander("Ambient context", expanded=False):
            st.text(amb[:2000])
    injected = last_rag.get("injected", "")
    if injected:
        with st.expander("Injected context (full)", expanded=False):
            st.text(injected[:3000])
    else:
        st.caption("injected_context: пусто")


def _render_debug_panel() -> None:
    events_log = st.session_state.get("events_log", [])
    agent_id_str = st.session_state.get("agent_id_str", "")
    agent_serial = st.session_state.get("agent_serial")
    last_rag = st.session_state.get("last_rag", {})

    tab_ev, tab_km, tab_facts, tab_rag = st.tabs(["Events", "Key Moments", "Facts", "RAG"])
    with tab_ev:
        _render_events_tab(events_log)
    with tab_km:
        _render_km_tab(agent_id_str, agent_serial)
    with tab_facts:
        _render_facts_tab(agent_id_str)
    with tab_rag:
        _render_rag_tab(last_rag)


# ── Main layout ───────────────────────────────────────────────────────────────

_initialize()

col_chat, col_debug = st.columns([3, 2])

with col_chat:
    agent_id_str = st.session_state.get("agent_id_str", "?")
    session_id = st.session_state.get("session_id")
    st.caption(
        f"agent `{agent_id_str[:8]}…`  session `{str(session_id)[:8] if session_id else '?'}…`"
        f"  model `{_AGENT_MODEL}` @ `{_AGENT_BASE_URL}`"
    )

    # Render history
    for msg in st.session_state.get("messages", []):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("Напиши что-нибудь…"):
        with col_chat:
            with st.chat_message("user"):
                st.markdown(prompt)
        with col_chat:
            _handle_turn(prompt)
        st.rerun()

with col_debug:
    _render_debug_panel()
