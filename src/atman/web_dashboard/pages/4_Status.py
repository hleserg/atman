"""System status page — live health snapshot of Atman components.

Shows: PostgreSQL R/W, LLM endpoint, NLP stack, message pipeline, system
prompt, and agent tools. Reads deps from session_state (set by Chat page)
or lets the user connect manually via the sidebar button.

Run:  make chat-ui  (same Streamlit app, navigate via sidebar)
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import streamlit as st


# ── Env loader (same as Chat page) ─────────────────────────────────────────────
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

st.set_page_config(layout="wide", page_title="Atman Status")
st.title("System Status")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _ok(label: str) -> None:
    st.markdown(f"✅ **{label}**")


def _warn(label: str, detail: str = "") -> None:
    st.markdown(f"⚠️ **{label}**" + (f" — {detail}" if detail else ""))


def _err(label: str, detail: str = "") -> None:
    st.markdown(f"❌ **{label}**" + (f" — {detail}" if detail else ""))


def _pkg(name: str) -> bool:
    """Return True if the Python package can be imported."""
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def _pg_url() -> str:
    u = os.getenv("POSTGRES_USER", "")
    if not u:
        return os.getenv("ATMAN_DB_URL") or os.getenv("DATABASE_URL", "")
    return (
        f"postgresql://{u}:{os.getenv('POSTGRES_PASSWORD', '')}"
        f"@{os.getenv('POSTGRES_HOST', 'localhost')}"
        f":{os.getenv('POSTGRES_PORT', '5432')}"
        f"/{os.getenv('POSTGRES_DB', 'atman')}"
    )


# ── Connect button (sidebar) ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Agent connection")
    if st.button("Connect / Refresh", use_container_width=True):
        from atman.web_dashboard.utils.chat_deps import get_chat_deps
        try:
            deps, sm, _ss = get_chat_deps()
            st.session_state["deps"] = deps
            st.session_state["sm"] = sm
            st.success("Connected.")
        except Exception as exc:
            st.error(f"Failed: {exc}")
        st.rerun()

deps = st.session_state.get("deps")
sm = st.session_state.get("sm")

if deps is None:
    st.info("Agent not initialized. Open the **Chat** page first, or click **Connect / Refresh** in the sidebar.")

st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# Section 1 — Connectivity
# ══════════════════════════════════════════════════════════════════════════════
st.header("1 · Connectivity")
col_pg, col_llm = st.columns(2)

with col_pg:
    st.subheader("PostgreSQL")
    pg_url = _pg_url()
    if not pg_url:
        _err("No DB URL", "set POSTGRES_USER / DATABASE_URL / ATMAN_DB_URL")
    else:
        try:
            import psycopg
            t0 = time.perf_counter()
            with psycopg.connect(pg_url, connect_timeout=5) as conn:
                conn.execute("SELECT 1")
                ms_r = int((time.perf_counter() - t0) * 1000)
                # Write check: create + drop a temp table
                t1 = time.perf_counter()
                conn.execute(
                    "CREATE TEMP TABLE _atman_status_probe (id int); "
                    "INSERT INTO _atman_status_probe VALUES (1); "
                    "DROP TABLE _atman_status_probe"
                )
                ms_w = int((time.perf_counter() - t1) * 1000)
            _ok(f"Read OK ({ms_r} ms)")
            _ok(f"Write OK ({ms_w} ms)")
        except Exception as exc:
            _err("PostgreSQL error", str(exc)[:120])

with col_llm:
    st.subheader("LLM endpoint")
    base_url = os.getenv("AGENT_LLM_BASE_URL", "http://localhost:8081/v1")
    model_name = os.getenv("AGENT_LLM_MODEL", "gemma4")
    st.caption(f"`{base_url}`  model: `{model_name}`")
    models_url = base_url.rstrip("/") + "/models"
    try:
        import httpx
        t0 = time.perf_counter()
        resp = httpx.get(models_url, timeout=5, follow_redirects=True)
        ms = int((time.perf_counter() - t0) * 1000)
        if resp.status_code < 400:
            try:
                names = [m.get("id", "?") for m in resp.json().get("data", [])]
                model_list = ", ".join(f"`{n}`" for n in names[:5]) if names else "no models listed"
            except Exception:
                model_list = ""
            _ok(f"Reachable ({ms} ms)" + (f" — {model_list}" if model_list else ""))
        else:
            _warn(f"HTTP {resp.status_code}", f"{ms} ms")
    except Exception as exc:
        _err("LLM endpoint unreachable", str(exc)[:120])

# ══════════════════════════════════════════════════════════════════════════════
# Section 2 — Agent
# ══════════════════════════════════════════════════════════════════════════════
st.header("2 · Agent")
if deps is None:
    st.caption("*Connect first to see agent details.*")
else:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Agent ID:** `{deps.agent_id}`")
        session_id = st.session_state.get("session_id")
        if session_id:
            st.markdown(f"**Session:** `{session_id}` ✅")
        else:
            _warn("No active session", "start a conversation in Chat")

    with c2:
        affect = getattr(sm, "affect_detector", None) if sm else None
        if affect is not None:
            _ok("AffectDetector wired")
            la = getattr(affect, "_linguistic_analyzer", None)
            if la is not None:
                _ok(f"LinguisticAnalyzer: `{type(la).__name__}`")
            else:
                _warn("LinguisticAnalyzer: None inside AffectDetector")
        else:
            _err("AffectDetector is None", "`record_key_moment` will fail silently")

# ══════════════════════════════════════════════════════════════════════════════
# Section 3 — NLP Stack
# ══════════════════════════════════════════════════════════════════════════════
st.header("3 · NLP Stack")

ling_enabled = os.getenv("ATMAN_LINGUISTIC_ENABLED", "true").lower() == "true"
if ling_enabled:
    _ok("ATMAN_LINGUISTIC_ENABLED = true")
else:
    _warn("ATMAN_LINGUISTIC_ENABLED = false", "NLP stack disabled")

nlp_data = [
    ("GLiNER", "gliner", "urchade/gliner_multi-v2.1", "Entity extraction"),
    ("MiniLM (NLI)", "transformers", "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli", "Zero-shot classification"),
    ("BGE-M3", "FlagEmbedding", "BAAI/bge-m3", "Dense embeddings"),
    ("BGE-Reranker", "FlagEmbedding", "BAAI/bge-reranker-v2-m3", "Cross-encoder reranker"),
    ("mREBEL", "transformers", "Babelscape/mrebel-large", "Relation extraction"),
]

missing_pkgs = {pkg for _, pkg, _, _ in nlp_data if not _pkg(pkg)}

for model_label, pkg, model_id, role in nlp_data:
    available = _pkg(pkg)
    icon = "✅" if available else "❌"
    st.markdown(
        f"{icon} **{model_label}** — `{model_id}`  "
        f"<span style='color:grey;font-size:0.85em'>{role} · pkg: `{pkg}` {'installed' if available else 'NOT installed'}</span>",
        unsafe_allow_html=True,
    )

if missing_pkgs:
    st.warning(f"Missing packages: {', '.join(f'`{p}`' for p in sorted(missing_pkgs))}")
    if st.button("Install + warmup  (`pip install atman[linguistic]` → `make warmup-models`)"):
        import subprocess, sys
        repo_root = str(Path(__file__).resolve().parents[4])
        with st.spinner("Step 1/2 — installing packages…"):
            r1 = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", ".[linguistic]"],
                capture_output=True, text=True, cwd=repo_root,
            )
        if r1.returncode != 0:
            st.error("pip install failed")
            st.code(r1.stderr[-2000:], language="text")
        else:
            st.success("Packages installed.")
            with st.spinner("Step 2/2 — warming up models (downloading weights, ~6 GB first run)…"):
                r2 = subprocess.run(
                    [sys.executable, "scripts/warmup_native_models.py"],
                    capture_output=True, text=True, cwd=repo_root,
                    env={**os.environ, "CUDA_VISIBLE_DEVICES": "", "PYTHONPATH": f"{repo_root}/src"},
                )
            if r2.returncode == 0:
                st.success("All models warmed. **Restart the Streamlit server** (`make chat-ui`) to pick up changes.")
                st.code(r2.stdout[-2000:], language="text")
            else:
                st.error("Warmup failed")
                st.code((r2.stdout + r2.stderr)[-2000:], language="text")

# ══════════════════════════════════════════════════════════════════════════════
# Section 4 — Message Pipeline
# ══════════════════════════════════════════════════════════════════════════════
st.header("4 · Message Pipeline")
st.caption("Steps run by AtmanTurn.pre() and AtmanTurn.post() every turn.")

def _pipe(step: str, ok: bool | None, note: str = "") -> None:
    if ok is True:
        icon = "✅"
    elif ok is False:
        icon = "❌"
    else:
        icon = "⚠️"
    st.markdown(f"{icon} **{step}**" + (f" — {note}" if note else ""))


if deps is None:
    st.caption("*Connect first to see pipeline status.*")
else:
    er = deps.entity_registry
    am = deps.ambient_memory
    pm = deps.passive_memory_injector
    mw = deps.maintenance_worker
    rrq = deps.reflection_request_queue
    pri = deps.pending_review_inbox

    _pipe("Entity Registration (pre)",
          er is not None and am is not None,
          f"entity_registry={'✓' if er else '✗'}  ambient_memory={'✓' if am else '✗'}")
    _pipe("Passive RAG injection (pre)",
          pm is not None,
          f"passive_memory_injector={'✓' if pm else '✗'}")
    _pipe("Ambient memory injection (pre)",
          am is not None,
          f"ambient_memory={'✓' if am else '✗'}")

    affect = getattr(sm, "affect_detector", None) if sm else None
    la = getattr(affect, "_linguistic_analyzer", None) if affect else None
    la_name = type(la).__name__ if la else "None"
    is_noop = la_name == "NoOpLinguisticAnalyzer" or la is None

    _pipe("Response analysis (post)",
          affect is not None,
          f"affect={'✓' if affect else '✗'}  linguistic={la_name}")
    _pipe("Auto key moment (post)",
          affect is not None and not is_noop,
          "requires AffectDetector + real LinguisticAnalyzer" if is_noop or affect is None else "")
    _pipe("Identity facts write (post)",
          True,
          "identity_service always available")
    _pipe("Maintenance drain (post)",
          mw is not None,
          f"maintenance_worker={'✓' if mw else '✗'}")
    _pipe("Reflection queue (post)",
          rrq is not None,
          f"reflection_request_queue={'✓' if rrq else '✗'}")
    _pipe("Pending review inbox (post)",
          pri is not None,
          f"pending_review_inbox={'✓' if pri else '✗'}")

# ══════════════════════════════════════════════════════════════════════════════
# Section 5 — System Prompt
# ══════════════════════════════════════════════════════════════════════════════
st.header("5 · System Prompt")

if deps is None:
    st.caption("*Connect first to see system prompt.*")
else:
    from atman.adapters.agent.instructions import build_instructions
    try:
        instructions = build_instructions(deps)
        char_count = len(instructions)
        st.caption(
            f"Source: `atman.adapters.agent.instructions.build_instructions` · "
            f"{char_count} chars"
        )
        with st.expander("Show system prompt", expanded=False):
            st.code(instructions, language="markdown")
    except Exception as exc:
        _err("Failed to build system prompt", str(exc)[:200])

# ══════════════════════════════════════════════════════════════════════════════
# Section 6 — Agent Skills
# ══════════════════════════════════════════════════════════════════════════════
st.header("6 · Agent Skills")

TOOLS_INFO = [
    ("record_key_moment", "Records a significant moment with emotional valence. Requires AffectDetector."),
    ("restart_session", "Agent-initiated session restart with optional reason."),
    ("wait_session", "Suspend session for N minutes (sleep mode)."),
    ("resolve_pending_review", "Commit or discard a pending human-review item."),
    ("request_reflection", "Queue a reflection job (micro/daily/deep)."),
]

for tool_name, tool_desc in TOOLS_INFO:
    with st.container():
        col_name, col_desc = st.columns([1, 3])
        with col_name:
            st.markdown(f"`{tool_name}`")
        with col_desc:
            st.caption(tool_desc)

st.markdown("---")
st.subheader("record_key_moment — quick test")
st.caption(
    "Calls `AffectDetector.submit_self_report` directly — bypasses the agent "
    "so you can verify the DB write path independently."
)

affect = getattr(sm, "affect_detector", None) if sm else None
session_id = st.session_state.get("session_id")

if deps is None:
    st.caption("*Connect first.*")
elif affect is None:
    _err(
        "AffectDetector is None",
        "cannot test record_key_moment. "
        "Check factory.py: AffectDetector is wired only when PostgreSQL is available.",
    )
elif session_id is None:
    _warn(
        "No active session",
        "open Chat and send a message first to start a session, then return here to test.",
    )
else:
    if st.button("Run test: record_key_moment"):
        from atman.affect.models import AgentMemoryReport
        from atman.core.models import EmotionalDepth

        try:
            report = AgentMemoryReport(
                content="Status page probe: testing the AffectDetector → DB write pipeline.",
                why_it_matters="Verifying record_key_moment tool path is intact.",
                emotional_valence=0.1,
                emotional_intensity=0.2,
                emotional_depth=EmotionalDepth.PASSING,
                self_reported_emotions=["curious"],
                tags=["atman:status-probe"],
            )
            asyncio.run(affect.submit_self_report(report, session_id=session_id))
            st.success("Key moment recorded successfully. Check the Key Moments tab in Chat.")
        except Exception as exc:
            st.error(f"record_key_moment failed: {type(exc).__name__}: {exc}")
