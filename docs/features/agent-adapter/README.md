# Agent Adapter

**Status:** shipped runtime surface (E26+)
**Purpose:** Pydantic AI wrapper that lets an LLM agent run through Atman's session, memory, reflection, affect, and skill services.

[[ru](README-ru.md)] — *Russian version*

---

## Overview

The agent adapter (`src/atman/adapters/agent/`) is the LLM-facing composition
layer for Atman. It does not own domain state itself. Instead, it wires existing
Core services and ports into a runnable agent loop:

```text
agent input -> AtmanTurn.pre -> pydantic-ai Agent.run -> AtmanTurn.post
```

There are two supported integration paths:

- **Interactive REPL:** `src/run_agent.py` creates or loads an agent from the
  agent registry, builds `AtmanRunner`, and starts a full chat session.
- **Embedded host:** `AtmanTurn` exposes the per-turn pre/post pipeline for
  Streamlit, session tester, or another host that owns the outer chat loop.

For the full architecture flow, see `docs/architecture/SYSTEM.md`. For
operator-level health checks around embedded runs, see
`docs/development/SESSION_TESTER_RUNBOOK.md`.

---

## Module Map

| Module | Public surface | Role |
|--------|----------------|------|
| `config.py` | `ModelConfig`, `AgentConfig` | Runtime limits and model settings: model string, output/context limits, narrative truncation, RAG budget, memory injection mode, prompt caching flag. |
| `deps.py` | `AtmanDeps`, `AtmanDeps.from_config(...)` | Frozen DI container for `SessionManager`, `IdentityService`, `MicroReflectionService`, `StateStore`, runtime IDs, and optional ports such as skill manager, reflection queue, memory guardian, ambient memory, and maintenance worker. |
| `factory.py` | `build_deps(...)`, reflection service builders | Composition root. Wires storage, affect, divergence, post-write scheduler, memory guardian, passive/ambient RAG, skills, maintenance, and reflection services. |
| `runner.py` | `AtmanRunner`, `AtmanTurn` | Full REPL runner plus host-embeddable per-turn pipeline. Handles session start/finish, restart/wait sentinels, memory injection, post-turn affect/refusal analysis, and maintenance drain. |
| `instructions.py` | `build_instructions(...)`, `build_memory_context(...)`, `build_skill_suggestions_section(...)` | Separates stable behavioral rules from personal memory. Memory enters through `inject_memory()` unless `memory_injection_mode="system_prompt"`. |
| `memory_injection.py` | `inject_memory(...)`, `MemoryInjectionMode` | Places recalled context as an assistant message, user message, or system-prompt extension. |
| `tools.py` | `record_key_moment`, `log_experience`, `restart_session`, `wait_session`, `resolve_pending_review`, `request_reflection` | Pydantic AI tool callbacks and runner sentinels. |
| `preflight.py` | `run_cli_preflight(...)`, `run_streamlit_preflight(...)` | Readiness checks for local model, PostgreSQL, and NLP dependencies. |

Import note: `atman.adapters.agent.__all__` exports the config, dependency,
instruction, token monitor, and basic tool symbols. Import `AtmanRunner`,
`AtmanTurn`, and `build_deps` from their submodules.

---

## Quick Start: REPL

`src/run_agent.py` uses `AgentsRegistry`, so the REPL path requires
`DATABASE_URL` (or `.env` with `DATABASE_URL`) even though lower-level
`build_deps(...)` can fall back to file storage for zero-DB test/dev wiring.

```bash
# List registered agents.
uv run src/run_agent.py --list

# Create a registered agent and workspace under ~/.atman/agents/<serial_id>/.
uv run src/run_agent.py --new "research assistant"

# Resume agent #1 with an explicit Pydantic AI model string.
uv run src/run_agent.py --agent 1 --model ollama:qwen3.5:9b
```

The default workspace root is `~/.atman/agents`. Override it with
`--workspace-root` when testing against disposable local state.

---

## Embedded Path: `AtmanTurn`

Use `AtmanTurn` when another application owns the chat loop but still wants the
Atman lifecycle around every model turn:

```python
turn = AtmanTurn(deps, session_manager, session_id)
deps_for_run = turn.pre(user_text)
result = await agent.run(user_text, deps=deps_for_run, message_history=history)
turn.post(result.output)
```

`AtmanTurn.pre(...)` performs entity registration, passive RAG, ambient RAG, and
skill suggestion injection. `AtmanTurn.post(...)` records the assistant response,
runs affect/refusal hooks, may auto-record key moments for boundary markers, and
drains maintenance work when a worker is wired.

---

## Agent Tools

| Tool | Backend behavior | Availability |
|------|------------------|--------------|
| `record_key_moment` | Validates emotional values and sends an `AgentMemoryReport` to `AffectDetector.submit_self_report(...)`. It returns error strings instead of raising so the LLM can self-correct. | Requires an active session and an affect detector on `SessionManager`. |
| `log_experience` | Deprecated redirect. It tells the agent to use `record_key_moment`; session-level `Experience` is persisted when the session finishes. | Always safe as a migration shim. |
| `restart_session` | Returns a `__ATMAN_RESTART_REQUESTED__` sentinel. `AtmanRunner` owns the actual restart lifecycle. | REPL runner path. |
| `wait_session` | Returns a `__ATMAN_WAIT_REQUESTED__<minutes>` sentinel. `AtmanRunner` owns the actual wait loop. | REPL runner path. |
| `resolve_pending_review` | Resolves an item in `PendingHumanReviewInbox`. | Registered only when `AtmanDeps.pending_review_inbox` is present. |
| `request_reflection` | Enqueues a `ReflectionRequest` using an idempotent hourly run key. | Registered only when `AtmanDeps.reflection_request_queue` is present. |

Constraint: `record_key_moment` no longer writes through
`SessionManager.record_key_moment`; that legacy method intentionally raises. The
supported path is affect self-reporting, documented in
`docs/features/affect-detector/README.md`.

---

## Configuration

| Setting | Where | Effect |
|---------|-------|--------|
| `DATABASE_URL` / `ATMAN_DB_URL` | environment | Enables Postgres-backed state when the registered agent exists in `public.agents`; otherwise `factory.py` falls back to file storage. `src/run_agent.py` requires `DATABASE_URL` for `AgentsRegistry`. |
| `ATMAN_LINGUISTIC_ENABLED=true` | environment | Enables the real linguistic/RAG path when optional dependencies are installed. Otherwise the factory uses no-op analyzers and keeps the session path alive. |
| `ATMAN_SKILLS_ENABLED` | environment | Overrides settings-level skill-loop enablement. Falsy values (`false`, `0`, `no`, `off`) disable skill wiring. |
| `ATMAN_LLM_BASE_URL`, `ATMAN_LLM_MODEL`, `ATMAN_LLM_API_KEY` | environment | Enable a real OpenAI-compatible reflection model for narrative/reflection wiring; otherwise mock reflection models keep dev/test runs local. |
| `ATMAN_SESSION_LOG`, `ATMAN_SESSION_LOG_FILE` | environment | Controls JSONL session debug logging. Enabled by default unless set to `0`, `false`, `no`, or `off`. |
| `ATMAN_OBS_LEVEL` | environment | Controls observability level (`off`, `minimal`, `debug`, `verbose`). See `docs/features/observability/levels.md`. |
| `AgentConfig.memory_injection_mode` | code/config | Chooses `assistant_message` (default), `user_message`, or `system_prompt` memory delivery. |
| `AgentConfig.rag_token_budget` | code/config | Caps per-request RAG context using the repository's token heuristic. |
| `AgentConfig.max_tool_calls` | code/config | Validated and carried in `AtmanDeps`; dispatch enforcement is still pending. |

---

## Known Constraints

- There is no `make demo-agent` target yet. Use `uv run src/run_agent.py ...`.
- `enable_experience_search` exists in `AgentConfig`, but no direct experience
  search tool is currently exposed.
- `max_tool_calls` is validated but not yet enforced by the runner dispatch loop.
- Postgres-backed REPL runs require the agent registry. Lower-level factory tests
  can still use file/in-memory fallbacks without external services.
- Optional NLP, skill, reflection, and observability subsystems degrade to no-op or
  in-memory implementations when their dependencies or env flags are absent.

---

## Testing

Focused adapter checks:

```bash
pytest tests/test_agent_config.py tests/test_instructions.py tests/test_tools.py \
       tests/test_runner.py tests/test_atman_turn.py tests/test_skill_factory_wiring.py -v
```

Docs-only edits should at least run:

```bash
git diff --check
```

For code changes in this area, run the full repository quality gate:

```bash
make check
```
