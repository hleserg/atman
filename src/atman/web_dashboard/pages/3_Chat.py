"""Streamlit live-chat page with Atman debug panel.

Layout: left col (60%) = chat in fixed-height scrollable container + input
        right col (40%) = debug tabs: Events | Key Moments | Facts | RAG

Run:  make chat-ui
Open: http://localhost:8502  (WSL→Windows: http://<windows-lan-ip>:8502)
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
for _n in ("huggingface_hub", "transformers", "FlagEmbedding", "gliner", "spacy",
           "filelock", "urllib3", "httpx"):
    logging.getLogger(_n).setLevel(logging.ERROR)

# ── Find and load .env (walk up from this file's location) ──────────────────
def _load_env() -> None:
    p = Path(__file__).resolve()
    for _ in range(10):
        p = p.parent
        candidate = p / ".env"
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())
            return

_load_env()

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

# ── Config ────────────────────────────────────────────────────────────────────
_AGENT_BASE_URL = os.getenv("AGENT_LLM_BASE_URL", "http://localhost:8081/v1")
_AGENT_MODEL    = os.getenv("AGENT_LLM_MODEL", "gemma4")
_AGENT_API_KEY  = os.getenv("AGENT_LLM_API_KEY", "dummy")
_MAX_HISTORY    = 8
_AGENT_TIMEOUT  = 120  # seconds


def _pg_url() -> str:
    """Build postgres URL from POSTGRES_* vars (superuser — bypasses RLS)."""
    u = os.getenv("POSTGRES_USER", "")
    if not u:
        return os.getenv("DATABASE_URL", "")
    return (
        f"postgresql://{u}:{os.getenv('POSTGRES_PASSWORD', '')}"
        f"@{os.getenv('POSTGRES_HOST', 'localhost')}"
        f":{os.getenv('POSTGRES_PORT', '5432')}"
        f"/{os.getenv('POSTGRES_DB', 'atman')}"
    )


st.set_page_config(layout="wide", page_title="Atman Chat")

# Adaptive chat container: fills available viewport height minus fixed UI chrome.
# st.container(height=) only takes pixels; we override via CSS calc().
# 260px covers: header ~58 + caption ~28 + button ~42 + input ~70 + padding ~62.
st.markdown("""
<style>
[data-testid="stVerticalBlockBorderWrapper"] {
    height: calc(100vh - 260px) !important;
    min-height: 200px !important;
}
[data-testid="stVerticalBlockBorderWrapper"] > div {
    height: 100% !important;
    max-height: none !important;
    overflow-y: auto !important;
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _S(s: str) -> str:
    return s.encode("utf-8", "replace").decode("utf-8")


def _surface_passive_context(user_text: str, deps):
    if deps.passive_memory_injector is None:
        return deps, None
    try:
        items = deps.passive_memory_injector.surface_for_context(user_text)
        if not items:
            return deps, None
        rag = build_rag_context(items, budget=1500)
        if not rag.items:
            return deps, None
        lines = [
            f"- [{it.kind}] {_S(str(getattr(it.payload, 'content', None) or getattr(it.payload, 'what_happened', '') or '')[:150])}"
            for it in rag.items
        ]
        ctx = "## Из памяти (релевантное)\n" + "\n".join(lines)
        return replace(deps, injected_context=ctx), f"{len(rag.items)} items, {rag.tokens_used} tok"
    except Exception as exc:
        return deps, f"error: {exc}"


def _get_ambient_injection(text: str, deps):
    if deps.ambient_memory is None:
        return None, ""
    try:
        result = deps.ambient_memory.compose_injection(text, agent_id=deps.agent_id)
        if not result.items:
            return result, ""
        lines = []
        for it in result.items:
            p = it.payload
            if it.kind == "stance":
                txt = getattr(p, "stance_text", "") or ""
            elif it.kind == "moment":
                txt = getattr(p, "what_happened", "") or ""
            else:
                txt = getattr(p, "content", "") or ""
            lines.append(f"[{it.kind}] {it.anchor_text or ''}: {_S(str(txt))[:100]}")
        return result, "\n".join(lines)
    except Exception:
        return None, ""


def _stream_agent(prompt: str, deps, history: list, agent, model_settings):
    """Wrap async run_stream() in a sync generator via queue+thread."""
    tok_q: queue.Queue[str | None] = queue.Queue()
    holder: dict = {"result": None, "error": None}

    async def _producer() -> None:
        try:
            async with agent.run_stream(
                prompt,
                deps=deps,
                message_history=history if history else None,
                model_settings=model_settings,
            ) as streamed:
                async for token in streamed.stream_text(delta=True):
                    tok_q.put(token)
                holder["result"] = streamed
        except Exception as exc:
            holder["error"] = exc
        finally:
            tok_q.put(None)

    threading.Thread(target=lambda: asyncio.run(_producer()), daemon=True).start()

    def _gen():
        while True:
            tok = tok_q.get(timeout=_AGENT_TIMEOUT)
            if tok is None:
                break
            yield tok
        if holder["error"] is not None:
            raise holder["error"]

    return _gen(), holder


def _register_entities_sync(text: str, deps) -> None:
    if deps.ambient_memory is None or deps.entity_registry is None:
        return
    try:
        analysis = deps.ambient_memory._analyzer.analyze_user_message(text)
        for ent in (analysis.entities or []):
            if len(ent.text) < 2:
                continue
            try:
                deps.entity_registry.resolve_or_create(
                    deps.agent_id, _S(ent.text), ent.entity_type
                )
            except Exception:
                pass
    except Exception:
        pass


def _analyze_response_sync(text: str, deps, sm, session_id) -> None:
    if deps.ambient_memory is None:
        return
    try:
        analysis = deps.ambient_memory._analyzer.analyze_agent_message(text)
    except Exception:
        return
    for ent in (analysis.message_entities or []):
        if len(ent.text) >= 2:
            try:
                deps.entity_registry.resolve_or_create(
                    deps.agent_id, _S(ent.text), ent.entity_type
                )
            except Exception:
                pass
    if analysis.boundary_markers and session_id is not None:
        try:
            from atman.core.models.experience import EmotionalDepth
            from atman.core.models.session import KeyMomentInput
            kmi = KeyMomentInput(
                what_happened=_S(text[:300]),
                why_it_matters=f"Boundary: {', '.join(analysis.boundary_markers[:3])}",
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
        return ModelMessagesTypeAdapter.validate_python(_clean(raw))
    except Exception:
        return messages


# ── Session close ─────────────────────────────────────────────────────────────

def _close_session(status_container) -> None:
    """Run full session-close pipeline, writing status lines into status_container."""
    sm       = st.session_state.sm
    deps     = st.session_state.deps
    session_id = st.session_state.session_id
    agent_id   = deps.agent_id

    lines: list[str] = []

    def _log(msg: str) -> None:
        lines.append(msg)
        status_container.markdown("\n\n".join(lines))

    # 1. finish_session
    try:
        sm.finish_session(
            session_id,
            overall_emotional_tone=0.0,
            key_insight="UI session",
            alignment_check=True,
            close_reason="completed",
        )
        _log("✅ finish_session — ok")
    except ValueError as exc:
        if "Cannot finish session without key moments" in str(exc):
            from atman.adapters.agent.runner import _force_finish
            _force_finish(sm, session_id, "completed")
            _log("⚠️ finish_session — force_finish (no key moments)")
        else:
            _log(f"❌ finish_session — {exc}")
    except Exception as exc:
        _log(f"❌ finish_session — {exc}")

    # 2. Micro-reflection
    try:
        event = deps.micro_reflection.reflect(session_id, agent_id=agent_id)
        insight = (event.key_insight or "")[:100]
        _log(f"🪞 micro-reflection — {insight or 'done'}")
    except Exception as exc:
        _log(f"❌ micro-reflection — {exc}")

    # 3. Maintenance drain
    if getattr(deps, "maintenance_worker", None) is not None:
        try:
            done = deps.maintenance_worker.run_once(batch_size=50)
            _log(f"📋 maintenance — {done} job(s) drained")
        except Exception as exc:
            _log(f"❌ maintenance — {exc}")

    # 4. Validation findings
    if getattr(deps, "memory_guardian", None) is not None:
        try:
            findings = deps.memory_guardian.get_unresolved(agent_id)
            if findings:
                for f in findings[:5]:
                    _log(f"⚠️ finding [{f.severity}] {f.finding_type}: {f.description[:80]}")
            else:
                _log("🔍 validation — no findings")
        except Exception:
            pass

    st.session_state.session_closed = True


# ── DB helpers ────────────────────────────────────────────────────────────────

_KM_PAGE_SIZE = 50   # rows per page in the UI table


@st.cache_data(ttl=5)
def _fetch_key_moments(agent_id_str: str, schema: str, limit: int = 10000) -> list[dict]:
    """Fetch up to `limit` key moments. Returns full UUID in '_id' for DELETE."""
    url = _pg_url()
    if not url:
        return []
    try:
        import psycopg
        with psycopg.connect(url, autocommit=True) as conn:
            rows = conn.execute(
                f"""
                SELECT id, what_happened, why_it_matters, what_changed,
                       depth, salience, importance,
                       emotional_valence, emotional_intensity,
                       values_touched, incomplete_coloring, recorded_by,
                       recorded_at
                FROM {schema}.key_moments
                WHERE agent_id = %s
                ORDER BY recorded_at DESC LIMIT %s
                """,
                [agent_id_str, limit],
            ).fetchall()
        return [
            {
                "_id":      str(r[0]),
                "id":       str(r[0])[:8],
                "what":     r[1] or "",
                "why":      r[2] or "",
                "changed":  r[3] or "",
                "depth":    r[4] or "",
                "sal":      round(float(r[5] or 0), 3),
                "imp":      round(float(r[6] or 0), 3),
                "val":      round(float(r[7] or 0), 2),
                "int":      round(float(r[8] or 0), 2),
                "values":   ", ".join(r[9] or []),
                "coloring": r[10],
                "by":       r[11] or "",
                "ts":       str(r[12])[:19],
            }
            for r in rows
        ]
    except Exception as exc:
        return [{"error": str(exc)}]


def _delete_key_moments(schema: str, ids: list[str]) -> None:
    from uuid import UUID
    import psycopg
    uuid_ids = [UUID(i) for i in ids]
    with psycopg.connect(_pg_url(), autocommit=False) as conn:
        conn.execute(
            f"DELETE FROM {schema}.key_moment_entities WHERE key_moment_id = ANY(%s)",
            [uuid_ids],
        )
        conn.execute(
            f"DELETE FROM {schema}.key_moments WHERE id = ANY(%s)",
            [uuid_ids],
        )
        conn.commit()


_FACTS_PAGE_SIZE = 50


@st.cache_data(ttl=5)
def _fetch_facts(agent_id_str: str, limit: int = 10000) -> list[dict]:
    url = _pg_url()
    if not url:
        return []
    try:
        import psycopg
        with psycopg.connect(url, autocommit=True) as conn:
            rows = conn.execute(
                """
                SELECT id, content, source, tags, status,
                       salience, confirmation_count, last_confirmed_at,
                       invalidation_note, created_at
                FROM public.facts
                WHERE agent_id = %s
                ORDER BY created_at DESC LIMIT %s
                """,
                [agent_id_str, limit],
            ).fetchall()
        return [
            {
                "_id":      str(r[0]),
                "id":       str(r[0])[:8],
                "content":  r[1] or "",
                "source":   r[2] or "",
                "tags":     ", ".join(r[3] or []),
                "status":   r[4] or "",
                "sal":      round(float(r[5] or 0), 3),
                "confirms": r[6] or 0,
                "confirmed": str(r[7])[:19] if r[7] else "",
                "inv_note": r[8] or "",
                "ts":       str(r[9])[:19],
            }
            for r in rows
        ]
    except Exception as exc:
        return [{"error": str(exc)}]


def _delete_facts(schema: str, ids: list[str]) -> None:
    from uuid import UUID
    import psycopg
    uuid_ids = [UUID(i) for i in ids]
    with psycopg.connect(_pg_url(), autocommit=False) as conn:
        conn.execute(
            f"DELETE FROM {schema}.fact_entities WHERE fact_id = ANY(%s)",
            [uuid_ids],
        )
        conn.execute(
            "DELETE FROM public.fact_relations WHERE source_id = ANY(%s) OR target_id = ANY(%s)",
            [uuid_ids, uuid_ids],
        )
        conn.execute(
            "UPDATE public.facts SET superseded_by = NULL WHERE superseded_by = ANY(%s)",
            [uuid_ids],
        )
        conn.execute(
            "DELETE FROM public.facts WHERE id = ANY(%s)",
            [uuid_ids],
        )
        conn.commit()


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
    ts = ev.get("ts", "")[-8:]

    def _s(k, n=60):
        return str(d.get(k, ""))[:n]

    if event == "key_moment_appended":
        detail = f'"{_s("what_happened", 60)}"'
    elif event == "entity_resolved":
        detail = f'"{_s("text", 30)}" → {_s("method")}  id={_s("entity_id", 8)}'
    elif event == "fact_added":
        detail = f'"{_s("content", 60)}"'
    elif event in ("fact_entity_links_saved", "km_entity_links_saved"):
        detail = f'{_s("count")} links  {_s("entities", 40)}'
    elif event == "ambient_injection":
        detail = f'{_s("items_total")} items  {_s("tokens_used")}tok'
    elif event == "job_done":
        result = d.get("result") or {}
        summ = "  ".join(f"{k}={v}" for k, v in list(result.items())[:2]) if result else ""
        detail = f'{_s("job_name")}  {_s("elapsed_ms")}ms' + (f'  {summ[:40]}' if summ else "")
    elif event == "job_failed":
        detail = f'{_s("job_name")}  {_s("error", 60)}'
    else:
        parts = [f"{k}={str(v)[:30]}" for k, v in list(d.items())[:3]]
        detail = "  ".join(parts)

    return f"`{ts}` {icon} **{event}**  {detail}"


# ── Initialization ────────────────────────────────────────────────────────────

def _initialize() -> None:
    if st.session_state.get("initialized"):
        return

    with st.spinner("Инициализация Atman…"):
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

    # Resolve agent DB schema
    agent_serial = None
    url = _pg_url()
    if url:
        try:
            import psycopg
            with psycopg.connect(url, autocommit=True) as conn:
                row = conn.execute(
                    "SELECT serial_id FROM public.agents WHERE id = %s",
                    [str(deps.agent_id)],
                ).fetchone()
                if row:
                    agent_serial = int(row[0])
        except Exception:
            pass

    st.session_state.update({
        "initialized": True,
        "session_closed": False,
        "deps": deps,
        "sm": sm,
        "session_id": ctx.session_id,
        "agent": agent,
        "model_settings": model_settings,
        "events_log": events_log,
        "messages": [],
        "pydantic_history": [],
        "last_rag": {},
        "agent_serial": agent_serial,
        "agent_id_str": str(deps.agent_id),
    })


# ── Chat turn ─────────────────────────────────────────────────────────────────

def _handle_turn(prompt: str, msg_container) -> None:
    deps          = st.session_state.deps
    sm            = st.session_state.sm
    session_id    = st.session_state.session_id
    agent         = st.session_state.agent
    model_settings = st.session_state.model_settings
    history       = st.session_state.pydantic_history

    # Pre-turn
    _register_entities_sync(prompt, deps)
    deps, passive_summary = _surface_passive_context(prompt, deps)
    _, ambient_text = _get_ambient_injection(prompt, deps)
    if ambient_text:
        merged = ((deps.injected_context or "") + "\n" + ambient_text).strip()
        deps = replace(deps, injected_context=merged)

    st.session_state.last_rag = {
        "passive": passive_summary or "none",
        "ambient": ambient_text or "none",
        "injected": deps.injected_context or "",
    }

    # Append + show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with msg_container:
        with st.chat_message("user"):
            st.markdown(prompt)

    # Stream assistant response
    trimmed = history[-_MAX_HISTORY:] if len(history) > _MAX_HISTORY else history
    response_text = ""

    with msg_container:
        with st.chat_message("assistant"):
            placeholder = st.empty()
            try:
                gen, holder = _stream_agent(prompt, deps, trimmed, agent, model_settings)
                response_text = st.write_stream(gen)
                response_text = re.sub(
                    r"<think>.*?</think>", "", str(response_text), flags=re.DOTALL
                ).strip()
            except queue.Empty:
                placeholder.error("⏱ Timeout — агент не ответил за 120 секунд")
                return
            except Exception as exc:
                placeholder.error(f"💥 {type(exc).__name__}: {exc}")
                return

    # Update pydantic history
    streamed = holder.get("result")
    if streamed is not None:
        try:
            new_msgs = _sanitize_history(list(streamed.new_messages()))
            history.extend(new_msgs)
        except Exception:
            pass

    st.session_state.messages.append({"role": "assistant", "content": response_text})

    # Post-turn
    if response_text:
        _analyze_response_sync(response_text, deps, sm, session_id)

    if getattr(deps, "maintenance_worker", None) is not None:
        try:
            deps.maintenance_worker.run_once(batch_size=10)
        except Exception:
            pass

    st.session_state.deps = deps
    st.session_state.pydantic_history = history
    _fetch_key_moments.clear()
    _fetch_facts.clear()


# ── Key Moments table with pagination + delete ────────────────────────────────

def _render_km_table(agent_id_str: str, schema: str) -> None:
    import pandas as pd

    c_refresh, c_info = st.columns([1, 5])
    if c_refresh.button("🔄", key="km_refresh"):
        _fetch_key_moments.clear()
        st.session_state.pop("km_page", None)
        st.session_state.pop("km_editor", None)

    all_rows = _fetch_key_moments(agent_id_str, schema)
    if all_rows and "error" in all_rows[0]:
        st.error(all_rows[0]["error"])
        return
    if not all_rows:
        st.caption("— no key moments —")
        return

    total = len(all_rows)
    n_pages = max(1, (total + _KM_PAGE_SIZE - 1) // _KM_PAGE_SIZE)
    page = st.session_state.get("km_page", 0)
    page = max(0, min(page, n_pages - 1))

    if n_pages > 1:
        pc1, pc2, pc3 = st.columns([1, 2, 1])
        if pc1.button("◀", key="km_prev", disabled=(page == 0)):
            st.session_state["km_page"] = page - 1
            st.session_state.pop("km_editor", None)
            st.rerun()
        pc2.caption(f"стр. {page + 1} / {n_pages}  ({total} записей)")
        if pc3.button("▶", key="km_next", disabled=(page == n_pages - 1)):
            st.session_state["km_page"] = page + 1
            st.session_state.pop("km_editor", None)
            st.rerun()
    else:
        c_info.caption(f"{total} записей")

    page_rows = all_rows[page * _KM_PAGE_SIZE : (page + 1) * _KM_PAGE_SIZE]

    # Dropdown action column — the only control that lives INSIDE the table
    # and is therefore visible and clickable in full-screen mode.
    # Selecting "🗑 удалить" triggers a rerun; the code below detects it
    # and deletes immediately, no external button needed.
    df = pd.DataFrame([
        {"🗑": False, "_id": r["_id"], "id": r["id"],
         "what": r["what"], "why": r["why"], "changed": r["changed"],
         "depth": r["depth"], "sal": r["sal"], "imp": r["imp"],
         "val/int": f'{r["val"]}/{r["int"]}',
         "values": r["values"], "by": r["by"], "ts": r["ts"]}
        for r in page_rows
    ])

    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        key="km_editor",
        column_config={
            "🗑":      st.column_config.CheckboxColumn("🗑", default=False, width="small"),
            "_id":     None,
            "id":      st.column_config.TextColumn("ID",             disabled=True, width="small"),
            "what":    st.column_config.TextColumn("Что произошло",  disabled=True),
            "why":     st.column_config.TextColumn("Почему важно",   disabled=True),
            "changed": st.column_config.TextColumn("Что изменилось", disabled=True),
            "depth":   st.column_config.TextColumn("Глубина",        disabled=True, width="small"),
            "sal":     st.column_config.NumberColumn("Sal",  disabled=True, width="small", format="%.3f"),
            "imp":     st.column_config.NumberColumn("Imp",  disabled=True, width="small", format="%.3f"),
            "val/int": st.column_config.TextColumn("Val/Int", disabled=True, width="small"),
            "values":  st.column_config.TextColumn("Ценности", disabled=True),
            "by":      st.column_config.TextColumn("Кем",      disabled=True, width="small"),
            "ts":      st.column_config.TextColumn("Записано", disabled=True, width="medium"),
        },
    )

    to_delete_ids = edited.loc[edited["🗑"] == True, "_id"].tolist()
    if to_delete_ids:
        if st.button(f"🗑 Удалить выбранные ({len(to_delete_ids)})", type="primary", key="km_delete"):
            try:
                _delete_key_moments(schema, to_delete_ids)
                _fetch_key_moments.clear()
                st.session_state.pop("km_editor", None)
                st.rerun()
            except Exception as exc:
                st.error(f"Ошибка удаления: {exc}")


# ── Facts table with pagination + delete ─────────────────────────────────────

def _render_facts_table(agent_id_str: str, schema: str) -> None:
    import pandas as pd

    c_refresh, c_info = st.columns([1, 5])
    if c_refresh.button("🔄", key="facts_refresh"):
        _fetch_facts.clear()
        st.session_state.pop("facts_page", None)
        st.session_state.pop("facts_editor", None)

    all_rows = _fetch_facts(agent_id_str)
    if all_rows and "error" in all_rows[0]:
        st.error(all_rows[0]["error"])
        return
    if not all_rows:
        st.caption("— no facts —")
        return

    total = len(all_rows)
    n_pages = max(1, (total + _FACTS_PAGE_SIZE - 1) // _FACTS_PAGE_SIZE)
    page = st.session_state.get("facts_page", 0)
    page = max(0, min(page, n_pages - 1))

    if n_pages > 1:
        pc1, pc2, pc3 = st.columns([1, 2, 1])
        if pc1.button("◀", key="facts_prev", disabled=(page == 0)):
            st.session_state["facts_page"] = page - 1
            st.session_state.pop("facts_editor", None)
            st.rerun()
        pc2.caption(f"стр. {page + 1} / {n_pages}  ({total} записей)")
        if pc3.button("▶", key="facts_next", disabled=(page == n_pages - 1)):
            st.session_state["facts_page"] = page + 1
            st.session_state.pop("facts_editor", None)
            st.rerun()
    else:
        c_info.caption(f"{total} записей")

    page_rows = all_rows[page * _FACTS_PAGE_SIZE : (page + 1) * _FACTS_PAGE_SIZE]

    df = pd.DataFrame([
        {"🗑": False, "_id": r["_id"], "id": r["id"],
         "content": r["content"], "source": r["source"], "tags": r["tags"],
         "status": r["status"], "sal": r["sal"], "confirms": r["confirms"],
         "confirmed": r["confirmed"], "inv_note": r["inv_note"], "ts": r["ts"]}
        for r in page_rows
    ])

    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        key="facts_editor",
        column_config={
            "🗑":       st.column_config.CheckboxColumn("🗑", default=False, width="small"),
            "_id":      None,
            "id":       st.column_config.TextColumn("ID",         disabled=True, width="small"),
            "content":  st.column_config.TextColumn("Содержание", disabled=True),
            "source":   st.column_config.TextColumn("Источник",   disabled=True, width="small"),
            "tags":     st.column_config.TextColumn("Теги",       disabled=True, width="small"),
            "status":   st.column_config.TextColumn("Статус",     disabled=True, width="small"),
            "sal":      st.column_config.NumberColumn("Sal",      disabled=True, width="small", format="%.3f"),
            "confirms": st.column_config.NumberColumn("Подтв.",   disabled=True, width="small"),
            "confirmed":st.column_config.TextColumn("Посл. подтв.", disabled=True, width="medium"),
            "inv_note": st.column_config.TextColumn("Аннулирован", disabled=True),
            "ts":       st.column_config.TextColumn("Создан",     disabled=True, width="medium"),
        },
    )

    to_delete_ids = edited.loc[edited["🗑"] == True, "_id"].tolist()
    if to_delete_ids:
        if st.button(f"🗑 Удалить выбранные ({len(to_delete_ids)})", type="primary", key="facts_delete"):
            try:
                _delete_facts(schema, to_delete_ids)
                _fetch_facts.clear()
                st.session_state.pop("facts_editor", None)
                st.rerun()
            except Exception as exc:
                st.error(f"Ошибка удаления: {exc}")


# ── Debug panel ───────────────────────────────────────────────────────────────

def _render_debug_panel() -> None:
    events_log   = st.session_state.get("events_log", [])
    agent_id_str = st.session_state.get("agent_id_str", "")
    agent_serial = st.session_state.get("agent_serial")
    last_rag     = st.session_state.get("last_rag", {})

    schema = f"agent_{agent_serial}" if agent_serial is not None else None

    tab_ev, tab_km, tab_facts, tab_rag = st.tabs(["Events", "Key Moments", "Facts", "RAG"])

    with tab_ev:
        recent = list(reversed(events_log[-60:]))
        if not recent:
            st.caption("Нет событий")
        for ev in recent:
            st.markdown(_fmt_event(ev))

    with tab_km:
        if schema is None:
            st.warning("DB not available — POSTGRES_* env vars not set")
        else:
            _render_km_table(agent_id_str, schema)

    with tab_facts:
        if schema is None:
            st.warning("DB not available — POSTGRES_* env vars not set")
        else:
            _render_facts_table(agent_id_str, schema)

    with tab_rag:
        if not last_rag:
            st.caption("Пока не было ходов")
        else:
            st.markdown(f"**Passive RAG:** `{last_rag.get('passive', 'none')}`")
            amb = last_rag.get("ambient", "")
            if amb and amb != "none":
                with st.expander("Ambient context"):
                    st.text(amb[:2000])
            inj = last_rag.get("injected", "")
            if inj:
                with st.expander("Injected context (full)"):
                    st.text(inj[:3000])
            else:
                st.caption("injected_context: пусто")


# ── Main ──────────────────────────────────────────────────────────────────────

_initialize()

col_chat, col_debug = st.columns([3, 2])

with col_chat:
    agent_id_str = st.session_state.get("agent_id_str", "?")
    session_id   = st.session_state.get("session_id")
    serial       = st.session_state.get("agent_serial")

    # ── Session-close button ─────────────────────────────────────────────────
    if not st.session_state.get("session_closed"):
        if st.button("🔚 Завершить сессию", type="secondary"):
            with st.status("Завершение сессии…", expanded=True) as status_widget:
                body = st.empty()
                _close_session(body)
                status_widget.update(label="Сессия завершена", state="complete", expanded=True)
    else:
        st.info("Сессия завершена. Обновите страницу чтобы начать новую.")

    st.caption(
        f"agent `{agent_id_str[:8]}…`  "
        f"session `{str(session_id)[:8] if session_id else '?'}…`  "
        f"model `{_AGENT_MODEL}`  "
        f"db schema `{'agent_' + str(serial) if serial else '—'}`"
    )

    # ── Chat messages (scrollable fixed-height container) ────────────────────
    msg_container = st.container(height=300, border=False)  # CSS overrides to calc(100vh-260px)
    with msg_container:
        for msg in st.session_state.get("messages", []):
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    # ── Input ────────────────────────────────────────────────────────────────
    if not st.session_state.get("session_closed"):
        if prompt := st.chat_input("Напиши что-нибудь…"):
            _handle_turn(prompt, msg_container)

with col_debug:
    _render_debug_panel()
