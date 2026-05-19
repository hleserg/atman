"""Helpers for the Streamlit chat page: deps initialization + slog hook factory."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable
from uuid import UUID, uuid4

from atman.adapters.agent.factory import build_deps
from atman.core import session_log

_LOG = logging.getLogger("atman.web_dashboard.utils.chat_deps")


def _resolve_agent_id() -> UUID:
    raw = os.getenv("ATMAN_CURRENT_AGENT", "").strip()
    if raw:
        _LOG.debug("[chat_deps] agent_id from ATMAN_CURRENT_AGENT: %s", raw)
        return UUID(raw)
    # Fall back through ATMAN_AGENT_WORKSPACE → ATMAN_VAULT_PATH → default
    workspace = Path(
        os.getenv("ATMAN_AGENT_WORKSPACE", "")
        or os.getenv("ATMAN_VAULT_PATH", "")
        or str(Path.home() / ".atman" / "dev-agent")
    )
    id_file = workspace / "agent_id.txt"
    if id_file.exists():
        agent_id = UUID(id_file.read_text().strip())
        _LOG.debug("[chat_deps] agent_id from %s: %s", id_file, agent_id)
        return agent_id
    new_id = uuid4()
    workspace.mkdir(parents=True, exist_ok=True)
    id_file.write_text(str(new_id))
    _LOG.warning(
        "[chat_deps] minted new agent_id=%s — agent may not be registered in public.agents."
        " Set ATMAN_CURRENT_AGENT to use an existing agent.",
        new_id,
    )
    return new_id


def get_chat_deps():
    """Build (deps, session_manager, state_store) for the chat UI.

    Same agent resolution as live_chat.py: ATMAN_CURRENT_AGENT or persisted agent_id.txt.
    """
    agent_id = _resolve_agent_id()
    vault = Path(
        os.getenv("ATMAN_VAULT_PATH", "")
        or os.getenv("ATMAN_AGENT_WORKSPACE", "")
        or str(Path.home() / ".atman" / "dev-agent")
    )
    vault.mkdir(parents=True, exist_ok=True)
    _LOG.debug("[chat_deps] building deps: agent_id=%s  vault=%s", agent_id, vault)
    return build_deps(vault, agent_id)


def make_slog_hook(events_store: list[dict]) -> Callable[[str, dict], None]:
    """Return a hook that appends every slog event to ``events_store``."""

    def hook(event: str, data: dict) -> None:
        events_store.append({
            "event": event,
            "data": data,
            "ts": datetime.now(UTC).isoformat(),
        })

    return hook


def install_slog_hook(events_store: list[dict]) -> None:
    """Register the slog hook globally (overwrites any previous hook)."""
    session_log.set_display_hook(make_slog_hook(events_store))
