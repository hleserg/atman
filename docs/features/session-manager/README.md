# Session Manager

> **Russian:** [README-ru.md](README-ru.md)

## What It Does

Session Manager is the runtime that lives inside an active conversation. It tracks what is happening moment-to-moment — events, key moments, emotional state — and produces a structured record when the session closes. The session is experienced in real time, not reconstructed retrospectively.

## Key Concepts

**`SessionContext`** — the initial configuration of a session: agent ID, session ID, metadata about the context (user, platform, etc.).

**`SessionEvent`** — a single recorded event within a session. Can be a user message, agent response, tool call, internal observation, or any other notable occurrence.

**`KeyMomentInput`** — the input schema for capturing a key moment during a session. Contains description, optional `FeltSense`, and salience score.

**`SessionResult`** — the output of a completed session: summary, list of key moments, eigenstate, and timestamps.

**`ActiveSessionSummary`** — a lightweight read model of a currently-running session (for dashboards and monitoring).

**`Session`** — the full persistent record of a session, combining context, events, result, and metadata.

**`AffectPort` hook** — an optional async hook called on every `record_event()` call. Used by the affect detector to update the agent's affective state in response to what is happening.

**`PostWriteScheduler`** — optional component that queues maintenance jobs (micro/daily reflection, salience decay) after the session writes its result. Decouples session close from background processing.

**Crash recovery** — when journal-based recovery is enabled, `SessionManager` writes a durable event log during the session. If the process crashes before `finish_session` completes, the session can be reconstructed from the journal on next startup.

## Public API

```python
class SessionManager:
    async def start_session(self, context: SessionContext) -> Session: ...
    async def record_event(self, session_id: str, event: SessionEvent) -> None: ...
    async def append_key_moment(self, session_id: str, input: KeyMomentInput) -> KeyMoment: ...
    async def finish_session(self, session_id: str) -> SessionResult: ...
    async def get_active_summary(self, session_id: str) -> ActiveSessionSummary | None: ...
```

`finish_session` produces an `Eigenstate` — a snapshot of the agent's cognitive and affective state at session end — which is persisted alongside the session result and feeds the next session's context.

## Configuration

Session Manager is assembled by `factory.py`. Optional components are enabled via environment:

```bash
# Enable skill manager integration
ATMAN_SKILLS_ENABLED=1

# Enable GLiNER+MiniLM affect detection
ATMAN_LINGUISTIC_ENABLED=1

# Session log for debugging
ATMAN_SESSION_LOG=~/.atman/session.log
```

## Example Usage

```bash
make demo-session
```

Programmatic usage:

```python
context = SessionContext(agent_id="agent-001", session_id="sess-42")
session = await session_manager.start_session(context)

# During conversation
await session_manager.record_event(session.session_id, SessionEvent(
    type="user_message",
    content="I've been struggling with this for weeks.",
))

# Agent decides this is significant
await session_manager.append_key_moment(session.session_id, KeyMomentInput(
    description="User disclosed prolonged struggle — high emotional weight.",
    salience=0.9,
))

# End of conversation
result = await session_manager.finish_session(session.session_id)
print(result.eigenstate)
```
