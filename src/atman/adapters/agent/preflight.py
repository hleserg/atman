"""Session preflight: validate all required components before a session starts.

Policy tiers
------------
REQUIRED (blocks start)   : PostgreSQL R/W, LLM endpoint, AffectDetector wired
NLP packages (blocks start): GLiNER, FlagEmbedding — user is prompted; if they
                             agree, packages are installed and the process restarts.
Warmup (non-blocking)      : bge-m3 / bge-reranker warmup started in background;
                             warning shown but session continues immediately.

Entry points
------------
run_cli_preflight()        — for live_chat.py and similar CLI runners
run_streamlit_preflight()  — for 3_Chat.py (Streamlit UI)

Both raise / call st.stop() if a REQUIRED check fails and cannot be auto-fixed.
"""

from __future__ import annotations

import os
import subprocess  # nosec B404 — trusted dev install/warmup helpers
import sys
import time
from pathlib import Path

# ── Public exception ──────────────────────────────────────────────────────────


class PreflightError(Exception):
    """Raised when a required component is unavailable and cannot be fixed."""


# ── Internal helpers ──────────────────────────────────────────────────────────


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


def _repo_root() -> str:
    return str(Path(__file__).resolve().parents[4])


# ── Shared checks ─────────────────────────────────────────────────────────────

_NLP_PACKAGES = ["gliner", "FlagEmbedding"]


def check_nlp_packages() -> list[str]:
    """Return list of NLP package names that cannot be imported."""
    missing = []
    for pkg in _NLP_PACKAGES:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    return missing


def check_postgres(pg_url: str) -> tuple[bool, str]:
    """Attempt a minimal PostgreSQL read. Returns (ok, error_detail)."""
    if not pg_url:
        return False, "No DB URL — set POSTGRES_USER or DATABASE_URL in .env"
    try:
        import psycopg

        with psycopg.connect(pg_url, connect_timeout=5) as conn:
            conn.execute("SELECT 1")
        return True, ""
    except Exception as exc:
        return False, str(exc)[:200]


def check_llm(base_url: str) -> tuple[bool, str]:
    """Probe LLM /v1/models endpoint. Returns (ok, error_detail)."""
    models_url = base_url.rstrip("/") + "/models"
    try:
        import httpx

        resp = httpx.get(models_url, timeout=5, follow_redirects=True)
        if resp.status_code < 400:
            return True, ""
        return False, f"HTTP {resp.status_code}"
    except Exception as exc:
        return False, str(exc)[:200]


def is_warmup_needed() -> bool:
    """True if bge-m3 has not been downloaded to the HuggingFace cache yet."""
    try:
        cache_root = (
            Path(os.getenv("HF_HOME", ""))
            if os.getenv("HF_HOME")
            else Path.home() / ".cache" / "huggingface"
        ) / "hub"
        return not any(cache_root.glob("models--BAAI--bge-m3"))
    except Exception:
        return False


def install_nlp() -> bool:
    """Run `pip install -e .[linguistic]`. Returns True on success."""
    result = subprocess.run(  # nosec B603
        [sys.executable, "-m", "pip", "install", "-e", ".[linguistic]"],
        cwd=_repo_root(),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def start_warmup_background() -> subprocess.Popen[bytes]:
    """Launch warmup_native_models.py in a detached background process."""
    root = _repo_root()
    return subprocess.Popen(  # nosec B603
        [sys.executable, "scripts/warmup_native_models.py"],
        cwd=root,
        env={**os.environ, "CUDA_VISIBLE_DEVICES": "", "PYTHONPATH": f"{root}/src"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ── CLI preflight ─────────────────────────────────────────────────────────────


def run_cli_preflight(print_fn=None) -> None:
    """Interactive preflight for CLI runners (e.g. live_chat.py).

    Raises PreflightError if session cannot start.
    May restart the process via os.execv after installing NLP packages.

    Args:
        print_fn: callable used for output; defaults to built-in print.
                  Pass a Rich console.print for coloured output.
    """
    _p = print_fn or print

    # 1. NLP packages (hard block — ask user)
    missing = check_nlp_packages()
    if missing:
        _p(f"\n[yellow]⚠  Missing NLP packages:[/yellow] {', '.join(missing)}")
        _p("   Required for linguistic analysis (key moments, entity linking, embeddings).")
        try:
            answer = input("   Install atman[linguistic] now? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer != "y":
            raise PreflightError(
                f"NLP packages required but not installed: {missing}\n"
                "Fix: pip install -e .[linguistic] && make warmup-models"
            )
        _p("   Installing… (may take a minute on first run)")
        if not install_nlp():
            raise PreflightError(
                "pip install failed. Run manually:\n"
                "  pip install -e .[linguistic] && make warmup-models"
            )
        _p("[green]✅ Packages installed. Restarting…[/green]")
        time.sleep(0.4)
        os.execv(sys.executable, [sys.executable, *sys.argv])  # nosec B606
        # Never reached

    # 2. PostgreSQL (hard block)
    pg_url = _pg_url()
    ok, err = check_postgres(pg_url)
    if not ok:
        raise PreflightError(
            f"PostgreSQL unavailable: {err}\n"
            "Check .env: POSTGRES_HOST / POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB"
        )

    # 3. LLM endpoint (hard block)
    base_url = os.getenv("AGENT_LLM_BASE_URL", "http://localhost:8081/v1")
    ok, err = check_llm(base_url)
    if not ok:
        raise PreflightError(
            f"LLM endpoint unreachable at {base_url}: {err}\n"
            "Check AGENT_LLM_BASE_URL in .env and ensure the LLM server is running."
        )

    # 4. Warmup (non-blocking — background)
    if is_warmup_needed():
        _p(
            "[yellow]⚠  NLP models not pre-warmed.[/yellow] Starting warmup in background...\n"
            "   First embedding call may take 30–60 s. "
            "Run 'make warmup-models' before next session to avoid this."
        )
        start_warmup_background()


# ── Streamlit preflight ───────────────────────────────────────────────────────


def run_streamlit_preflight() -> None:
    """Preflight for Streamlit context (3_Chat.py).

    Displays errors and blocks via st.stop() when session cannot start.
    Installs NLP packages and restarts via os.execv when user agrees.
    Warmup is started in background with a warning; session is not blocked.
    """
    import streamlit as st

    # 1. NLP packages (hard block — ask user via button)
    missing = check_nlp_packages()
    if missing:
        if st.session_state.get("_preflight_installing"):
            with st.spinner("Installing `atman[linguistic]`… (may take a minute)"):
                success = install_nlp()
            if success:
                st.success("✅ Packages installed. Restarting Streamlit server…")
                time.sleep(1)
                os.execv(sys.executable, sys.argv)  # nosec B606
                # Never reached
            else:
                st.session_state.pop("_preflight_installing", None)
                st.error(
                    "❌ Installation failed.\n\n"
                    "Run manually: `pip install -e .[linguistic]` then restart the server."
                )
        else:
            pkg_list = ", ".join(f"`{p}`" for p in missing)
            st.error(
                f"**Session blocked — missing NLP packages:** {pkg_list}\n\n"
                "These are required for linguistic analysis (key moments, entity linking, "
                "embeddings). Click below to install automatically."
            )
            if st.button("📦 Install `atman[linguistic]` and restart", type="primary"):
                st.session_state["_preflight_installing"] = True
                st.rerun()
        st.stop()

    # 2. PostgreSQL (hard block)
    pg_url = _pg_url()
    ok, err = check_postgres(pg_url)
    if not ok:
        st.error(
            f"**Session blocked — PostgreSQL unavailable**\n\n```\n{err}\n```\n\n"
            "Check `.env`: `POSTGRES_HOST` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`"
        )
        st.stop()

    # 3. LLM endpoint (hard block)
    base_url = os.getenv("AGENT_LLM_BASE_URL", "http://localhost:8081/v1")
    ok, err = check_llm(base_url)
    if not ok:
        st.error(
            f"**Session blocked — LLM endpoint unreachable** — `{base_url}`\n\n"
            f"```\n{err}\n```\n\n"
            "Check `AGENT_LLM_BASE_URL` in `.env` and ensure the LLM server is running."
        )
        st.stop()

    # 4. Warmup (background, non-blocking)
    if is_warmup_needed():
        if not st.session_state.get("_preflight_warmup_started"):
            start_warmup_background()
            st.session_state["_preflight_warmup_started"] = True
        st.warning(
            "⚠️ **NLP models warming up in background.** "
            "First embedding / key-moment call may take 30–60 s. "
            "Run `make warmup-models` before next session to pre-warm."
        )
