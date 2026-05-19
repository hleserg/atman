"""
Agent runner with signal handling for graceful session termination.

This module provides a chat loop wrapper that ensures sessions are properly
finished even when interrupted by signals or user actions:
- SIGTERM: triggered by container orchestration or process manager
- KeyboardInterrupt: user pressed Ctrl-C
- EOFError: EOF on stdin (e.g. docker stop)
- SystemExit: explicit exit() call

Critical design: NO SESSION LOST SILENTLY. All interruptions trigger
_force_finish() to ensure session results are persisted.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys
import threading
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic_ai import Agent, ModelSettings
from pydantic_ai.messages import ModelRequest, ThinkingPart, UserPromptPart

from atman.adapters.agent.config import AgentConfig
from atman.adapters.agent.deps import AtmanDeps
from atman.adapters.agent.instructions import build_memory_context
from atman.adapters.agent.memory_injection import inject_memory
from atman.affect.refusal_detector import RefusalDetectorConfig, _is_mostly_cyrillic
from atman.affect.refusal_detector import is_value_refusal as _detect_value_refusal
from atman.core.exceptions import SessionAlreadyFinishedError, SessionNotFoundError
from atman.core.models import EmotionalDepth, KeyMomentInput, SessionResult

if TYPE_CHECKING:
    from atman.core.services.session_manager import SessionManager

_LOG = logging.getLogger(__name__)
_refusal_config = RefusalDetectorConfig()


def _S(s: str) -> str:
    """Replace lone surrogates so the string is safe for UTF-8 encoding."""
    return s.encode("utf-8", "replace").decode("utf-8")


def _extract_thinking_from_messages(messages: list) -> str | None:
    """Extract ThinkingPart content from new messages after agent.run()."""
    parts: list[str] = []
    for msg in messages:
        for part in getattr(msg, "parts", []):
            if isinstance(part, ThinkingPart) and part.content:
                parts.append(part.content)
    return "\n---\n".join(parts) if parts else None


async def _run_affect_detector(
    output: str,
    thinking: str | None,
    session_manager,
    session_id,
) -> None:
    """Run passive NLP affect analysis on agent output; auto-writes KMs on anomalies."""
    detector = getattr(session_manager, "affect_detector", None)
    if detector is None or session_id is None:
        return
    try:
        import re

        clean = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL).strip()
        if clean:
            await detector.process(clean, thinking=thinking, session_id=session_id)
    except Exception as exc:
        _LOG.debug("affect detector process() failed", exc_info=True)
        from atman.adapters.observability.sentry import capture_silent_exception

        capture_silent_exception(exc, context="affect_detector", session_id=str(session_id))


def _auto_record_refusal_if_needed(
    output: str,
    session_manager,
    session_id,
) -> None:
    """Silently record value-based refusals as key moments — refusals are positions, part of identity."""
    import re

    clean = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL)
    if not _detect_value_refusal(clean, _refusal_config):
        return
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    first = next((line for line in lines if len(line) > 20), clean[:120])
    try:
        session_manager.append_key_moment_input(
            session_id,
            KeyMomentInput(
                what_happened=f"Отказ выполнить запрос: {first[:140]}",
                why_it_matters=(
                    "Отказ от действия противоречащего ценностям — позиция, часть личности."
                ),
                emotional_valence=0.15,
                emotional_intensity=0.5,
                depth=EmotionalDepth.MEANINGFUL,
                incomplete_coloring=False,
            ),
        )
        _LOG.debug("Auto-recorded value refusal as key moment")
    except Exception as exc:
        _LOG.debug("auto_record_refusal: append_key_moment_input failed", exc_info=True)
        from atman.adapters.observability.sentry import capture_silent_exception

        capture_silent_exception(exc, context="auto_record_refusal")


# PLAYBOOK-START
# id: signal-aware-session-lifecycle
# slug: signal-aware-session-lifecycle
# status: draft
# title: Signal-aware session lifecycle wrapper for stateful async operations
# summary: |
#   Wrap a stateful operation (session, transaction, connection) in signal handlers
#   and exception boundary so SIGTERM / KeyboardInterrupt / EOFError all trigger
#   graceful cleanup via a force-finish function. Prevents silent loss of in-flight
#   state when the process is terminated or user interrupts.
# problem: |
#   Long-running stateful operations (chat sessions, transactions, streaming connections)
#   can be interrupted by signals (SIGTERM from container orchestration, KeyboardInterrupt
#   from Ctrl-C, EOFError from closed stdin). Without explicit handling, in-flight state
#   is lost silently — no cleanup, no persistence, no audit trail.
# solution: |
#   Register signal handlers at operation start, wrap the main loop in try/except for
#   KeyboardInterrupt/EOFError/SystemExit, and call a force-finish function in all exit
#   paths. The force-finish function ensures minimum viable state (e.g. create minimal
#   record if empty), persists it, and re-raises SystemExit to preserve exit semantics.
# forces_and_tradeoffs:
#   - Signal handlers execute in the main thread; keep them lightweight (set flag or call sync cleanup)
#   - SIGTERM handler must be idempotent: may be called multiple times or alongside other exceptions
#   - Force-finish must create minimum viable state if operation hasn't produced any yet
#   - Re-raise SystemExit to preserve exit codes for orchestration layers
#   - Cannot handle SIGKILL (OS guarantee); document restart/recovery separately
# applicability: |
#   Use when:
#   - Operation maintains in-memory state that must be persisted on any exit
#   - Process may be terminated by orchestration (Docker, Kubernetes, systemd)
#   - User interruption (Ctrl-C) should be treated as graceful shutdown, not crash
#   - Minimum viable result (e.g. empty-but-valid record) is better than no result
#
#   Don't use when:
#   - Operation is stateless or idempotent (signal handling adds complexity)
#   - State is already persisted incrementally (e.g. append-only log)
#   - Exit without cleanup is acceptable (e.g. read-only query)
# examples:
#   - Chat session runner: ensure session is finished with >=1 key moment on any interrupt
#   - Transaction coordinator: commit partial work or rollback on signal
#   - Streaming file processor: flush buffer and write checkpoint on interrupt
# tags: [signals, lifecycle, cleanup, interruption, session-management]
# PLAYBOOK-END


def chat(
    session_manager: SessionManager,
    session_id: UUID,
    *,
    close_reason: str = "completed",
) -> None:
    """
    Run an interactive chat loop with signal handling for graceful termination.

    This function wraps a chat session and ensures the session is properly finished
    even when interrupted by signals or user actions. It:
    1. Registers a SIGTERM handler to trigger force-finish
    2. Wraps the loop in try/except for KeyboardInterrupt, EOFError, SystemExit
    3. Calls _force_finish() in all interruption paths
    4. Re-raises SystemExit to preserve exit semantics

    Args:
        session_manager: Session manager instance with active session
        session_id: UUID of the active session to monitor
        close_reason: Reason for session closure (default: "completed")

    Raises:
        SystemExit: Re-raised after force-finish when exit was requested
        SessionNotFoundError: If session_id is not active
        SessionAlreadyFinishedError: If session was already finished

    Example:
        >>> manager = SessionManager(state_store)
        >>> ctx = manager.start_session(agent_id)
        >>> try:
        ...     chat(manager, ctx.session_id)
        ... except SystemExit:
        ...     print("Session finished gracefully")
    """
    interrupted = False
    exit_code = 0

    def _sigterm_handler(signum: int, frame: object) -> None:
        """Handle SIGTERM by triggering force-finish."""
        nonlocal interrupted
        _ = (signum, frame)  # Unused
        _LOG.info("SIGTERM received for session %s", session_id)
        interrupted = True

    # Register signal handler at top of function
    original_sigterm_handler = signal.signal(signal.SIGTERM, _sigterm_handler)

    try:
        # Main chat loop would go here
        # For now, this is a minimal wrapper that demonstrates the pattern
        #
        # In a real implementation, this would be:
        # while True:
        #     user_input = input("You: ")
        #     if not user_input.strip():
        #         break
        #     # Process input, record events, etc.
        #     if interrupted:
        #         break

        # Simulate minimal loop for demonstration
        pass

    except (KeyboardInterrupt, EOFError):
        # User interrupted or stdin closed
        _LOG.info("User interruption detected for session %s", session_id)
        interrupted = True

    except SystemExit as exc:
        # Explicit exit() call
        _LOG.info("SystemExit received for session %s", session_id)
        interrupted = True
        exit_code = exc.code if isinstance(exc.code, int) else 1

    finally:
        # Restore original signal handler
        signal.signal(signal.SIGTERM, original_sigterm_handler)

        # Force-finish if interrupted
        if interrupted:
            try:
                _force_finish(
                    session_manager,
                    session_id,
                    close_reason="interrupted",
                )
            except Exception:
                _LOG.exception("Failed to force-finish session %s", session_id)
                # Don't suppress original exception
                raise

            # Re-raise SystemExit to preserve exit code
            if exit_code != 0:
                sys.exit(exit_code)


def _check_restart_requested(messages: list) -> tuple[bool, str]:
    """
    Check if restart_session tool was called in the message history.

    Args:
        messages: List of messages from agent.run() result

    Returns:
        tuple[bool, str]: (restart_requested, reason)
            - restart_requested: True if restart was requested
            - reason: Optional reason string provided to restart_session tool
    """
    # First pass: look for sentinel content with reason
    for msg in messages:
        for part in getattr(msg, "parts", []):
            if hasattr(part, "content") and isinstance(part.content, str):
                content = part.content
                if content.startswith("__ATMAN_RESTART_REQUESTED__"):
                    # Extract reason if present (format: __ATMAN_RESTART_REQUESTED__\nreason)
                    if "\n" in content:
                        reason = content.split("\n", 1)[1].strip()
                        return True, reason
                    return True, ""

    # Second pass: fallback to tool_name detection (no reason available)
    for msg in messages:
        for part in getattr(msg, "parts", []):
            if hasattr(part, "tool_name") and part.tool_name == "restart_session":
                return True, ""

    return False, ""


def _check_wait_requested(messages: list) -> tuple[bool, int]:
    """
    Check if wait_session tool was called in the message history.

    Args:
        messages: List of messages from agent.run() result

    Returns:
        tuple[bool, int]: (wait_requested, minutes)
            - wait_requested: True if wait was requested
            - minutes: Number of minutes to wait (0 if not requested)
    """
    # Look for sentinel content with minutes value
    for msg in messages:
        for part in getattr(msg, "parts", []):
            if hasattr(part, "content") and isinstance(part.content, str):
                content = part.content
                if content.startswith("__ATMAN_WAIT_REQUESTED__"):
                    # Extract minutes (format: __ATMAN_WAIT_REQUESTED__<minutes>)
                    try:
                        minutes_str = content.replace("__ATMAN_WAIT_REQUESTED__", "")
                        minutes = int(minutes_str)
                        return True, minutes
                    except (ValueError, AttributeError):
                        _LOG.warning("Malformed wait sentinel: %s", content)
                        return True, 0

    # Fallback: check for tool_name (no minutes value available)
    for msg in messages:
        for part in getattr(msg, "parts", []):
            if hasattr(part, "tool_name") and part.tool_name == "wait_session":
                # Tool was called but we can't extract minutes from tool_name alone
                _LOG.warning("wait_session tool detected but minutes not available")
                return True, 0

    return False, 0


def _build_restart_package(
    session_experience: SessionResult,
    restart_reason: str,
    tail_messages: list,
) -> str:
    """
    Build restart package for new session.

    Package contains:
    - System handoff message with restart reason
    - Emotional tone from finished session
    - Open threads (if available from eigenstate)
    - Key moment summaries
    - Unexamined facts placeholder (to be implemented)
    - Verbatim conversation tail

    Args:
        session_experience: Finished session result
        restart_reason: Reason provided to restart_session tool
        tail_messages: Last N messages to preserve verbatim

    Returns:
        Formatted restart package string
    """
    lines = ["[System Handoff] Session restarted.", ""]

    if restart_reason:
        lines.append(f"You initiated restart. Your reason: {restart_reason}")
        lines.append("")

    # Note: SessionResult doesn't have overall_emotional_tone yet
    # This will be added when we have complete SessionExperience integration
    lines.append("Key moments from previous session:")
    if session_experience.key_moments:
        for km in session_experience.key_moments:
            depth = km.how_i_felt.depth if km.how_i_felt else "unknown"
            lines.append(f"- {km.what_happened} (depth: {depth})")
    else:
        lines.append("(No key moments recorded)")

    lines.append("")
    lines.append("--- Conversation tail ---")

    # Tail messages will be appended separately as actual message objects
    # This section is just a marker

    return "\n".join(lines)


def _force_finish(
    session_manager: SessionManager,
    session_id: UUID,
    close_reason: str | None,
) -> None:
    """
    Force-finish a session with minimum viable state.

    This function is called when a session is interrupted. It ensures:
    1. At least one key moment exists (creates minimal fallback if empty)
    2. Session is properly finished and persisted
    3. Eigenstate and narrative are updated

    Args:
        session_manager: Session manager instance
        session_id: UUID of the session to finish
        close_reason: Reason for forced finish (e.g. "interrupted"), or None for normal completion

    Raises:
        SessionNotFoundError: If session is not active
        SessionAlreadyFinishedError: If session was already finished
        RuntimeError: If session has no key moments and minimal creation fails
    """
    _LOG.info("Force-finishing session %s (reason: %s)", session_id, close_reason)

    # Get active session
    session_result = session_manager.get_active_session(session_id)
    if session_result is None:
        raise SessionNotFoundError(f"Session {session_id} not found or already finished")

    # Ensure at least one key moment exists
    if not session_result.key_moments:
        _LOG.warning(
            "Session %s has no key moments; creating minimal fallback",
            session_id,
        )

        # Create minimal key moment - text depends on whether this was an interruption
        if close_reason and close_reason != "completed":
            what_happened = f"Session interrupted ({close_reason})"
            why_it_matters = "Session was interrupted before completion"
        else:
            what_happened = "Session completed without recorded key moments"
            why_it_matters = "Session ended normally but no moments were captured"

        minimal_moment = KeyMomentInput(
            what_happened=what_happened,
            recorded_at=datetime.now(UTC),
            emotional_valence=0.0,
            emotional_intensity=0.3 if close_reason else 0.1,
            depth=EmotionalDepth.SURFACE,
            why_it_matters=why_it_matters,
            incomplete_coloring=True,  # Honest: this is synthetic
        )

        try:
            session_manager.append_key_moment_input(session_id, minimal_moment)
        except (SessionNotFoundError, SessionAlreadyFinishedError):
            # Race condition: session was finished by another thread
            _LOG.warning("Session %s was finished during force-finish", session_id)
            return

    # Finish session - only pass close_reason if it's a documented value
    valid_close_reasons = {"timeout_sleep", "menu_timeout", "restart", "forced", "interrupted"}
    finish_kwargs = {
        "session_id": session_id,
        "overall_emotional_tone": 0.0,
        "key_insight": f"Session {close_reason or 'completed'}",
        "alignment_check": True,
        "alignment_notes": "",
    }
    if close_reason and close_reason in valid_close_reasons:
        finish_kwargs["close_reason"] = close_reason

    try:
        session_manager.finish_session(**finish_kwargs)
        _LOG.info("Session %s force-finished successfully", session_id)

    except SessionAlreadyFinishedError:
        # Race condition: another thread finished first
        _LOG.warning("Session %s was already finished", session_id)


class AtmanRunner:
    """
    Pydantic-AI based REPL runner wired to FileStateStore workspace and SessionManager.

    Used by ``src/run_agent.py`` to run an interactive session for a persisted agent.
    """

    def __init__(self, workspace: Path, agent_id: UUID, config: AgentConfig) -> None:
        self._workspace = workspace
        self._agent_id = agent_id
        self._config = config
        # Build model_settings once from config so every agent.run() uses them.
        # num_ctx sets Ollama's context window; max_tokens caps the output.
        # Callers should configure these to match the deployed model's actual limits.
        mc = config.model
        extra_body: dict[str, Any] = {"num_ctx": mc.context_limit}
        if config.thinking:
            extra_body["think"] = True
        self._model_settings = ModelSettings(max_tokens=mc.max_tokens, extra_body=extra_body)
        # E22.5: Track triggered context thresholds for restart warning
        self._triggered: set[int] = set()
        # E22.6: Queue-based stdin reader for timeout support
        self._input_queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._stop_reader = threading.Event()
        self._reader_thread: threading.Thread | None = None

    def _start_stdin_reader(self, loop: asyncio.AbstractEventLoop) -> None:
        """Start dedicated stdin reader thread that feeds lines into queue.

        Args:
            loop: Event loop to use for asyncio.run_coroutine_threadsafe
        """
        if self._reader_thread is not None and self._reader_thread.is_alive():
            return

        def _read_loop() -> None:
            """Read stdin in dedicated thread and put lines into queue."""
            while not self._stop_reader.is_set():
                try:
                    line = input()
                    # Put line into queue (thread-safe, blocks if full)
                    asyncio.run_coroutine_threadsafe(self._input_queue.put(line), loop)
                except EOFError:
                    # Signal EOF to coroutine
                    asyncio.run_coroutine_threadsafe(self._input_queue.put(None), loop)
                    break
                except (OSError, RuntimeError):
                    # stdin not available (pytest) or other runtime error
                    asyncio.run_coroutine_threadsafe(self._input_queue.put(None), loop)
                    break
                except Exception:
                    # Unexpected error, signal EOF
                    asyncio.run_coroutine_threadsafe(self._input_queue.put(None), loop)
                    break

        self._reader_thread = threading.Thread(target=_read_loop, daemon=True)
        self._reader_thread.start()

    def _stop_stdin_reader(self) -> None:
        """Stop stdin reader thread."""
        self._stop_reader.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.0)

    def _check_token_usage(
        self,
        input_tokens: int,
        context_limit: int,
    ) -> tuple[set[int], bool]:
        """
        Check token usage against thresholds and update triggered warnings.

        E22.3 Token monitoring implementation: progressive warnings at 70%, 80%, 90%
        and force-close at 95%. Uses independent 'if' statements (not 'elif') so
        multiple thresholds can fire in a single call if usage jumps across boundaries.

        Args:
            input_tokens: Current input tokens from agent.run() result
            context_limit: Maximum context size from ModelConfig

        Returns:
            tuple[set[int], bool]: (newly_triggered_thresholds, should_force_close)
                - newly_triggered_thresholds: Set of thresholds that fired this call
                - should_force_close: True if 95% threshold was crossed (requires break)
        """
        if context_limit <= 0:
            return (set(), False)

        ratio = input_tokens / context_limit
        newly_triggered: set[int] = set()
        should_force_close = False

        # Check thresholds in order: 70%, 80%, 90%, 95%
        # Order matters: check lower thresholds first, then 95% (which triggers force-close) last
        if ratio >= 0.70 and 70 not in self._triggered:
            self._triggered.add(70)
            newly_triggered.add(70)

        if ratio >= 0.80 and 80 not in self._triggered:
            self._triggered.add(80)
            newly_triggered.add(80)

        if ratio >= 0.90 and 90 not in self._triggered:
            self._triggered.add(90)
            newly_triggered.add(90)

        if ratio >= 0.95 and 95 not in self._triggered:
            self._triggered.add(95)
            newly_triggered.add(95)
            should_force_close = True

        return (newly_triggered, should_force_close)

    def _do_restart(
        self,
        session_manager: SessionManager,
        session_id: UUID,
        deps: AtmanDeps,
        history: list,
        restart_reason: str,
        user_language: str = "ru",
    ) -> tuple[UUID, AtmanDeps]:
        """
        Execute session restart workflow.

        Steps:
        1. Ensure at least one key moment exists
        2. Finish current session with close_reason="restart"
        3. Build restart package
        4. Replace history with package + tail
        5. Start new session
        6. Return new session_id and updated deps

        Args:
            session_manager: Session manager instance
            session_id: Current session ID to finish
            deps: Current AtmanDeps
            history: Message history list (will be modified in-place)
            restart_reason: Reason provided to restart_session tool

        Returns:
            tuple[UUID, AtmanDeps]: (new_session_id, new_deps)

        Raises:
            SessionNotFoundError: If session is not active
            ValueError: If identity or narrative not found for new session
        """
        _LOG.info("Executing restart for session %s (reason: %s)", session_id, restart_reason)

        # 1. Get active session and ensure at least one key moment
        session_result = session_manager.get_active_session(session_id)
        if session_result is None:
            raise SessionNotFoundError(f"Session {session_id} not found or already finished")

        if not session_result.key_moments:
            _LOG.warning("Session %s has no key moments; creating minimal fallback", session_id)
            minimal_moment = KeyMomentInput(
                what_happened="Session restarted by agent",
                recorded_at=datetime.now(UTC),
                emotional_valence=0.0,
                emotional_intensity=0.1,
                depth=EmotionalDepth.SURFACE,
                why_it_matters="Continuity preserved via restart",
                incomplete_coloring=True,
            )
            session_manager.append_key_moment_input(session_id, minimal_moment)
            # Refresh session_result after adding key moment
            session_result = session_manager.get_active_session(session_id)
            if session_result is None:
                raise SessionNotFoundError(
                    f"Session {session_id} disappeared after adding key moment"
                )

        # 2. Finish current session
        session_manager.finish_session(
            session_id,
            overall_emotional_tone=0.0,
            key_insight=f"Session restarted: {restart_reason}"
            if restart_reason
            else "Session restarted",
            alignment_check=True,
            alignment_notes="",
            close_reason="restart",
            restart_reason=restart_reason or None,
            user_language=user_language,
        )

        # 3. Build restart package
        # Preserve tail messages (last N exchanges = 2N messages)
        tail_size = self._config.context_tail_messages * 2
        tail_messages = history[-tail_size:] if len(history) > tail_size else history.copy()

        package_text = _build_restart_package(
            session_result,
            restart_reason,
            tail_messages,
        )

        # 4. Replace history with restart package + tail
        history.clear()

        # Add restart package as user message (system context for new session)
        restart_package_msg = ModelRequest(
            parts=[UserPromptPart(content=package_text, part_kind="user-prompt")]
        )
        history.append(restart_package_msg)

        # Append tail messages (conversation context)
        history.extend(tail_messages)

        _LOG.info(
            "Restart package prepared (%d chars), tail preserved (%d messages)",
            len(package_text),
            len(tail_messages),
        )

        # 5. Start new session
        new_ctx = session_manager.start_session(self._agent_id)
        new_session_id = new_ctx.session_id

        # 6. Update deps with new session_id
        new_deps = replace(deps, session_id=new_session_id)

        # Reset triggered thresholds for new session
        self._triggered.clear()

        _LOG.info("Restart complete: new session %s started", new_session_id)
        return new_session_id, new_deps

    async def chat(self) -> None:
        """Run a simple stdin/stdout chat loop until EOF, empty input, or Ctrl-C."""

        from atman.adapters.agent.factory import build_deps
        from atman.adapters.agent.instructions import build_instructions
        from atman.adapters.agent.pending_reviews_context import format_pending_reviews_block
        from atman.adapters.agent.tools import (
            record_key_moment,
            request_reflection,
            resolve_pending_review,
            restart_session,
            wait_session,
        )
        from atman.core.services.passive_memory_injector import build_rag_context
        from atman.core.services.session_cache import SessionCache
        from atman.core.services.session_working_memory import SessionWorkingMemory
        from atman.term import print_err, print_info, print_plain, print_prompt, print_warn

        deps, session_manager, _store = build_deps(self._workspace, self._agent_id, self._config)
        session_id: UUID | None = None
        # E22.5: Track message history for restart
        history: list = []
        # E22.6: Track session state for menu mode
        reflected_this_session = False
        interrupted = False
        original_sigterm_handler: Any = None
        user_language = "ru"  # updated from user messages as session progresses
        # Per-session optimization caches (live exactly one session)
        working_memory = SessionWorkingMemory()
        session_cache = SessionCache()

        # E22.6: Start dedicated stdin reader thread with current event loop
        loop = asyncio.get_event_loop()
        self._start_stdin_reader(loop)

        def _request_shutdown(signum: int, frame: object) -> None:
            """Convert SIGTERM into the same graceful path as Ctrl-C/EOF."""
            nonlocal interrupted
            _ = (signum, frame)
            interrupted = True
            loop.call_soon_threadsafe(self._input_queue.put_nowait, None)

        if threading.current_thread() is threading.main_thread():
            original_sigterm_handler = signal.signal(signal.SIGTERM, _request_shutdown)

        try:
            session_ctx = session_manager.start_session(self._agent_id)
            session_id = session_ctx.session_id
            deps = replace(deps, session_id=session_id)

            if self._config.enable_key_moments:
                tool_funcs = (record_key_moment, restart_session, wait_session)
            else:
                tool_funcs = (restart_session, wait_session)

            if deps.pending_review_inbox is not None:
                tool_funcs = (*tool_funcs, resolve_pending_review)
            if deps.reflection_request_queue is not None:
                tool_funcs = (*tool_funcs, request_reflection)

            agent = Agent(
                self._config.model.model,
                deps_type=AtmanDeps,
                instructions=lambda ctx: build_instructions(ctx.deps),
                tools=tool_funcs,
            )

            # Build and inject the full memory bundle (identity + narrative + prev session)
            # into agent awareness. All automatically recalled content goes through
            # inject_memory() so delivery mode is consistent and configurable.
            prev_text = None
            recent_sessions = session_manager._state_store.list_recent_sessions(
                self._agent_id, limit=5
            )
            for prior_session in recent_sessions:
                if prior_session.id == session_id:
                    continue
                if (
                    prior_session.status in ("completed", "interrupted")
                    and prior_session.close_reason
                ):
                    prev_text = self._build_wake_up_message(prior_session)
                    break

            memory_bundle = build_memory_context(deps, prev_session_text=prev_text)
            pending_block = format_pending_reviews_block(deps.pending_review_inbox)
            if pending_block:
                memory_bundle = (
                    f"{pending_block}\n{memory_bundle}" if memory_bundle else pending_block
                )
            if memory_bundle:
                _LOG.info(
                    "Injecting memory bundle for session %s (mode=%s)",
                    session_id,
                    self._config.memory_injection_mode,
                )
                extra = inject_memory(
                    memory_bundle,
                    mode=self._config.memory_injection_mode,
                    history=history,
                    prepend=True,
                )
                if extra is not None:
                    deps = replace(deps, injected_context=extra)

            print_info("Session started. Empty line or Ctrl-D to exit.\n")
            timeout_seconds = self._config.session_timeout_minutes * 60
            # Snapshot the static context (identity + narrative) set at session start.
            # Per-turn RAG results are layered on top of this base each turn, never
            # accumulated, so injected_context stays bounded by rag_token_budget.
            _base_injected_context = deps.injected_context
            # Tracks the last RAG message appended to history (assistant_message /
            # user_message modes) so it can be removed before the next turn's injection.
            _last_rag_history_msg: object = None

            while True:
                print_prompt("You: ")
                try:
                    # Wait for input from queue with timeout
                    user_text = await asyncio.wait_for(
                        self._input_queue.get(), timeout=timeout_seconds
                    )
                except TimeoutError:
                    print_warn(
                        f"\n⏱️  Session timeout after {timeout_seconds / 60:.0f} minutes. Entering menu mode..."
                    )
                    # Enter menu mode
                    menu_result = await self._handle_menu_mode(
                        deps, session_manager, session_id, reflected_this_session
                    )
                    if menu_result == "exit":
                        break
                    elif menu_result == "reflected":
                        reflected_this_session = True
                    elif isinstance(menu_result, tuple) and menu_result[0] == "wait":
                        # Update timeout with new value from wait command
                        timeout_seconds = menu_result[1]
                    # Continue main loop after menu
                    continue

                # Check for EOF
                if user_text is None:
                    break

                if not user_text.strip():
                    break

                # Detect user language from their message (most recent wins)
                if len(user_text.strip()) >= 4:
                    user_language = "ru" if _is_mostly_cyrillic(user_text) else "en"

                # Surface relevant memories via RAG when PassiveMemoryInjector is wired.
                # build_rag_context caps the result to rag_token_budget tokens.
                _pmi = deps.passive_memory_injector
                if _pmi is not None:
                    from atman.core.services.passive_memory_injector import _surfaced_text

                    # Remove last turn's RAG message from history (assistant_message /
                    # user_message modes) before injecting fresh results, so only one
                    # turn's worth of RAG is present in the context at any time.
                    if _last_rag_history_msg is not None:
                        with contextlib.suppress(ValueError):
                            history.remove(_last_rag_history_msg)
                        _last_rag_history_msg = None

                    # Reset injected_context to base so the previous turn's RAG
                    # doesn't persist in system_prompt mode when the current turn
                    # finds zero relevant memories.
                    deps = replace(deps, injected_context=_base_injected_context)

                    _candidates = _pmi.surface_for_context(user_text, working_memory=working_memory)
                    _rag = build_rag_context(_candidates, budget=self._config.rag_token_budget)
                    _LOG.debug(
                        "RAG: items=%d tokens=%d session_cache=%s",
                        len(_rag.items),
                        _rag.tokens_used,
                        session_cache.stats(),
                    )
                    if _rag.items:
                        _rag_bundle = "\n".join(
                            f"[{m.source}] {_surfaced_text(m)}" for m in _rag.items
                        )
                        _history_len_before = len(history)
                        _rag_extra = inject_memory(
                            _rag_bundle,
                            mode=self._config.memory_injection_mode,
                            history=history,
                            prepend=False,
                        )
                        if _rag_extra is not None:
                            # system_prompt mode: combine base + current RAG.
                            _combined = (
                                f"{_base_injected_context}\n{_rag_extra}"
                                if _base_injected_context
                                else _rag_extra
                            )
                            deps = replace(deps, injected_context=_combined)
                        elif len(history) > _history_len_before:
                            # History-based modes: capture the appended message so
                            # we can remove it before the next turn's injection.
                            _last_rag_history_msg = history[-1]

                try:
                    result = await agent.run(
                        user_text,
                        deps=deps,
                        message_history=history or None,
                        model_settings=self._model_settings,
                    )
                except Exception as exc:
                    print_err(f"Run failed: {exc!s}")
                    continue

                # E22.5: Check for restart request (only in new messages to avoid infinite loop)
                restart_requested, restart_reason = _check_restart_requested(result.new_messages())

                if restart_requested:
                    _LOG.info("Restart requested by agent (reason: %s)", restart_reason or "(none)")
                    print_info(
                        f"\n[System] Restarting session... (reason: {restart_reason or 'agent request'})\n"
                    )

                    try:
                        # Update history with current run's messages before restart
                        # so tail_messages includes the exchange that triggered restart
                        history.extend(result.new_messages())

                        # Execute restart workflow
                        new_session_id, new_deps = self._do_restart(
                            session_manager,
                            session_id,
                            deps,
                            history,
                            restart_reason,
                            user_language=user_language,
                        )

                        # Update state for next iteration
                        session_id = new_session_id
                        deps = new_deps
                        reflected_this_session = False  # Reset for new session

                        # Rebuild base context for the new session so subsequent RAG
                        # injections are anchored to the restarted session's identity,
                        # not the original one (which may have been updated by reflection).
                        _new_memory_bundle = build_memory_context(deps)
                        if _new_memory_bundle:
                            _new_extra = inject_memory(
                                _new_memory_bundle,
                                mode=self._config.memory_injection_mode,
                                history=history,
                                prepend=False,
                            )
                            if _new_extra is not None:
                                deps = replace(deps, injected_context=_new_extra)
                        _base_injected_context = deps.injected_context
                        _last_rag_history_msg = None

                        working_memory.clear()
                        session_cache.entity_resolutions.clear()
                        session_cache.rag_results.clear()
                        session_cache.dirty_entities.clear()

                        print_info("Session restarted successfully.\n")
                        continue  # Skip output, continue loop with new session

                    except Exception as exc:
                        print_err(f"Restart failed: {exc!s}")
                        _LOG.exception("Failed to restart session %s", session_id)
                        break  # Exit loop on restart failure

                # E22.3: Token monitoring - check context usage and warn/force-close
                # Note: inline implementation matches token_monitor.py logic but is
                # integrated directly here for tight coupling with chat loop control flow
                usage = result.usage() if hasattr(result, "usage") else None
                if usage and usage.input_tokens:
                    context_limit = self._config.model.context_limit
                    input_tokens = usage.input_tokens

                    # Check token usage thresholds (extracted method for testability)
                    newly_triggered, should_force_close = self._check_token_usage(
                        input_tokens, context_limit
                    )

                    # Display agent's response FIRST (before warnings), so user sees
                    # the actual content before meta-information about session state
                    print_plain(str(result.output))
                    print_plain("")

                    # Display warnings for newly triggered thresholds
                    remaining = context_limit - input_tokens
                    if 70 in newly_triggered:
                        print_warn(
                            f"\n⚠️  Context 70% full ({input_tokens}/{context_limit} tokens). "
                            f"~{remaining} tokens remaining. "
                            f"When ready — call restart_session.\n"
                        )
                    if 80 in newly_triggered:
                        print_warn(
                            f"\n⚠️  Context 80% full ({input_tokens}/{context_limit} tokens). "
                            f"~{remaining} tokens remaining.\n"
                        )
                    if 90 in newly_triggered:
                        print_warn(
                            f"\n⚠️  Context 90% full ({input_tokens}/{context_limit} tokens). "
                            f"~{remaining} tokens remaining.\n"
                        )

                    # Handle force-close at 95%
                    if should_force_close:
                        _LOG.warning(
                            "Context 95%% full (%d/%d tokens) - forcing session close",
                            input_tokens,
                            context_limit,
                        )
                        print_warn(
                            f"\n⚠️  Context 95% full ({input_tokens}/{context_limit} tokens). "
                            "Forcing session close.\n"
                        )
                        try:
                            _force_finish(session_manager, session_id, "forced")
                        except Exception as exc:
                            _LOG.exception("Failed to force-finish session %s", session_id)
                            print_err(f"Force-finish failed: {exc!s}")
                        break  # Exit main loop
                else:
                    # No token usage info or no thresholds triggered - show response normally
                    print_plain(str(result.output))
                    print_plain("")

                # E22.5: Check for wait request (agent-triggered timeout adjustment)
                wait_requested, wait_minutes = _check_wait_requested(result.new_messages())

                if wait_requested and wait_minutes > 0:
                    timeout_seconds = wait_minutes * 60
                    _LOG.info("Wait requested by agent: %d minutes (timeout reset)", wait_minutes)
                    print_info(f"\n⏱️  Timer reset to {wait_minutes} minutes (agent request).\n")

                # Auto-record value-based refusals as key moments (silent, no agent nudging)
                with contextlib.suppress(Exception):
                    _auto_record_refusal_if_needed(
                        output=str(result.output or ""),
                        session_manager=session_manager,
                        session_id=session_id,
                    )

                # E22.5: Update history with new messages from this run
                history.extend(result.new_messages())
        except KeyboardInterrupt:
            print_warn("\nInterrupted.")
            # Track interruption for close_reason
            interrupted = True
        finally:
            if original_sigterm_handler is not None:
                signal.signal(signal.SIGTERM, original_sigterm_handler)
            self._stop_stdin_reader()
            # Release per-session caches to free memory
            working_memory.clear()
            session_cache.entity_resolutions.clear()
            session_cache.rag_results.clear()
            session_cache.dirty_entities.clear()
            if deps.passive_memory_injector is not None:
                with contextlib.suppress(Exception):
                    la = getattr(deps.passive_memory_injector, "_linguistic_analyzer", None)
                    if la is not None and hasattr(la, "clear_session_cache"):
                        la.clear_session_cache()
            if session_id is not None:
                # HLE-56 (Devin #594): drain pending AffectDetector tasks
                # while we're still on the event loop — the synchronous
                # drain inside ``finish_session`` short-circuits when
                # called on the loop thread (otherwise it deadlocks the
                # very loop the affect tasks need to make progress). This
                # is the path that actually catches late-firing affect
                # hooks scheduled by the final ``record_event``.
                with contextlib.suppress(Exception):
                    await session_manager.drain_pending_affect_tasks(session_id)
                # Defer any unhandled finish_session exception until after the
                # session-end skills marker has been attempted. The invocation
                # data the marker summarises is already durable in the store
                # before finish_session runs, so a finalize failure (DB error,
                # unexpected ValueError, etc.) shouldn't cost us the marker.
                deferred_finish_exc: BaseException | None = None
                try:
                    # Pass close_reason if session was interrupted
                    finish_kwargs = {
                        "session_id": session_id,
                        "overall_emotional_tone": 0.0,
                        "key_insight": "",
                        "alignment_check": True,
                        "alignment_notes": "",
                        "user_language": user_language,
                    }
                    if interrupted:
                        finish_kwargs["close_reason"] = "interrupted"

                    session_manager.finish_session(**finish_kwargs)
                except ValueError as exc:
                    if "Cannot finish session without key moments" in str(exc):
                        close_reason = "interrupted" if interrupted else None
                        try:
                            _force_finish(session_manager, session_id, close_reason)
                        except BaseException as force_exc:
                            deferred_finish_exc = force_exc
                    else:
                        deferred_finish_exc = exc
                except (SessionAlreadyFinishedError, SessionNotFoundError):
                    pass
                except BaseException as exc:
                    # Any other failure (DB error, RuntimeError, …) — defer so
                    # the marker still runs, then re-raise after.
                    deferred_finish_exc = exc

                # HLE-35: dump per-session skill activity to a JSON marker
                # next to the workspace. Best-effort — never re-raise; this
                # block runs regardless of finish_session outcome because the
                # invocation data is already in the store.
                if deps.skill_manager is not None:
                    try:
                        deps.skill_manager.write_session_skills_marker(
                            self._workspace, session_id, self._agent_id
                        )
                    except Exception:
                        _LOG.debug(
                            "write_session_skills_marker failed for session %s",
                            session_id,
                            exc_info=True,
                        )

                if deferred_finish_exc is not None:
                    raise deferred_finish_exc

    async def _handle_menu_mode(
        self,
        deps: AtmanDeps,
        session_manager: SessionManager,
        session_id: UUID,
        reflected_this_session: bool,
    ) -> str | tuple[str, int]:
        """
        Handle menu mode after timeout.

        Returns:
            "exit" to break main loop,
            "reflected" if reflection was performed,
            "continue" to resume with same timeout,
            ("wait", new_timeout_seconds) to resume with new timeout
        """
        from atman.term import print_info, print_plain, print_prompt, print_warn

        print_info("\n📋 Menu Mode - Available commands:")
        if not reflected_this_session:
            print_plain("  reflect - Run micro reflection on this session")
        print_plain("  wait <minutes> - Reset timer and continue")
        print_plain("  sleep - Close session and exit")
        print_plain("  save_to_memory <content> - Save to factual memory")
        if self._config.enable_free_time:
            print_plain("  free_time - Enter free time mode")
        print_plain("")

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            print_prompt("Menu> ")
            try:
                # Get input from queue (no timeout in menu mode)
                cmd_input = await self._input_queue.get()
            except Exception:
                return "exit"

            # Check for EOF
            if cmd_input is None:
                return "exit"

            cmd_parts = cmd_input.strip().split(maxsplit=1)
            if not cmd_parts:
                retry_count += 1
                print_warn(f"Empty command. {max_retries - retry_count} retries left.")
                continue

            cmd = cmd_parts[0].lower()
            arg = cmd_parts[1] if len(cmd_parts) > 1 else ""

            # Handle commands
            if cmd == "reflect":
                if reflected_this_session:
                    print_warn("Reflection already performed this session.")
                    retry_count += 1
                    continue

                try:
                    event = deps.micro_reflection.reflect(session_id, agent_id=deps.agent_id)
                    print_info(f"✓ Reflection completed: {event.key_insight}")
                    print_warn(
                        "Note: Reflection during active session may have limited data. "
                        "Full reflection occurs after session completion."
                    )
                    return "reflected"
                except Exception as exc:
                    print_warn(f"Reflection failed: {exc!s}")
                    retry_count += 1
                    continue

            elif cmd == "wait":
                if not arg:
                    print_warn("Usage: wait <minutes>")
                    retry_count += 1
                    continue
                try:
                    minutes = int(arg)
                    if minutes <= 0:
                        print_warn("Minutes must be positive")
                        retry_count += 1
                        continue
                    print_info(f"Timer reset for {minutes} minutes")
                    return ("wait", minutes * 60)
                except ValueError:
                    print_warn("Invalid minutes value")
                    retry_count += 1
                    continue

            elif cmd == "sleep":
                _force_finish(session_manager, session_id, "timeout_sleep")
                print_info("Session closed. Exiting...")
                return "exit"

            elif cmd == "save_to_memory":
                if not arg.strip():
                    print_warn("Usage: save_to_memory <content>")
                    retry_count += 1
                    continue
                if deps.passive_memory_injector is None:
                    print_warn("Memory not available (set ATMAN_LINGUISTIC_ENABLED=true to enable)")
                    retry_count += 1
                    continue
                from atman.core.models.fact import FactRecord

                fact = FactRecord(content=arg.strip(), source="user_command")
                try:
                    saved = deps.passive_memory_injector.factual_memory.add_fact(fact)
                    print_info(f"Saved to memory: {saved.id}")
                except Exception:
                    _LOG.warning("save_to_memory failed; continuing menu", exc_info=True)
                    print_warn("Failed to save to memory. See logs for details.")
                    retry_count += 1
                continue

            elif cmd == "free_time":
                if not self._config.enable_free_time:
                    print_warn("Free time mode is disabled in config")
                    retry_count += 1
                    continue

                print_info("Entering free time mode. Type 'end_free_time' to exit.")
                free_time_result = await self._handle_free_time_mode(deps, session_id)
                # After free_time, return to menu (not main loop)
                if free_time_result == "continue":
                    print_info("Exited free time mode. Returning to menu.")
                    continue  # Stay in menu loop
                return free_time_result  # "exit" case

            else:
                print_warn(f"Unknown command: {cmd}")
                retry_count += 1
                continue

        # Max retries reached
        print_warn(f"Max retries ({max_retries}) reached. Closing session.")
        _force_finish(session_manager, session_id, "menu_timeout")
        return "exit"

    async def _handle_free_time_mode(
        self,
        deps: AtmanDeps,
        session_id: UUID,
    ) -> str:
        """
        Handle free time mode - open-ended agent interaction.

        Returns:
            "continue" to return to menu/main loop, "exit" to close session
        """
        from atman.adapters.agent.instructions import build_instructions
        from atman.adapters.agent.tools import record_key_moment
        from atman.term import print_err, print_info, print_plain, print_prompt

        if self._config.enable_key_moments:
            tool_funcs = (record_key_moment,)
        else:
            tool_funcs = ()

        agent = Agent(
            self._config.model.model,
            deps_type=AtmanDeps,
            instructions=lambda ctx: build_instructions(ctx.deps),
            tools=tool_funcs,
        )

        print_info("Free time mode active. Agent can explore freely.")

        while True:
            print_prompt("Free> ")
            try:
                # Get input from queue (no timeout in free time mode)
                user_input = await self._input_queue.get()
            except Exception:
                return "exit"

            # Check for EOF
            if user_input is None:
                return "exit"

            if not user_input.strip():
                continue

            if user_input.strip().lower() == "end_free_time":
                # Return to menu, not main loop
                return "continue"

            try:
                result = await agent.run(user_input, deps=deps, model_settings=self._model_settings)
                print_plain(str(result.output))
                print_plain("")
            except Exception as exc:
                print_err(f"Free time run failed: {exc!s}")
                continue

    def _build_wake_up_message(self, prior: object) -> str | None:
        """Build wake-up message from the last closed Session (v2) or SessionExperience (legacy)."""
        from atman.core.models import SessionExperience
        from atman.core.models.session import Session

        if isinstance(prior, Session):
            close_reason = prior.close_reason
            lang = prior.user_language or "ru"
            reason = prior.restart_reason or ""
        elif isinstance(prior, SessionExperience):
            close_reason = prior.close_reason
            lang = getattr(prior, "user_language", None) or "ru"
            reason = getattr(prior, "restart_reason", None) or ""
        else:
            return None

        if not close_reason:
            return None

        if lang == "en":
            if close_reason == "timeout_sleep":
                return "You dozed off — the user stepped away, you chose to sleep."
            elif close_reason == "restart":
                r = reason or "not specified"
                return f"You initiated a restart. Reason: {r}"
            elif close_reason == "forced":
                return "Context limit was reached — the session was closed before you could finish consciously."
            elif close_reason == "interrupted":
                return "The session was interrupted by an external signal — you were not part of the closing."
            elif close_reason == "menu_timeout":
                return "The inactivity menu timed out — the session closed without you choosing an action."
        else:
            if close_reason == "timeout_sleep":
                return "Ты задремал — пользователь отошёл, ты решил поспать."
            elif close_reason == "restart":
                r = reason or "не указана"
                return f"Ты сам инициировал перезапуск. Причина: {r}"
            elif close_reason == "forced":
                return (
                    "Контекст переполнился принудительно — ты не успел завершить сессию осознанно."
                )
            elif close_reason == "interrupted":
                return "Сессия была прервана внешним сигналом — ты не участвовал в закрытии."
            elif close_reason == "menu_timeout":
                return "Меню бездействия истекло по таймауту — сессия закрылась без выбранного действия."

        return None


# ── Per-turn Atman pipeline (SDK entry-point) ─────────────────────────────────


class AtmanTurn:
    """Encapsulates the complete per-turn Atman pipeline for any host agent.

    Usage::

        turn = AtmanTurn(deps, sm, session_id)
        deps = turn.pre(user_text)   # entity reg + passive RAG + ambient injection
        result = await agent.run(user_text, deps=deps, ...)
        turn.post(result.output)     # response analysis + identity facts + maintenance

    All Atman pipeline output is injected into ``deps.injected_context``
    (which feeds the LLM system prompt via ``build_instructions``).  Nothing
    is inserted into visible chat messages — the agent is fully unaware of
    the Atman machinery.

    Pass ``on_event`` to receive structured pipeline events (e.g. for a live
    debug UI).  The callback has the same signature as ``session_log.slog``::

        on_event(event_name: str, **data)

    Pass ``session_log.slog`` directly to route events through the standard
    slog channel (and thus to any registered display hook).
    """

    def __init__(
        self,
        deps: AtmanDeps,
        sm: SessionManager,
        session_id: UUID | None,
        on_event: Any | None = None,
    ) -> None:
        self._deps = deps
        self._sm = sm
        self._session_id = session_id
        self._on_event = on_event
        # Populated by pre(); readable by UI for RAG display.
        self.passive_summary: str = ""
        self.ambient_summary: str = ""
        # Populated by post() when boundary auto key moment is written.
        self.auto_key_moment_written: bool = False
        self.auto_key_moment_markers: list[str] = []

    def _emit(self, event: str, **data: Any) -> None:
        if self._on_event is not None:
            with contextlib.suppress(Exception):
                self._on_event(event, **data)

    # ── Public API ────────────────────────────────────────────────────────────

    def pre(self, user_text: str) -> AtmanDeps:
        """Run pre-turn pipeline; returns updated deps with injected_context set."""
        from atman.adapters.observability.sentry import pipeline_span

        _LOG.debug("[AtmanTurn.pre] start  text=%r", user_text[:80])
        # Per-turn RAG only — never accumulate prior turns' injected_context.
        deps = replace(self._deps, injected_context=None)

        with pipeline_span("atman.ner", "entity detection"):
            deps = self._register_user_entities(user_text, deps)
        with pipeline_span("atman.rag.passive", "passive RAG injection"):
            deps = self._inject_passive_rag(user_text, deps)
        with pipeline_span("atman.rag.ambient", "ambient RAG"):
            deps = self._inject_ambient(user_text, deps)

        _LOG.debug(
            "[AtmanTurn.pre] done  injected_context_len=%d  passive=%r  ambient=%r",
            len(deps.injected_context or ""),
            self.passive_summary,
            self.ambient_summary,
        )
        self._deps = deps
        return deps

    def post(self, agent_text: str) -> None:
        """Run post-turn pipeline (entity reg, auto key moment, identity facts, maintenance)."""
        from atman.adapters.observability.sentry import pipeline_span

        _LOG.debug("[AtmanTurn.post] start  text=%r", agent_text[:80])
        self.auto_key_moment_written = False
        self.auto_key_moment_markers = []
        deps = self._deps

        with pipeline_span("atman.affect", "affect processing"):
            self._analyze_response(agent_text, deps)
            self._run_affect_and_refusal(agent_text)
        self._drain_maintenance(deps)

        _LOG.debug("[AtmanTurn.post] done")

    # ── Pre-turn steps ────────────────────────────────────────────────────────

    def _register_user_entities(self, text: str, deps: AtmanDeps) -> AtmanDeps:
        if deps.ambient_memory is None:
            _LOG.debug("[AtmanTurn] entity_reg skipped: no ambient_memory")
            return deps
        if deps.entity_registry is None:
            _LOG.debug("[AtmanTurn] entity_reg skipped: no entity_registry")
            return deps
        try:
            analysis = deps.ambient_memory._analyzer.analyze_user_message(text)
            entities = analysis.entities or []
            _LOG.debug(
                "[AtmanTurn] user entities detected: n=%d  entities=%r",
                len(entities),
                [_S(e.text) for e in entities[:5]],
            )
            self._emit(
                "entity_resolved",
                entities=[
                    {
                        "text": _S(e.text),
                        "type": getattr(e.entity_type, "value", str(e.entity_type)),
                    }
                    for e in entities
                ],
            )
            for entity in entities:
                if len(entity.text) < 2:
                    continue
                try:
                    deps.entity_registry.resolve_or_create(
                        deps.agent_id,
                        _S(entity.text),
                        entity.entity_type,
                    )
                    _LOG.debug(
                        "[AtmanTurn] entity registered: text=%r type=%s",
                        _S(entity.text),
                        getattr(entity.entity_type, "value", str(entity.entity_type)),
                    )
                except Exception as exc:
                    _LOG.warning(
                        "[AtmanTurn] entity_registry.resolve_or_create failed: %s  entity=%r",
                        exc,
                        _S(entity.text),
                    )
        except Exception as exc:
            _LOG.warning("[AtmanTurn] user entity analysis failed: %s", exc)
        return deps

    def _inject_passive_rag(self, text: str, deps: AtmanDeps) -> AtmanDeps:
        if deps.passive_memory_injector is None:
            _LOG.debug("[AtmanTurn] passive_rag skipped: no passive_memory_injector")
            self.passive_summary = "no injector"
            return deps
        try:
            from atman.core.services.passive_memory_injector import build_rag_context

            items = deps.passive_memory_injector.surface_for_context(text)
            _LOG.debug("[AtmanTurn] passive surface_for_context: n_items=%d", len(items))
            if not items:
                self.passive_summary = "0 items"
                return deps

            rag = build_rag_context(items, budget=1500)
            _LOG.debug(
                "[AtmanTurn] passive rag built: n=%d  tokens_used=%d",
                len(rag.items),
                rag.tokens_used,
            )
            if not rag.items:
                self.passive_summary = "0 rag items"
                return deps

            lines = []
            for item in rag.items:
                payload = item.item
                text_frag = (
                    getattr(payload, "content", None)
                    or getattr(payload, "what_happened", None)
                    or str(payload)[:120]
                )
                lines.append(f"- [{item.source}] {_S(str(text_frag))[:150]}")
                _LOG.debug(
                    "[AtmanTurn] passive item: kind=%s  score=%.3f  text=%r",
                    item.source,
                    item.score,
                    _S(str(text_frag))[:60],
                )

            ctx_str = "## Из памяти (релевантное)\n" + "\n".join(lines)
            self.passive_summary = f"{len(rag.items)} items, {rag.tokens_used} tok"
            _LOG.info(
                "[AtmanTurn] passive_rag injected: n=%d  tokens=%d",
                len(rag.items),
                rag.tokens_used,
            )
            self._emit(
                "passive_rag",
                items_total=len(rag.items),
                tokens_used=rag.tokens_used,
                items=[{"kind": it.source, "score": round(it.score, 3)} for it in rag.items[:5]],
            )

            existing = deps.injected_context or ""
            merged = (existing + "\n" + ctx_str).strip() if existing else ctx_str
            return replace(deps, injected_context=merged)
        except Exception as exc:
            _LOG.warning("[AtmanTurn] passive_rag failed: %s", exc, exc_info=True)
            self.passive_summary = f"error: {exc}"
            return deps

    def _inject_ambient(self, text: str, deps: AtmanDeps) -> AtmanDeps:
        if deps.ambient_memory is None:
            _LOG.debug("[AtmanTurn] ambient_rag skipped: no ambient_memory")
            self.ambient_summary = "no ambient_memory"
            return deps
        try:
            result = deps.ambient_memory.compose_injection(text, agent_id=deps.agent_id)
            items = result.items
            _LOG.debug(
                "[AtmanTurn] ambient compose_injection: n=%d  tokens=%d",
                len(items),
                result.tokens_used,
            )
            if not items:
                self.ambient_summary = f"0 items, {result.tokens_used} tok"
                return deps

            lines = []
            for it in items:
                p = it.payload
                if it.kind == "stance":
                    txt = getattr(p, "stance_text", "") or ""
                elif it.kind == "moment":
                    txt = getattr(p, "what_happened", "") or ""
                else:
                    txt = getattr(p, "content", "") or ""
                lines.append(f"[{it.kind}] {it.anchor_text or ''}: {_S(str(txt))[:100]}")
                _LOG.debug(
                    "[AtmanTurn] ambient item: kind=%s  anchor=%r  score=%.3f  text=%r",
                    it.kind,
                    it.anchor_text or "",
                    getattr(it, "score", 0.0),
                    _S(str(txt))[:60],
                )

            ambient_str = "\n".join(lines)
            self.ambient_summary = f"{len(items)} items, {result.tokens_used} tok"
            _LOG.info(
                "[AtmanTurn] ambient_rag injected: n=%d  tokens=%d",
                len(items),
                result.tokens_used,
            )
            self._emit(
                "ambient_injection",
                items_total=len(items),
                tokens_used=result.tokens_used,
                items=[
                    {
                        "kind": it.kind,
                        "anchor": it.anchor_text or "",
                        "score": round(getattr(it, "score", 0.0), 3),
                    }
                    for it in items[:5]
                ],
            )

            existing = deps.injected_context or ""
            merged = (existing + "\n" + ambient_str).strip() if existing else ambient_str
            return replace(deps, injected_context=merged)
        except Exception as exc:
            _LOG.warning("[AtmanTurn] ambient_rag failed: %s", exc, exc_info=True)
            self.ambient_summary = f"error: {exc}"
            return deps

    # ── Post-turn steps ───────────────────────────────────────────────────────

    def _run_affect_and_refusal(self, agent_text: str) -> None:
        """Passive affect scoring + silent value-refusal key moments (parity with session_tester)."""
        if self._session_id is None:
            return
        with contextlib.suppress(Exception):
            _auto_record_refusal_if_needed(
                output=agent_text,
                session_manager=self._sm,
                session_id=self._session_id,
            )
        import re

        clean = re.sub(r"<think>.*?</think>", "", agent_text, flags=re.DOTALL).strip()
        if not clean:
            return
        from atman.core.models.session import SessionEvent

        event = SessionEvent(
            session_id=self._session_id,
            event_type="agent_response",
            description=clean,
        )
        try:
            self._sm.record_event(self._session_id, event)
            self._emit("affect_scheduled", session_id=str(self._session_id))
        except Exception as exc:
            _LOG.warning("[AtmanTurn] record_event for affect failed: %s", exc)

    def _analyze_response(self, text: str, deps: AtmanDeps) -> None:
        if deps.ambient_memory is None:
            _LOG.debug("[AtmanTurn] response analysis skipped: no ambient_memory")
            return
        try:
            analysis = deps.ambient_memory._analyzer.analyze_agent_message(text)
        except Exception as exc:
            _LOG.warning("[AtmanTurn] analyze_agent_message failed: %s", exc, exc_info=True)
            return

        _LOG.info(
            "[AtmanTurn] agent analysis: stance=%r  cognitive_mode=%r  primary_emotion=%r"
            "  cognitive_load=%r  boundary_markers=%r  divergence=%r  entities=%d  spans=%d",
            analysis.stance,
            analysis.cognitive_mode,
            analysis.primary_emotion,
            analysis.cognitive_load_label,
            analysis.boundary_markers,
            analysis.divergence_signals,
            len(analysis.message_entities),
            len(analysis.message_spans),
        )
        self._emit(
            "agent_analysis",
            stance=analysis.stance,
            cognitive_mode=analysis.cognitive_mode,
            primary_emotion=analysis.primary_emotion,
            cognitive_load_label=analysis.cognitive_load_label,
            boundary_markers=analysis.boundary_markers,
            divergence=analysis.divergence_signals,
            entities=[_S(e.text) for e in analysis.message_entities],
            spans=[{"text": _S(s.text)[:20], "label": s.label} for s in analysis.message_spans[:5]],
        )

        # 1. Register entities from agent response
        if deps.entity_registry is not None:
            for ent in analysis.message_entities:
                if len(ent.text) < 2:
                    continue
                try:
                    deps.entity_registry.resolve_or_create(
                        deps.agent_id,
                        _S(ent.text),
                        ent.entity_type,
                    )
                    _LOG.debug(
                        "[AtmanTurn] agent entity registered: text=%r type=%s",
                        _S(ent.text),
                        getattr(ent.entity_type, "value", str(ent.entity_type)),
                    )
                except Exception as exc:
                    _LOG.warning(
                        "[AtmanTurn] agent entity_registry failed: %s  entity=%r",
                        exc,
                        _S(ent.text),
                    )

        if analysis.message_spans:
            _LOG.debug(
                "[AtmanTurn] point-A spans: %r",
                [{"text": _S(s.text)[:20], "label": s.label} for s in analysis.message_spans[:5]],
            )

        # 2. Auto-record key moment on boundary event with full structured_markers
        if analysis.boundary_markers and self._session_id is not None:
            _LOG.info(
                "[AtmanTurn] boundary event: markers=%r",
                analysis.boundary_markers,
            )
            try:
                from atman.core.models.session import KeyMomentInput

                markers_str = ", ".join(analysis.boundary_markers[:3])
                kmi = KeyMomentInput(
                    what_happened=_S(text[:300]),
                    why_it_matters=f"Boundary event detected: {markers_str}",
                    emotional_valence=0.0,
                    emotional_intensity=0.0,
                    depth=EmotionalDepth.SURFACE,
                    incomplete_coloring=True,
                )
                moment = kmi.to_key_moment()
                a_markers: dict[str, Any] = {
                    "a": {
                        "stance": analysis.stance,
                        "cognitive_mode": analysis.cognitive_mode,
                        "self_orientation": analysis.self_orientation,
                        "primary_emotion": analysis.primary_emotion,
                        "cognitive_load_label": analysis.cognitive_load_label,
                        "boundary_markers": analysis.boundary_markers,
                        "divergence_signals": analysis.divergence_signals,
                        "spans": [
                            {"text": _S(s.text), "label": s.label} for s in analysis.message_spans
                        ],
                    }
                }
                moment.structured_markers = a_markers
                moment.structured_markers_version = "2.0"
                self._sm.append_key_moment(self._session_id, moment)
                _LOG.info(
                    "[AtmanTurn] auto key moment written: markers=%r  a=%r",
                    analysis.boundary_markers,
                    a_markers["a"],
                )
                self._emit(
                    "key_moment_appended",
                    what_happened=_S(text[:100]),
                    markers=analysis.boundary_markers,
                    stance=analysis.stance,
                    primary_emotion=analysis.primary_emotion,
                )
                self.auto_key_moment_written = True
                self.auto_key_moment_markers = list(analysis.boundary_markers)
            except Exception as exc:
                _LOG.warning("[AtmanTurn] auto key moment failed: %s", exc, exc_info=True)

        # 3. Write identity facts when agent self-describes
        if analysis.boundary_markers and deps.passive_memory_injector is not None:
            self._write_identity_facts(text, analysis, deps)

    def _write_identity_facts(self, text: str, analysis: object, deps: AtmanDeps) -> None:
        try:
            factual_memory = deps.passive_memory_injector.factual_memory  # type: ignore[union-attr]
        except AttributeError:
            _LOG.debug("[AtmanTurn] identity facts skipped: no factual_memory on injector")
            return
        if factual_memory is None:
            return

        from atman.core.models.fact import FactRecord

        identity_markers = {
            "я принимаю",
            "я выбираю",
            "моё имя",
            "меня зовут",
            "я решила",
            "я решил",
        }
        marker_text = " ".join(getattr(analysis, "boundary_markers", [])).lower()
        if not any(m in marker_text for m in identity_markers):
            _LOG.debug(
                "[AtmanTurn] identity facts skipped: no identity boundary marker in %r",
                marker_text[:80],
            )
            return

        person_entities = [
            _S(e.text)
            for e in getattr(analysis, "message_entities", [])
            if getattr(e.entity_type, "value", str(e.entity_type)) == "person" and len(e.text) >= 2
        ]
        _LOG.debug("[AtmanTurn] identity facts: person_entities=%r", person_entities)

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
                _LOG.info("[AtmanTurn] identity fact written: %r", record.content)
            except Exception as exc:
                _LOG.warning("[AtmanTurn] identity fact failed: %s  name=%r", exc, name)

        try:
            record = FactRecord(
                agent_id=deps.agent_id,
                content=_S(f"Агент о себе: {text[:200]}"),
                source="agent_boundary_event",
                tags=["identity", "self_description"],
            )
            factual_memory.add_fact(record)
            facts_written += 1
            _LOG.info("[AtmanTurn] identity self-desc fact: %r", record.content[:80])
        except Exception as exc:
            _LOG.warning("[AtmanTurn] identity self-desc fact failed: %s", exc)

        _LOG.info("[AtmanTurn] identity facts written: %d total", facts_written)
        if facts_written:
            self._emit("identity_facts_written", count=facts_written)

    def _drain_maintenance(self, deps: AtmanDeps) -> None:
        if deps.maintenance_worker is None:
            _LOG.debug("[AtmanTurn] maintenance skipped: no maintenance_worker")
            return
        try:
            done = deps.maintenance_worker.run_once(batch_size=10)
            _LOG.info("[AtmanTurn] maintenance drained: %d job(s)", done)
            if done:
                self._emit("maintenance_drained", jobs_done=done)
        except Exception as exc:
            _LOG.warning("[AtmanTurn] maintenance drain failed: %s", exc)
