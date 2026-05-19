# Design — Atman Living Codemap

> **Type:** Design document  
> **Status:** Review  
> **Owner:** Sergey Khlebnikov  
> **Date:** 2026-05-19  
> **Location:** `docs/design/DESIGN_living_codemap.md`  
> **Related:** `docs/design/DESIGN_docs_structure.md`

---

## 1. Problem

Agents complete tasks and file reports. The reports are optimistic. The code is honest.

There is no automated system that reads the actual source tree and answers:
- Which components exist right now and what public classes do they expose?
- What external services must be running for Atman to start?
- What changed since the last PR?
- What is in the code but missing from the docs?

`SYSTEM_MAP.md` exists as a standard (§26 DEVELOPMENT_STANDARD.md) but it is maintained by agents who have already proven they don't maintain it reliably. The map drifts. Agents reading a stale map make confident wrong assumptions. Sergey reviews PRs that "fixed" things that aren't broken and skipped things that are.

**Goal:** The code describes itself. No human or agent writes `SYSTEM_MAP.md` by hand. Every push regenerates ground truth automatically.

---

## 2. Generated Artifacts

Six output files, all committed to `docs/architecture/codemap/`:

```
docs/architecture/codemap/
  SYSTEM_MAP.md          ← per-component module/class/port inventory
  STARTUP_DEPS.md        ← what must be running for Atman to start
  TEST_ENV.md            ← current test environment description
  ENDPOINTS.md           ← generated replacement for the manual one
  DELTA_REPORT.md        ← what changed since previous codemap run
  UNDOCUMENTED.md        ← things in code that have no doc counterpart
```

All six are regenerated on every push. The CI job fails if the committed versions are stale (i.e., someone pushed without running the generator). Git diff is the audit trail.

---

## 3. SYSTEM_MAP.md — Component-by-Component Inventory

### 3.1 Why per-component matters

Most tasks in Atman touch exactly one component. An agent working on Reflection Engine does not need to know the Skill Loop's internals. A flat list of 200 classes is noise. A per-component map is a focused scope that an agent can read at the start of a task and act on.

### 3.2 Component detection

Components are detected by directory name under `src/atman/`. The mapping is declared in a config file (not hardcoded in the script) so it can be extended without touching the generator:

```yaml
# scripts/codemap/components.yaml
components:
  factual-memory:
    path: src/atman/factual_memory
    display: "Factual Memory"
  experience-store:
    path: src/atman/experience
    display: "Experience Store"
  identity-store:
    path: src/atman/identity
    display: "Identity Store"
  reflection-engine:
    path: src/atman/reflection
    display: "Reflection Engine"
  session-manager:
    path: src/atman/session
    display: "Session Manager"
  reality-anchor:
    path: src/atman/reality
    display: "Reality Anchor"
  proactive-engine:
    path: src/atman/proactive
    display: "Proactive Engine"
  skill-loop:
    path: src/atman/skill
    display: "Skill Loop"
  eval:
    path: src/atman/eval
    display: "Eval (isolated namespace)"
  core-ports:
    path: src/atman/core/ports
    display: "Core / Ports"
  core-services:
    path: src/atman/core/services
    display: "Core / Services"
  adapters:
    path: src/atman/adapters
    display: "Adapters"
  infra:
    path: src/atman/infra
    display: "Infrastructure"
```

### 3.3 What is extracted per component

For each component, the generator uses Python's `ast` module to extract:

| Extracted item | Source |
|----------------|--------|
| Public classes | `ast.ClassDef` without leading `_` |
| Public functions at module level | `ast.FunctionDef` without leading `_` |
| Ports (Protocol subclasses) | `ast.ClassDef` with `Protocol` in bases |
| Adapters | Classes in `src/atman/adapters/` |
| Port↔Adapter wiring | Classes that implement a Protocol (structural check via `ast`) |
| CLI commands | Decorated with `@app.command()` or `@click.command()` |
| Pydantic models | Classes inheriting `BaseModel` |
| `schema_version` constants | Module-level `SCHEMA_VERSION = ...` assignments |
| TODOs and FIXMEs | Comments matching `# TODO` / `# FIXME` pattern |

### 3.4 Port/Adapter coverage matrix

An additional table at the top of `SYSTEM_MAP.md` shows which ports have real implementations vs only stubs:

```markdown
| Port | Real Adapter | Fake/Stub | Status |
|------|-------------|-----------|--------|
| `FactualMemory` | `FileFactualMemory`, `PostgresFactualMemory` | `InMemoryFactualMemory` | ✅ |
| `EmbeddingModel` | `BGEEmbeddingModel` | `FakeEmbeddingModel` | ✅ |
| `ReflectionModel` | `OpenAIReflectionModel`, `AnthropicReflectionModel` | `FakeReflectionModel` | ✅ |
| `SomeFuturePort` | *(none)* | `FakeSomeFuture` | ⚠️ no real impl |
```

This tells both Sergey and agents: if there's no real adapter, the feature is not production-ready regardless of what the PR description says.

### 3.5 Test coverage per component

A heatmap row per component:

```markdown
| Component | Test files | Test count | Coverage (lines) | Status |
|-----------|------------|------------|-----------------|--------|
| Factual Memory | 3 | 41 | 87% | ✅ |
| Experience Store | 2 | 28 | 74% | 🟡 |
| Reality Anchor | 0 | 0 | 0% | 🔴 not tested |
```

Generated by running `pytest --collect-only -q` (no execution) for counts and `coverage report` for percentages. Coverage run is skipped if `--no-coverage` flag is passed (fast mode for local checks).

---

## 3b. Relationship to the Existing `docs/architecture/SYSTEM_MAP.md`

The project already has a `SYSTEM_MAP.md` (674 lines, tracked in CI). It is richer than what any AST generator would produce alone. Before deciding what to generate, it is important to understand what that file actually contains — and what drifts.

### 3b.1 Anatomy of the existing file

| Section | Content type | Drifts without maintenance? |
|---------|-------------|----------------------------|
| §1 Modules — file/class/port tables | Code inventory | **Yes — this is the drift zone** |
| §2 Integrations — service↔port wiring | Partially inferable from code | **Partially** |
| §3 Scenarios A–G | Human-authored test coverage plan | No (human intent, not code fact) |
| §4 Edge cases / GAPs | Human analysis | No |
| §5 Regressions / TODOs | Partially inferable from test run results | **Partially** |
| §6 Architecture summary / component status | Partially inferable | **Partially** |
| §7–8 Work order / maintenance rules | Guidelines | No |

**Replacing the whole file with auto-generation would destroy §3–§5**, which contain genuine test planning knowledge that cannot be recovered from source code alone. Those sections describe *intent* (what scenarios should exist, what edge cases are known), not *facts* (what code exists).

### 3b.2 Strategy: selective replacement via markers

The generator does **not** rewrite the whole file. Instead, it updates only the sections that drift, identified by HTML comment markers embedded in the document:

```markdown
<!-- codemap:auto:start section="modules-domain-models" -->
| File | Purpose | Public classes |
|------|---------|----------------|
| `core/models/fact.py` | ... | `FactRecord`, `Relation` |
<!-- codemap:auto:end -->
```

On each run, the generator:
1. Reads the existing `SYSTEM_MAP.md`
2. Finds all `<!-- codemap:auto:start ... -->` / `<!-- codemap:auto:end -->` blocks
3. Replaces their content with freshly-extracted data from the AST
4. Leaves everything outside markers untouched
5. Writes the file back in-place

This means CI updating `SYSTEM_MAP.md` produces a small, reviewable diff — only the rows that actually changed in code.

### 3b.3 Which sections get markers

| SYSTEM_MAP.md section | Marker name | Generator fills from |
|-----------------------|-------------|---------------------|
| §1.1 Domain models table | `modules-domain-models` | AST: `core/models/` |
| §1.2 Ports table | `modules-ports` | AST: `core/ports/` |
| §1.3 Services table | `modules-services` | AST: `core/services/` |
| §1.4 Adapters table | `modules-adapters` | AST: `adapters/` |
| §1.5 CLI commands | `modules-cli` | AST: click decorators |
| §1.6 TUI tabs | `modules-tui` | AST: Textual decorators |
| Port/Adapter matrix (new, top of §1) | `port-adapter-matrix` | AST: Protocol + implementors |
| §6 Component status list | `arch-component-status` | `components.yaml` + AST: existence check |
| §5.4 TODO/FIXME count | `todos` | AST: comment scan |

Sections **without** markers: §2 Integrations narrative, §3 Scenarios, §4 Edge cases, §5 Regressions, §7 Work order, §8 Rules. These are human territory.

### 3b.4 Stale-marker detection

The generator also validates human-maintained sections against code reality — but only warns, does not rewrite:

- **§2 Integrations:** checks that every file path mentioned in the table actually exists. Reports `⚠️ dead path: src/atman/adapters/old_adapter.py` in `UNDOCUMENTED.md` if a path is missing.
- **§3 Scenarios:** checks that test file paths referenced in the right column exist. Missing paths go to `UNDOCUMENTED.md`.
- **§5 Regressions:** checks that referenced test functions (`test_file.py::test_name`) exist in the test suite. Missing references surface in `UNDOCUMENTED.md`.

This way human-written sections don't silently rot either — they just get a different treatment than auto-replaced sections.

### 3b.5 Migration plan for the existing file

1. Add `<!-- codemap:auto:start ... -->` markers to each §1 subsection and §6 component status — one PR, no content change.
2. Run `make codemap` locally — generator fills markers for the first time, diff shows if the current content matches reality or has already drifted.
3. Review drift findings, correct by hand anything that is substantively wrong (not just formatting).
4. From that point on, CI updates §1 automatically and flags dead paths in human sections.

The migration PR touches every §1 table but changes nothing structurally. Reviewable in under 10 minutes.

---

## 4. STARTUP_DEPS.md — What Atman Needs to Start

This file answers the question: "What must be running and configured for Atman to launch at all?" It is the operational dependency list, not the code architecture.

### 4.1 Sources parsed

| Source file | What is extracted |
|-------------|-------------------|
| `docker-compose.yml` | Container services (Postgres, Qdrant, open-webui) with ports |
| `pyproject.toml` → `[project.dependencies]` | Python runtime dependencies (non-eval) |
| `pyproject.toml` → `[project.optional-dependencies]` | Eval deps (marked as optional) |
| All `*.py` imports of known external packages | Cohere, Anthropic SDK, sentry_sdk, llama_cpp, httpx |
| `.env.example` or config dataclass fields | Required environment variables |
| `src/atman/infra/config.py` | Typed config fields flagged as required |

### 4.2 External systems categories

```markdown
## Required — Atman will not start without these

### Infrastructure
| Service | Version | Port | Purpose |
|---------|---------|------|---------|
| PostgreSQL + pgvector | 16.x | 5432 | Fact store, reflection history, schema state |
| Qdrant | 1.x | 6333 | Vector search for experience retrieval |

### LLM Runtime (one of)
| Service | Endpoint | Purpose |
|---------|---------|---------|
| llama.cpp lazy proxy | localhost:8081 | Local LLM (Gemma4, DeepSeek-R1) |
| Anthropic API | api.anthropic.com | Cloud LLM fallback |

### Required Environment Variables
| Variable | Used by | Example |
|----------|---------|---------|
| `POSTGRES_URL` | StateStore adapter | postgresql://atman:***@localhost:5432/atman |
| `QDRANT_URL` | Vector adapter | http://localhost:6333 |
| `ATMAN_LLM_BASE_URL` | OpenAIReflectionModel | http://localhost:8081/v1 |
| `ATMAN_LLM_MODEL` | OpenAIReflectionModel | gemma4 |
| ... | ... | ... |

## Optional — Degraded mode without these

| Service | Purpose | Degraded behavior |
|---------|---------|-------------------|
| Sentry (`SENTRY_DSN`) | Error tracking | Errors logged locally only |
| Cohere API | Reranking | Falls back to similarity score |
| BGE-M3 local | Local embeddings | Falls back to cloud embedding |

## NLP Models
| Model | Type | Loaded by | Required for |
|-------|------|-----------|-------------|
| Gemma 4 26B (GGUF) | Generative | llama-server | Reflection, micro/daily/deep |
| DeepSeek-R1-14B (GGUF) | Generative (reasoning) | llama-server | Alternative planner |
| BAAI/bge-m3 | Embedding | local Python | Fact/experience retrieval |
| BAAI/bge-reranker-v2-m3 | Reranker | local Python | Two-stage retrieval |
```

### 4.3 How env vars are detected

The generator scans for:
- `os.environ.get("VAR_NAME")` and `os.environ["VAR_NAME"]` patterns in all `*.py`
- Pydantic `model_config` with `env` prefix or `Field(alias=...)`
- Dataclass fields decorated with env-loading helpers
- `.env.example` keys

Result is a deduplicated table with which module uses each variable. Unset required vars are flagged as `🔴 MISSING` in the generated output.

---

## 5. TEST_ENV.md — Live Test Environment Guide

`TEST_ENV.md` is not a static config snapshot. It is a practical field guide: how to interact with a running Atman agent, how to observe what it does in real time, how to trigger specific behaviors, and how to inspect what ended up in memory. It should be the first file an engineer opens when they want to know "is this actually working?"

The generator populates the infrastructure table and LLM stack from detected config. The rest of the sections are semi-static templates updated when the interaction surface changes (new CLI commands, new monitoring hooks, new memory inspection queries). CI detects staleness via hash comparison like the other files.

---

### 5.1 Runtime Stack Table (auto-generated)

```markdown
# Atman Test Environment

Generated: 2026-05-19 14:32 UTC | Git: a1b2c3d | Branch: main

## LLM Stack

| Layer | Implementation | Endpoint | Notes |
|-------|---------------|---------|-------|
| Atman Reflection Model | `OpenAIReflectionModel` | http://localhost:8081/v1 | Default adapter |
| LLM backend | Gemma 4 26B UD-Q4_K_XL (GGUF) | llama-server :8080 | Via lazy proxy |
| Lazy proxy | `llama_lazy_proxy.py` | :8081 → :8080 | Auto-shutdown after idle |
| Alternative LLM | DeepSeek-R1-14B Q4_K_M | same proxy, model switch | Switch via ATMAN_LLM_MODEL |
| Anthropic fallback | `AnthropicReflectionModel` | api.anthropic.com | Set ANTHROPIC_API_KEY |
| Test agent LLM | Gemma 4 26B (same) | http://localhost:8080/v1 | Pydantic AI agent direct |
| Embedding (local) | BAAI/bge-m3 | Python in-process | 8192-token context |
| Reranker (local) | BAAI/bge-reranker-v2-m3 | Python in-process | Two-stage retrieval |

## Infrastructure

| Service | Container | Port | Status |
|---------|-----------|------|--------|
| PostgreSQL + pgvector | atman-postgres | 5432 | {status} |
| Qdrant | atman-qdrant | 6333 (HTTP), 6334 (gRPC) | {status} |
| OpenWebUI | open-webui | 3000 | {status} |

{status} = populated from last successful CI health check, not live.
```

---

### 5.2 Live Interaction — CLI

The primary way to have a real conversation with the agent without any UI overhead.

```markdown
## Live Interaction — CLI

### Start a live session (Pydantic AI agent as test user → Atman)
```bash
# Full interactive session — agent talks to Atman, you watch
python -m agent.atman_agent --interactive

# Single-turn probe (useful for quick sanity checks)
python -m agent.atman_agent --message "Что ты помнишь о нашем последнем разговоре?"

# With verbose LLM tracing — shows raw prompts and completions
ATMAN_LOG_LEVEL=DEBUG python -m agent.atman_agent --interactive 2>&1 | tee /tmp/session.log
```

### Run a predefined demo session (deterministic, no LLM needed)
```bash
make demo-session-fast    # instant output, no pacing
make demo-session         # paced output, human-readable
make demo-experience-fast
make demo-reflection-fast
make demo-identity-fast
```

### Trigger individual components from CLI
```bash
# Record a key moment manually
atman-experience add --session-id <uuid> \
  --what "User challenged agent's opinion" \
  --felt-valence -0.3 --felt-intensity 0.8 --felt-depth meaningful \
  --why "Values boundary was tested"

# Trigger micro reflection on last session
python -m atman.session.scheduler micro --dry-run   # shows what would happen
python -m atman.session.scheduler micro             # actually runs it

# Trigger daily / deep reflection
python -m atman.session.scheduler daily
python -m atman.session.scheduler deep

# Force identity snapshot
python -m atman.identity snapshot --force --note "manual snapshot before experiment"
```
```

---

### 5.3 Live Interaction — WebUI

```markdown
## Live Interaction — WebUI (OpenWebUI)

OpenWebUI provides a chat interface backed by the llama.cpp server (Gemma 4 or DeepSeek-R1).
This is a raw LLM conversation — it does NOT go through the Atman session pipeline by default.
Use it to probe model behavior independently of Atman's memory stack.

| URL | Access |
|-----|--------|
| WSL local | http://172.31.192.143:3000 |
| Windows localhost | http://localhost:3000 (after port forward) |
| LAN | http://<Windows_IP>:3000 |

### Connecting WebUI to Atman session pipeline (if integrated)
If an HTTP integration adapter is wired up, point OpenWebUI's custom model URL to
the Atman session entrypoint instead of the bare llama-server. This makes WebUI
conversations flow through Session Manager → Experience Store → reflection cycle.
Status: document here when that integration is implemented.

### Useful model switches in WebUI
- Switch to Gemma 4 for generation
- Switch to DeepSeek-R1 for reasoning-heavy tasks
- Both served through same llama-server (one at a time, lazy-loaded)
```

---

### 5.4 Monitoring — Watching Events in Real Time

```markdown
## Monitoring — Real-Time Event Observation

### 1. Log tailing (simplest)
```bash
# All Atman logs, DEBUG level
ATMAN_LOG_LEVEL=DEBUG python -m agent.atman_agent --interactive 2>&1 | tee /tmp/atman_live.log

# Watch in separate terminal
tail -f /tmp/atman_live.log | grep -E "(KEY_MOMENT|REFLECTION|SESSION|FACT|ERROR)"
```

### 2. Postgres event stream (SQL-level monitoring)
```bash
# Watch new key moments as they are written (poll every 2s)
watch -n 2 'psql -U atman -d atman -c \
  "SELECT created_at, session_id, what_happened, emotional_depth
   FROM key_moments ORDER BY created_at DESC LIMIT 5;"'

# Watch divergence events (Reality Anchor signals)
watch -n 5 'psql -U atman -d atman -c \
  "SELECT created_at, divergence_type, severity, description
   FROM divergence_events ORDER BY created_at DESC LIMIT 10;"'

# Watch reflection jobs as they run
watch -n 10 'psql -U atman -d atman -c \
  "SELECT started_at, job_type, status, notes
   FROM maintenance_jobs ORDER BY started_at DESC LIMIT 5;"'
```

### 3. Postgres LISTEN/NOTIFY (event-driven, no polling)
If the session pipeline publishes NOTIFY on key tables, a monitoring script can subscribe:
```bash
# Subscriber script (run in background terminal)
python scripts/monitor/pg_listener.py --channel atman_events --verbose
```
This pattern is documented here as a target; implement the NOTIFY hooks when Session Manager is wired to Postgres.

### 4. Datadog LLM Observability (when configured)
Tracks prompt/response latency, tool-call counts, memory read/write frequency, session completion.
```bash
# Verify Datadog tracing is active
DATADOG_SITE=datadoghq.com DD_SERVICE=atman DD_ENV=dev \
  python -m agent.atman_agent --message "test" 2>&1 | grep -i datadog

# Required env vars for Datadog
DATADOG_API_KEY=<from Bitwarden>
DD_ENV=dev
DD_SERVICE=atman
DD_VERSION=$(git rev-parse --short HEAD)
```
Dashboard: traces appear at https://app.datadoghq.com/apm/traces filtered by service=atman.
See: `docs/architecture/DATADOG-LLM-OBSERVABILITY.md`

### 5. llama-server request log
```bash
# See every prompt that hits the LLM (raw)
curl http://localhost:8080/metrics          # if metrics endpoint exposed
tail -f ~/.atman/llama_proxy.log           # proxy-level log
```
```

---

### 5.5 Session Scenario Runs

```markdown
## Session Scenario Runs on Live Agent

These runs exercise the full pipeline (Session Manager → Experience Store → Reflection)
with real LLM calls and real storage. They are slower than unit tests but prove the
system actually works end-to-end.

### Predefined scenarios (deterministic fixtures, no LLM)
```bash
# Runs lifecycle A–G from SYSTEM_MAP §3 (subprocess, real CLI, real FileStateStore)
uv run pytest tests/test_e2e_full_cli.py -v

# Same scenarios but against real Postgres + Qdrant (requires services up)
uv run pytest tests/test_e2e_full_cli.py -v -m integration
```

### Live agent scenarios (real LLM, real storage)
```bash
# Scenario: full session lifecycle (start → events → key moments → finish → micro reflection)
python -m e2e.full_loop --workspace /tmp/atman-e2e-$(date +%s)

# Scenario: multi-session day (3 sessions → daily reflection)
python -m e2e.day_loop --sessions 3 --workspace /tmp/atman-day

# Scenario: week loop (7 days → deep reflection)
python -m e2e.week_loop --workspace /tmp/atman-week
```

### What to look for after a scenario run
1. Check key moments were recorded: see §5.6 Memory Inspection → Key Moments
2. Check reflection ran: `maintenance_jobs` table, status = completed
3. Check narrative was updated: `cat <workspace>/NARRATIVE.md`
4. Check identity snapshot was created: see §5.6 → Identity
5. Check no ERROR lines in logs: `grep ERROR /tmp/atman-e2e-*/session.log`

### Running the Pydantic AI agent as synthetic test user
The agent in `agent/atman_agent.py` is infrastructure tooling — it simulates a user
talking to Atman, using Gemma 4 as its own LLM. It points to localhost:8080/v1 directly.

```bash
# One full synthetic conversation (20 turns)
python -m agent.atman_agent --scenario fixtures/scenarios/typical_workday.json

# Adversarial scenario (tests Reality Anchor)
python -m agent.atman_agent --scenario fixtures/scenarios/identity_pressure.json

# Custom prompt chain from file
python -m agent.atman_agent --prompts fixtures/prompts/boundary_test.txt
```
```

---

### 5.6 Memory Inspection — Looking Inside the Agent

```markdown
## Memory Inspection — What Is Actually in the Agent's Memory

### Key Moments (Experience Store)
```bash
# Last 10 key moments across all sessions
atman-experience search --limit 10

# Key moments from a specific session
atman-experience get --session-id <uuid>

# Key moments with high emotional intensity (> 0.7)
psql -U atman -d atman -c \
  "SELECT when_moment, what_happened, emotional_intensity, emotional_depth, values_touched
   FROM key_moments
   WHERE emotional_intensity > 0.7
   ORDER BY when_moment DESC LIMIT 20;"

# Salience decay preview (see what is fading from memory)
atman-experience decay-preview --agent-id <uuid>
```

### Facts (Factual Memory)
```bash
# All active facts about a subject
python -m atman.cli fact list --subject <entity_name>

# Fact timeline for a subject+predicate pair (bitemporal history)
python -m atman.cli fact timeline --subject <entity> --predicate <predicate>

# Facts pending clarification
psql -U atman -d atman -c \
  "SELECT subject_raw, predicate, status, created_at
   FROM pending_clarifications
   WHERE status = 'pending'
   ORDER BY created_at DESC;"
```

### Identity State
```bash
# Current identity (human-readable)
python -m atman.identity show --agent-id <uuid>

# Current narrative (the letter the agent writes to itself)
cat <workspace>/NARRATIVE.md

# Identity snapshot history
python -m atman.identity snapshots --agent-id <uuid> --limit 5

# Eigenstate of last session
psql -U atman -d atman -c \
  "SELECT created_at, emotional_baseline, agency_level, cognitive_load, growth_indicator
   FROM eigenstates ORDER BY created_at DESC LIMIT 1;"
```

### Reflection History
```bash
# Recent reflection runs
psql -U atman -d atman -c \
  "SELECT started_at, reflection_type, status, findings_count
   FROM reflection_runs ORDER BY started_at DESC LIMIT 10;"

# Patterns discovered by reflection
psql -U atman -d atman -c \
  "SELECT discovered_at, pattern_type, description, confidence
   FROM patterns WHERE status = 'active' ORDER BY confidence DESC;"

# Entity stances (how agent feels about known entities)
psql -U atman -d atman -c \
  "SELECT e.canonical_name, s.stance_text, s.valence, s.intensity, s.is_provisional
   FROM entity_stance s JOIN entities e ON s.entity_id = e.id
   WHERE s.superseded_at IS NULL ORDER BY s.formed_at DESC LIMIT 10;"
```

### Qdrant Vector Collections (semantic memory)
```bash
# Count vectors in each collection
curl -s -H "api-key: $QDRANT_API_KEY" \
  http://localhost:6333/collections | python -m json.tool | grep -A2 "vectors_count"

# Search experience collection by semantic query
python scripts/memory_inspector/qdrant_search.py \
  --collection atman_experiences \
  --query "moments where I felt my boundaries were tested" \
  --limit 5
```

### Audit Trail
```bash
# Recent audit events (who changed what in memory)
psql -U atman -d atman -c \
  "SELECT occurred_at, event_type, entity_type, entity_id, actor, reason
   FROM audit_events ORDER BY occurred_at DESC LIMIT 20;"

# Changes to identity specifically
psql -U atman -d atman -c \
  "SELECT occurred_at, event_type, before_value, after_value
   FROM audit_events WHERE entity_type = 'identity' ORDER BY occurred_at DESC LIMIT 10;"
```

### Schema Version Check
```bash
# Verify all components are on expected schema versions
psql -U atman -d atman -c \
  "SELECT component, schema_version, migrated_at
   FROM schema_versions ORDER BY component;"

# Check eval schema separately (isolated namespace)
psql -U atman -d atman -c "SELECT * FROM eval.schema_version;"
```

### Full Memory Export (for offline analysis)
```bash
# Export all agent memory to JSON (for inspection, not for import)
python -m atman.cli export --agent-id <uuid> --output /tmp/atman-export-$(date +%s).json

# Export specific component
python -m atman.cli export --agent-id <uuid> --component identity --output /tmp/identity.json
```
```

---

### 5.7 Automated Tests Without External Services

```markdown
## Running Tests Without Live Infrastructure

### Unit tests only (no Postgres, no Qdrant, no LLM)
```bash
uv run pytest tests/ -m "not integration" -v
```

### With fake adapters explicitly
```bash
uv run pytest tests/ \
  --fake-llm \
  --fake-store \
  --fake-embedding \
  -v
```

### Seven contract tests (run before every commit)
```bash
uv run pytest \
  tests/test_state_store_contract.py \
  tests/test_serialization_roundtrip.py \
  tests/test_cli_roundtrip.py \
  tests/test_domain_invariants.py \
  tests/test_golden_schema.py \
  tests/test_cli_all_commands.py \
  tests/test_e2e_full_cli.py \
  -v
```

### Integration tests (require Postgres + Qdrant running)
```bash
# Start infrastructure first
docker compose up -d

# Run integration suite
uv run pytest tests/ -m integration -v
```

### Benchmark / eval tests (require full stack + LLM)
```bash
# Single benchmark
uv run python scripts/eval/g1_identity.py --run-id $(uuidgen)

# Full eval suite (slow, ~30 min)
make eval-all
```
```

---

### 5.8 What the Generator Auto-Detects vs What Is Static

| Section | Auto-generated | Updated when |
|---------|---------------|-------------|
| LLM Stack table | ✅ from config.py + env | Config class changes |
| Infrastructure table | ✅ from docker-compose.yml | Services added/removed |
| Status column | ✅ from last CI health check | Every CI run |
| CLI command list | ✅ from AST (click decorators) | New command added |
| SQL inspection queries | ❌ static template | Schema migration lands |
| Datadog section | ❌ static template | Integration wired up |
| Scenario file paths | ❌ static template | New scenario added |
| Make targets list | ✅ from Makefile parsing | Makefile changes |

Static sections are updated by the engineer (or agent) when the relevant feature lands. The generator flags these sections as stale if the CLI command list or make targets they reference no longer exist.

---

## 6. ENDPOINTS.md — Auto-generated API Reference

The existing `ENDPOINTS.md` is written by hand and will drift. The generator replaces it.

Sources:
- FastAPI/Flask route decorators → HTTP endpoints with methods and path params
- Click `@app.command()` decorators → CLI commands with option signatures
- Docker Compose → infrastructure ports
- `llama_lazy_proxy.py` → proxy endpoint docs

Format matches the current manual `ENDPOINTS.md` so existing links don't break.

---

## 7. DELTA_REPORT.md — What Changed Since Last Run

The generator stores a snapshot hash per component after each successful run. On the next run, it computes the diff.

### 7.1 What counts as a change

| Change type | Detected how |
|-------------|-------------|
| New public class | Class name in current AST but not in previous snapshot |
| Deleted class | Opposite |
| Renamed class | Deleted + added in same component |
| New port defined | New Protocol subclass |
| Port got a new real adapter | New adapter class implementing a known port |
| New CLI command | New `@app.command()` decorated function |
| New required env var | New `os.environ["VAR"]` in any module |
| TODO count changed | Delta in TODO/FIXME counts per component |
| Test count changed | pytest collect diff |

### 7.2 Output format

```markdown
# Delta Report — 2026-05-19 14:32 UTC
Previous snapshot: 2026-05-18 09:11 UTC (commit a0f1c2b)
Current: commit a1b2c3d

## Added
- [reflection-engine] New class: `EntityStanceFormulator`
- [skill-loop] New port: `SkillInvocationStore`
- [infra] New required env var: `CHRONOS_MODEL_PATH`

## Removed
- [adapters] Class deleted: `OllamaReflectionModel` (was in adapters/llm/)

## Changed
- [experience-store] `ExperienceRepository` → `SessionRepository` (port renamed)
- [session-manager] Test count: 28 → 31 (+3)
- [reality-anchor] Coverage: 0% → 34% (still 🔴 below threshold)

## No changes
factual-memory, identity-store, proactive-engine, infra (rest)
```

---

## 8. UNDOCUMENTED.md — What Exists in Code but Not in Docs

Surfaces things agents created and either forgot to document or documented somewhere obscure.

### 8.1 Checks performed

| Check | How |
|-------|-----|
| Public class not mentioned in any `docs/` file | String search of class name across `docs/**/*.md` |
| CLI command not in ENDPOINTS.md | Compare generated CLI list vs current ENDPOINTS.md |
| Port with no adapter | Port coverage matrix |
| Module with no corresponding `docs/features/` entry | Check `docs/features/` subdirectory existence per component |
| Env var used in code but not in `.env.example` | Compare extracted vars vs `.env.example` keys |
| Migration file with no corresponding ADR | `migrations/versions/*.sql` not referenced in `docs/architecture/` |
| TODO count above threshold | Per component, flag if `> 5` open TODOs |

### 8.2 This is not blocking — it is visibility

`UNDOCUMENTED.md` does not fail the CI build (by default). It is informational. Sergey reads it to decide what needs attention. The threshold for build failure can be configured per-check:

```yaml
# scripts/codemap/thresholds.yaml
undocumented:
  fail_on_undocumented_port: true      # port with zero adapters = fail
  fail_on_missing_env_example: true    # env var not in .env.example = fail
  fail_on_todo_count: 10               # fail if any component has > 10 TODOs
  fail_on_missing_docs_feature: false  # warn only
```

---

## 9. Architecture — How It Works

### 9.1 Script structure

```
scripts/codemap/
  __main__.py          ← entry point: `python -m scripts.codemap`
  components.yaml      ← component → path mapping (editable without code change)
  thresholds.yaml      ← what triggers a build failure
  
  extractor/
    ast_walker.py      ← Python AST extraction (classes, ports, CLI, models)
    import_scanner.py  ← detects external package usage per module
    env_scanner.py     ← finds os.environ references + config field annotations
    docker_parser.py   ← parses docker-compose.yml for services and ports
    pyproject_parser.py← parses pyproject.toml for deps + optional deps
    
  snapshot/
    store.py           ← saves/loads component snapshots (JSON, stored in .codemap/)
    diff.py            ← computes delta between two snapshots
    en_hashes.json     ← per-marker EN hash + needs_translation flag (bilingual)
    
  renderer/
    system_map.py      ← renders SYSTEM_MAP.md (selective marker replacement)
    startup_deps.py    ← renders STARTUP_DEPS.md
    test_env.py        ← renders TEST_ENV.md
    endpoints.py       ← renders ENDPOINTS.md
    delta.py           ← renders DELTA_REPORT.md
    undocumented.py    ← renders UNDOCUMENTED.md (misplaced files + gaps)
    i18n.py            ← translation dict for static headers/column names
    
  coverage/
    runner.py          ← thin wrapper: calls pytest --collect-only and coverage
    
  agent_instructions.py  ← updates AGENTS.md, .cursor/rules, CLAUDE.md markers
  classifier.py          ← doc file classification + misplacement detection
  content_check.py       ← quality gate before docs/content/ sync
```

### 9.2 Dependency on external tools

| Tool | Purpose | Required? |
|------|---------|-----------|
| Python `ast` stdlib | Parse source files | Always |
| `pytest --collect-only` | Count tests per component | Yes (pytest already in dev deps) |
| `coverage run` + `coverage report` | Line coverage | Optional (`--no-coverage` flag) |
| `git log` / `git diff` | Snapshot comparison | Yes (git available in CI) |
| `pyyaml` | Read `components.yaml` | Yes (add to dev deps if not present) |

No tree-sitter, no heavy dependencies. The generator must be installable with `pip install -e ".[dev]"` and runnable without the full Atman stack (no Postgres, no Qdrant needed).

### 9.3 Snapshot storage

Snapshots are stored in `.codemap/` at the repo root (gitignored). Each snapshot is a JSON file keyed by component name with extracted metadata and a hash. The hash is compared on next run to determine if re-rendering is needed.

If `.codemap/` doesn't exist (first run, fresh clone), the generator runs in full mode and creates the directory.

---

## 10. CI/CD Integration — Three Workflows

Three separate workflows with different triggers and different scopes. Each is independent; none blocks the others from running.

```
Trigger          Workflow              Scope
─────────────────────────────────────────────────────────────────────
Every push/PR  → codemap.yml         EN codemap + EN README markers
Weekly cron    → translate.yml       RU translations of all EN files
Weekly cron    → sync-content.yml    docs/content/ → GitHub Pages copy
```

---

### 10.1 Workflow: `codemap.yml` — runs on every push/PR

Updates EN files only. Fast (< 90s). Must pass for a PR to merge.

```yaml
# .github/workflows/codemap.yml
name: Living Codemap (EN)

on:
  push:
    branches: ["**"]
  pull_request:

jobs:
  codemap:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2   # need HEAD~1 for delta

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11.9"

      - name: Install
        run: pip install -e ".[dev]"

      - name: Update codemap EN files (in-place marker replacement)
        run: python -m scripts.codemap --no-coverage --lang en

      - name: Update README.md auto-sections (in-place marker replacement)
        run: python -m scripts.codemap readme --lang en

      - name: Flag stale RU markers
        # Marks <!-- codemap:auto:start ... lang="ru" --> blocks as needs-translation
        # if their EN counterpart changed. Does NOT update RU content.
        run: python -m scripts.codemap flag-stale-ru

      - name: Fail if EN files have uncommitted changes
        run: |
          git diff --exit-code \
            docs/architecture/SYSTEM_MAP.md \
            docs/architecture/codemap/ \
            README.md \
            || (echo "::error::Run 'make codemap' locally and commit." && exit 1)

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: codemap-en
          path: |
            docs/architecture/codemap/
            docs/architecture/SYSTEM_MAP.md
            README.md
```

**What "fail if uncommitted changes" means in practice:**

An agent that modifies `src/atman/core/ports/` must also run `make codemap` before committing. If it doesn't, CI fails with a clear message. The agent can't slip in a new port without the map updating.

---

### 10.2 Workflow: `translate.yml` — weekly scheduled, also manually triggerable

Updates all RU files. Uses an LLM (Claude Sonnet via Anthropic API, key in repo secrets). Commits directly to the branch that triggered it (main by default). Runs after `codemap.yml` has already updated the EN source.

```yaml
# .github/workflows/translate.yml
name: Bilingual Translation (RU)

on:
  schedule:
    - cron: "0 3 * * 1"   # Every Monday 03:00 UTC
  workflow_dispatch:        # Manual trigger from GitHub UI

jobs:
  translate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11.9"

      - name: Install
        run: pip install -e ".[dev]"

      - name: Translate all stale RU markers
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          python -m scripts.codemap translate \
            --lang ru \
            --model claude-sonnet-4-20250514 \
            --only-stale    # only blocks flagged needs-translation

      - name: Commit and push if changed
        run: |
          git config user.name  "atman-bot"
          git config user.email "bot@atmanai.dev"
          git diff --quiet || (
            git add -A
            git commit -m "chore(i18n): auto-translate RU docs [skip ci]"
            git push
          )
```

The `[skip ci]` in the commit message prevents an infinite loop — the translation commit does not re-trigger `codemap.yml`.

---

### 10.3 Workflow: `sync-content.yml` — weekly scheduled, also manually triggerable

Copies the canonical files (README, MANIFEST, SYSTEM.md, SYSTEM_MAP.md, codemap files) and their RU twins to `docs/content/` for GitHub Pages rendering. Runs *after* `translate.yml` has updated the RU versions.

```yaml
# .github/workflows/sync-content.yml
name: Sync docs/content (GitHub Pages)

on:
  schedule:
    - cron: "0 5 * * 1"   # Every Monday 05:00 UTC (2h after translate)
  workflow_dispatch:

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Copy files to docs/content/
        run: make sync-site-content

      - name: Commit and push if changed
        run: |
          git config user.name  "atman-bot"
          git config user.email "bot@atmanai.dev"
          git diff --quiet || (
            git add docs/content/
            git commit -m "chore(site): sync content to docs/content/ [skip ci]"
            git push
          )
```

`make sync-site-content` already exists (per DEVELOPMENT_STANDARD.md). The workflow just automates running it on a schedule instead of requiring a human to remember.

---

### 10.4 Makefile targets (full set)

```makefile
.PHONY: codemap codemap-full codemap-check codemap-readme translate sync-site-content install-hooks

# ── Fast EN-only (use before committing) ──────────────────────────
codemap:
	python -m scripts.codemap --no-coverage --lang en
	python -m scripts.codemap readme --lang en

# ── Full EN with coverage (before release) ────────────────────────
codemap-full:
	python -m scripts.codemap --lang en
	python -m scripts.codemap readme --lang en

# ── CI check mode (exits non-zero if EN files are stale) ──────────
codemap-check:
	python -m scripts.codemap --no-coverage --lang en --check
	python -m scripts.codemap readme --lang en --check

# ── Translate RU (requires ANTHROPIC_API_KEY) ─────────────────────
translate:
	python -m scripts.codemap translate --lang ru --only-stale

translate-force:
	python -m scripts.codemap translate --lang ru

# ── Copy to docs/content/ (GitHub Pages) ─────────────────────────
sync-site-content:
	@echo "Syncing docs/content/..."
	cp README.md            docs/content/README.md
	cp README-ru.md         docs/content/README-ru.md
	cp MANIFEST.md          docs/content/MANIFEST.md
	cp MANIFEST-ru.md       docs/content/MANIFEST-ru.md
	cp docs/architecture/SYSTEM.md     docs/content/SYSTEM.md
	cp docs/architecture/SYSTEM-ru.md  docs/content/SYSTEM-ru.md
	cp docs/architecture/SYSTEM_MAP.md    docs/content/SYSTEM_MAP.md
	cp docs/architecture/SYSTEM_MAP-ru.md docs/content/SYSTEM_MAP-ru.md
	@echo "Done."

# ── Optional pre-commit hook ──────────────────────────────────────
install-hooks:
	echo '#!/bin/sh\nmake codemap\ngit add docs/architecture/ README.md' \
	  > .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

---

### 10.5 Weekly schedule — Monday pipeline

The three workflows run in sequence on Mondays:

```
03:00 UTC  translate.yml     — LLM translates stale RU sections
05:00 UTC  sync-content.yml  — copies updated EN+RU to docs/content/
```

`codemap.yml` runs separately on every push. The Monday batch ensures Russian docs and GitHub Pages stay current even during weeks with no pushes.

Manual override: both `translate.yml` and `sync-content.yml` have `workflow_dispatch` — triggerable from GitHub UI without waiting for Monday.

---

## 11. Import Graph — Actual vs Documented Dependencies

An additional output (rendered as a Mermaid diagram section inside `SYSTEM_MAP.md`) showing which components actually import from which other components.

This catches:

- `adapters/` importing from `core/services/` (port inversion violation)
- `eval/` importing from `core/` production code (isolation violation — `import-linter` catches this too, but the map makes it visual)
- Circular dependencies that shouldn't exist

Generated by walking all `import` and `from X import` statements per component directory and grouping by component.

---

## 11b. File Classification and Structure Enforcement

The codemap script includes a documentation structure enforcer (`scripts/codemap/classifier.py`). It runs on every push as part of `codemap.yml` and appends results to `UNDOCUMENTED.md`.

Full structure specification and classification rules: `docs/design/DESIGN_docs_structure.md`.

### 11b.1 What it scans

Every `.md` file in the repo is checked against the canonical structure defined in `DESIGN_docs_structure.md §2`. The classifier uses a decision tree (filename patterns → content front-matter → heuristics) to determine where a file should live.

```python
# scripts/codemap/classifier.py

RULES = [
    # Pattern-based (filename only, fast)
    Rule(pattern=r"^DESIGN_.*\.md$|.*-design\.md$|.*-system-design\.md$",
         target="docs/design/", confidence="HIGH"),
    Rule(pattern=r"^ADR-\d{3}-.*\.md$",
         target="docs/architecture/ADR/", confidence="HIGH"),
    Rule(pattern=r"^\d{2}-[a-z][a-z0-9-]+\.md$",   # 01-factual-memory-adapter.md
         target="docs/development/work-packages/", confidence="HIGH"),
    Rule(pattern=r"УСТАНОВКА|INSTALL.*GUIDE|SETUP.*GUIDE|GETTING.*STARTED",
         target="docs/ops/", confidence="HIGH", flags=re.IGNORECASE),
    Rule(pattern=r"DATADOG|SENTRY.*OBS|OBSERVABILITY|MONITORING",
         target="docs/ops/", confidence="HIGH", flags=re.IGNORECASE),
    Rule(pattern=r"IMPLEMENTATION_REPORT|SESSION.*REPORT|BACKLOG",
         target="reports/", confidence="HIGH", flags=re.IGNORECASE),
    Rule(pattern=r"_grants_|_comparison_|_analysis_|GRANTS.*\d{4}",
         target="docs/research/", confidence="MEDIUM", flags=re.IGNORECASE),

    # Content-based (reads first 10 lines, slower)
    Rule(content_contains=r"\*\*Type:\*\* Design document",
         target="docs/design/", confidence="HIGH"),
    Rule(content_contains=r"\*\*Type:\*\* Research",
         target="docs/research/", confidence="HIGH"),
    Rule(content_contains=r"^# ADR-\d{3}",
         target="docs/architecture/ADR/", confidence="HIGH"),

    # Special: files in docs/content/ that are not auto-synced
    Rule(location="docs/content/", not_in_sync_list=True,
         flag="manually-edited-in-content", confidence="HIGH", fail_ci=True),
]
```

### 11b.2 Output

Results are written to two places:

1. **`UNDOCUMENTED.md` → `## Misplaced Files` section** — the table with proposed moves, confidence, and reason. Updated on every codemap run.

2. **`.codemap/misplaced.json`** — machine-readable version consumed by `make docs-fix`.

### 11b.3 CI behavior

- HIGH-confidence misplacements → PR comment warning, does **not** fail CI
- Manually edited `docs/content/` file → **fails CI** (edit will be silently overwritten)
- LOW/MEDIUM misplacements → listed in `UNDOCUMENTED.md`, no CI comment

### 11b.4 `make docs-fix` — applying moves locally

```makefile
docs-fix:
	python -m scripts.codemap docs-fix

docs-fix-dry:
	python -m scripts.codemap docs-fix --dry-run
```

Applies HIGH-confidence moves via `git mv` and updates internal `.md` links. See `DESIGN_docs_structure.md §6.3` for full behavior.

---

## 11c. Agent Instruction Files — Auto-Updated Docs Map

`agent_instructions.py` is a **regular module**, not a one-time script. It runs on every `make codemap` and every CI push. It keeps `AGENTS.md`, `.cursor/rules`, and `CLAUDE.md` (if present) in sync with the actual docs/ structure.

Every time a doc is added, moved, or removed, the next codemap run updates the docs map block in all agent instruction files automatically.

### 11c.1 What it does

1. Scans `docs/` and builds a structured inventory per section.
2. Renders the inventory as a markdown reference block.
3. Finds `<!-- codemap:auto:start section="docs-structure" -->` markers in agent files.
4. Replaces the block content with the fresh inventory.
5. Checks for dead links — `` `docs/path/to/file.md` `` references in agent files that no longer exist on disk.

In `--check` mode (CI): computes expected content, exits non-zero if stale. Does not write.

### 11c.2 Supported agent files

| File | Marker section | Notes |
|------|---------------|-------|
| `AGENTS.md` | `docs-structure` | Required — warns if marker absent |
| `.cursor/rules` / `.cursor/rules.md` / `.cursorrules` | `docs-structure` | Tries each in order |
| `.claude/CLAUDE.md` / `CLAUDE.md` | `docs-structure` | Optional — silent if absent |

### 11c.3 What to add to AGENTS.md

Add this block in the navigation/orientation section (after "read these files first", before task checklist):

````markdown
## Documentation Structure

Before creating any documentation file, check where it belongs.
Full spec: `docs/design/DESIGN_docs_structure.md`

| You're writing... | Put it in |
|-------------------|-----------|
| Architecture decision (stable, reviewed) | `docs/architecture/ADR/ADR-NNN-title.md` |
| Design doc (in progress) | `docs/design/DESIGN_*.md` |
| Feature user guide | `docs/features/<slug>/README.md` + `README-ru.md` |
| Work package / task spec | `docs/development/work-packages/NN-name.md` |
| Ops runbook (install, monitor, debug) | `docs/ops/` |
| Research / experiment | `docs/research/` |
| Hypothesis, not yet started | `docs/ideas/` |
| Session / implementation report | `reports/` |

Rules:
- `docs/architecture/`, `docs/design/`, `docs/ops/` require a `-ru.md` pair (EN first).
- `docs/content/` is auto-managed — never edit files there directly.
- `docs/archive/` is read-only — only `git mv` into it, never create files there.
- Blocks between `<!-- codemap:auto:start -->` and `<!-- codemap:auto:end -->` are
  auto-updated by `make codemap`. Do not edit those blocks manually.

<!-- codemap:auto:start section="docs-structure" -->
## Current Docs Map
<!-- Updated automatically by `make codemap`. Do not edit. -->
<!-- codemap:auto:end -->
````

### 11c.4 What to add to .cursor/rules

Add at the end of the file:

````markdown
## Documentation Placement

When creating or modifying documentation, always place files correctly:

- Architecture decisions (stable) → `docs/architecture/ADR/`
- Design docs (evolving) → `docs/design/DESIGN_*.md`
- Feature guides → `docs/features/<slug>/README.md` + `README-ru.md`
- Work packages → `docs/development/work-packages/`
- Ops runbooks → `docs/ops/`
- Research → `docs/research/`
- Ideas → `docs/ideas/`

Never:
- Create docs in repo root (only README/MANIFEST/AGENTS allowed there)
- Edit files in `docs/content/` (auto-overwritten on sync)
- Edit blocks between `<!-- codemap:auto:start -->` and `<!-- codemap:auto:end -->`

Every doc in `docs/architecture/`, `docs/design/`, `docs/ops/` needs a `-ru.md` pair.

<!-- codemap:auto:start section="docs-structure" -->
## Current Docs Map
<!-- Updated automatically by `make codemap`. Do not edit. -->
<!-- codemap:auto:end -->
````

### 11c.5 Dead link detection output

```
── Agent instruction files ──────────────────────────────────
  ✓ AGENTS.md updated
  ✓ .cursor/rules updated
  ⚠ Dead doc links found in agent instruction files:
    AGENTS.md: `docs/development/work-packages/01-factual-memory-adapter.md` does not exist
```

Dead links do not fail CI — informational only. Fix by updating the reference or running `make docs-fix` if the file was moved.

---

## 12. README.md — Auto-Updated Sections

`README.md` (and `README-ru.md`) contains sections that drift as components are implemented, plus sections that are human-authored philosophy text. Same marker strategy as SYSTEM_MAP.md.

### 12.1 Sections that are auto-updated

```markdown
<!-- codemap:auto:start section="roadmap-status" -->
```text
● Research              ✅ Complete
● Design                ✅ Complete
● Prototyping           ← We are here
  ├─ Factual Memory     ✅ Implemented (v0.1.0)
  ├─ Experience Store   ✅ Implemented (WP02)
  ├─ Identity Store     ✅ Implemented (WP03)
  ├─ Reflection Engine  ✅ Implemented (WP04)
  ├─ Session Manager    ✅ Implemented (WP05)
  ├─ Reality Anchor     ⏳ In progress
  └─ Skill Loop         ⏳ Queued
```
<!-- codemap:auto:end -->
```

```markdown
<!-- codemap:auto:start section="ready-components" -->
**✅ Factual Memory Adapter** ...
**✅ Experience Store** ...
<!-- codemap:auto:end -->
```

```markdown
<!-- codemap:auto:start section="test-stats" -->
- 31 test modules in `tests/` + 1 integration module (79 tests total)
<!-- codemap:auto:end -->
```

### 12.2 How component status is determined

| Status | Condition |
|--------|-----------|
| ✅ Implemented | `src/atman/<component>/` exists AND has at least one non-stub adapter AND test count > 0 |
| 🚧 In progress | Directory exists, no real adapter yet (only fakes) |
| ⏳ Queued | Directory absent OR declared in `components.yaml` but no files |

This makes the roadmap block in README reflect reality, not what an agent last wrote by hand.

### 12.3 Sections that are NOT touched

- Project philosophy / "What This Changes" / "How It Works" — human text
- Contact section
- Contributing / Code of Conduct links
- Any section without a `<!-- codemap:auto:start -->` marker

The same rule applies to `README-ru.md`: only marked sections are auto-updated (via the weekly translation workflow for the Russian prose, or via direct marker replacement for the Russian equivalents of the status tables).

---

## 13. Bilingual Strategy — EN Canonical → RU Quality Translation

Every file in the codemap system has an `-ru.md` twin. The strategy is:

```
EN file (always first, generated from code)
  └─ RU file (weekly LLM translation of changed sections only)
       └─ docs/content/ copy (weekly sync, both EN and RU)
```

### 13.1 What gets translated vs what stays in English

Even in the RU files, some content always stays in English regardless of translation:

| Content type | In RU file |
|-------------|-----------|
| File paths (`src/atman/core/ports/fact.py`) | English |
| Class and function names (`FactRecord`, `StateStore`) | English |
| CLI commands (`pytest tests/ -v`, `make codemap`) | English |
| SQL queries | English |
| Code blocks | English |
| Section headers | **Russian** |
| Prose descriptions of what a section/component does | **Russian** |
| Table column headers | **Russian** |
| Status emoji and values (✅, ⏳, PASS, FAIL) | Unchanged |

The LLM translator receives explicit instructions: "translate prose and headers; leave code, paths, and class names in English."

### 13.2 Marker structure in RU files

RU files use the same marker syntax with `lang="ru"`:

```markdown
<!-- codemap:auto:start section="modules-ports" lang="ru" -->
### 1.2. Порты / интерфейсы (`src/atman/core/ports/`)

| Файл | Назначение | Контракты |
|------|-----------|-----------|
| `core/ports/memory_backend.py` | Интерфейс фактической памяти | `FactualMemory` (ABC) |
<!-- codemap:auto:end -->
```

When the EN section changes, the RU block is flagged internally with a `needs-translation` attribute. The weekly translation workflow finds all flagged blocks, re-translates them from the updated EN source, and clears the flag.

### 13.3 Translation prompts

Two prompts: one for translation, one for quality check before sync.

#### Prompt 1 — Translation (used by `translate.yml` / `codemap translate`)

**System prompt:**
```
You are a technical documentation translator for the Atman project (an AI memory system).
Translate the provided English markdown documentation block into Russian.

STRICT RULES — no exceptions:
1. Translate: all prose, section headers, table column headers, list items that are descriptions.
2. Do NOT translate: file paths (src/atman/...), class names (FactRecord, StateStore),
   function names, CLI commands, shell/SQL/Python code blocks, environment variable names
   (POSTGRES_URL, ATMAN_LLM_MODEL), version numbers, status values (PASS/FAIL/WARN),
   emoji (✅ ⏳ 🔴), URLs, git branch names, Docker service names.
3. Keep all markdown formatting exactly: table structure, heading levels (##/###),
   bullet nesting, bold (**text**), inline code (`text`), fenced code blocks (```lang).
4. Do not add explanatory notes, translator comments, caveats, or anything not in the original.
5. Do not add or remove sections. Output only the translated block, nothing else.
6. Use consistent Russian technical terminology:
   - port → порт | adapter → адаптер | component → компонент
   - session → сессия | reflection → рефлексия | snapshot → снапшот
   - fact → факт | embedding → эмбеддинг | pipeline → пайплайн
   - schema → схема | migration → миграция | runtime → рантайм
   - stub / fake → заглушка | coverage → покрытие | stale → устаревший
   - canonical → канонический | drift → дрейф
```

**User message:**
```
Translate this documentation block from English to Russian.

---BEGIN ENGLISH---
{en_block_content}
---END ENGLISH---
```

**Call parameters:**
```python
model       = "claude-sonnet-4-20250514"
max_tokens  = len(en_block_content) * 3  # RU is longer than EN
temperature = 0                           # determinism over creativity
```

#### Prompt 2 — Quality check (used by `content_check.py` before docs/content/ sync)

**System prompt:**
```
You are a quality checker for bilingual technical documentation (English + Russian pairs).
You will receive two markdown files: the English original and its Russian translation.
Your job is to find quality problems ONLY — do not suggest style improvements.

Return ONLY a JSON object in this exact format, no other text:
{
  "ok": true/false,
  "problems": [
    {
      "severity": "error|warning",
      "type": "untranslated_prose|missing_section|placeholder|structure_mismatch|other",
      "location": "section header or line description",
      "detail": "brief description of the problem"
    }
  ]
}

Check for:
1. UNTRANSLATED_PROSE (error): Russian file contains English sentences in prose sections
   (not in code blocks, paths, class names — those should stay English).
2. MISSING_SECTION (error): A section (## heading) present in EN is absent in RU.
3. EXTRA_SECTION (warning): RU has a section not in EN.
4. PLACEHOLDER (error): RU file contains TODO, PLACEHOLDER, TBD, [TRANSLATE] in prose.
5. STALE_MARKER (warning): RU file contains <!-- needs-translation --> anywhere.
6. STRUCTURE_MISMATCH (warning): Tables in RU have different column count than EN.
7. EMPTY_TRANSLATION (error): A prose paragraph in EN has no corresponding content in RU.

Do NOT flag: English file paths, class names, commands, code blocks in RU (those are correct).
Do NOT flag: minor wording differences (translation is not literal).
```

**User message:**
```
Check this EN/RU documentation pair for quality problems.

---BEGIN ENGLISH FILE: {filename}---
{en_content}
---END ENGLISH---

---BEGIN RUSSIAN FILE: {filename_ru}---
{ru_content}
---END RUSSIAN---
```

**Call parameters:**
```python
model       = "claude-sonnet-4-20250514"
max_tokens  = 1024   # JSON response is short
temperature = 0
```

**How to use the result:**
```python
result = json.loads(response)
errors   = [p for p in result["problems"] if p["severity"] == "error"]
warnings = [p for p in result["problems"] if p["severity"] == "warning"]

if errors:
    # Commit anyway but open a GitHub issue / send notification
    notify(f"Translation errors in {filename_ru}: {errors}")

if result["ok"]:
    copy_to_content(en_path, ru_path)  # clean sync
```

### 13.4 Staleness tracking

The generator stores a hash of each EN marker block in `.codemap/en_hashes.json`. On the next run, if the hash changed, it sets `needs-translation=true` on the corresponding RU block. The translation workflow queries this file to know what to translate.

```json
{
  "SYSTEM_MAP.md::modules-ports": {
    "en_hash": "a1b2c3",
    "translated_at": "2026-05-12T03:00:00Z",
    "needs_translation": false
  },
  "SYSTEM_MAP.md::modules-services": {
    "en_hash": "d4e5f6",
    "translated_at": "2026-05-05T03:00:00Z",
    "needs_translation": true
  }
}
```

### 13.5 Full file inventory — what has an `-ru.md` twin

| EN file | RU twin | Updated by |
|---------|---------|-----------|
| `docs/architecture/SYSTEM_MAP.md` | `SYSTEM_MAP-ru.md` | Weekly translate |
| `docs/architecture/codemap/STARTUP_DEPS.md` | `STARTUP_DEPS-ru.md` | Weekly translate |
| `docs/architecture/codemap/TEST_ENV.md` | `TEST_ENV-ru.md` | Weekly translate |
| `docs/architecture/codemap/ENDPOINTS.md` | `ENDPOINTS-ru.md` | Weekly translate |
| `docs/architecture/codemap/DELTA_REPORT.md` | `DELTA_REPORT-ru.md` | Weekly translate |
| `docs/architecture/codemap/UNDOCUMENTED.md` | `UNDOCUMENTED-ru.md` | Weekly translate |
| `README.md` | `README-ru.md` | Weekly translate (marked sections only) |
| `MANIFEST.md` | `MANIFEST-ru.md` | Human (philosophy text, rarely changes) |
| `docs/architecture/SYSTEM.md` | `SYSTEM-ru.md` | Human (architecture narrative) |

`MANIFEST.md` and `SYSTEM.md` remain human-translated — they contain the philosophy and architecture rationale that benefits from careful authorship rather than automated translation.

---

## 14. docs/content/ — GitHub Pages Sync

`docs/content/` is read by the GitHub Pages site (`document.html`). It contains copies of the key docs and must stay in sync with the canonical files.

### 14.1 Files synced

```
docs/content/
  README.md              ← from root README.md
  README-ru.md           ← from root README-ru.md
  MANIFEST.md            ← from root MANIFEST.md
  MANIFEST-ru.md         ← from root MANIFEST-ru.md
  SYSTEM.md              ← from docs/architecture/SYSTEM.md
  SYSTEM-ru.md           ← from docs/architecture/SYSTEM-ru.md
  SYSTEM_MAP.md          ← from docs/architecture/SYSTEM_MAP.md
  SYSTEM_MAP-ru.md       ← from docs/architecture/SYSTEM_MAP-ru.md
```

### 14.2 Sync schedule and quality

The sync runs weekly on Mondays at 05:00 UTC, *after* the translation workflow has already updated the RU files. This ensures `docs/content/` always gets both EN and RU in their most current state.

**Quality bar for `docs/content/`:**
The files in `docs/content/` are what external visitors and other developers read on `atmanai.dev`. Before the weekly sync commits, the workflow runs a lightweight check:

```python
# scripts/codemap/content_check.py
def check_content_quality(en_path, ru_path):
    """
    Flags obvious quality problems before publishing to docs/content/:
    - RU file has English prose where Russian is expected (translation failed)
    - EN and RU files have different section count (structure desync)
    - Any file has placeholder text (TODO, PLACEHOLDER, TBD in prose sections)
    - RU file is more than 7 days older than EN file (not yet translated)
    """
```

If the check fails, the sync workflow posts a GitHub issue summary but still commits — a stale copy is better than no copy. The issue serves as a human nudge to fix translation quality.

### 14.3 Manual override

```bash
# Force sync right now (e.g., after a hotfix to MANIFEST.md)
make sync-site-content

# Check what would change without committing
make sync-site-content --dry-run
```

---

## 15. What This Does NOT Do

- Does not generate narrative architecture documentation (`SYSTEM.md`, `MANIFEST.md` — human-written)
- Does not evaluate code quality or correctness — maps only what exists
- Does not replace `AGENTS.md` — behavioral instructions stay human-written
- Does not detect semantic drift (class exists but behaves differently than documented) — that requires tests
- Does not watch files in real-time — batch job on push, not a daemon
- Does not translate `MANIFEST.md` or `SYSTEM.md` — those are human-translated (philosophy text)

---

## 16. Open Questions Before Implementation

Genuinely unresolved. Everything else in this document is decided.

1. **`.cursor/rules` filename** — check whether it's `.cursor/rules`, `.cursor/rules.md`, or `.cursorrules` in the actual repo. `agent_instructions.py` tries all three in order; just verify so the "marker absent" warning is accurate.

2. **`AGENTS.md` current content** — not readable via GitHub API without auth. Before adding the docs-structure marker (§11c.3), read the file locally and find the right insertion point. Don't insert mid-section.

3. **`.env.example`** — does it exist? If yes, the env var scanner can diff against it. If no, point the scanner at `src/atman/infra/config.py` typed config fields instead.

4. **`src/atman/` actual directory names** — `components.yaml` uses DEVELOPMENT_STANDARD.md §6 canonical names. Verify real directory names match before the first codemap run. A mismatch means components silently missing from the generated map.

5. **CI runner for coverage** — `--no-coverage` default in `codemap.yml`. If coverage is needed in CI, GitHub-hosted runner may time out. Consider self-hosted runner or separate scheduled coverage job.

6. **`atman-bot` identity** — translate and sync workflows commit as `atman-bot`. If no dedicated bot account, change `user.name` / `user.email` in workflow steps to `github-actions[bot]`.

---

## 17. Implementation Order

**Phase 0 — One-time repo cleanup (before any code):**

```bash
bash scripts/docs/01_archive.sh      # archive stale files
bash scripts/docs/02_scaffold.sh     # create ops/, design/, ADR/, codemap/
python scripts/docs/03_patch_dev_standard.py  # patch §24 + add §28
```

Then manually: add markers to `AGENTS.md` and `.cursor/rules` (see §11c.3–11c.4). Commit with `[skip ci]`.

**Phase 1 — EN codemap (delivers value immediately):**

1. `extractor/ast_walker.py` — core AST extraction. Test against `src/atman/core/models/` first.
2. Add `<!-- codemap:auto:start -->` markers to `docs/architecture/SYSTEM_MAP.md` §1 tables — one PR, no content change.
3. `renderer/system_map.py` — selective in-place replacement for §1 tables.
4. `components.yaml` + `__main__.py` — wire all components.
5. `extractor/docker_parser.py` + `extractor/env_scanner.py` → `renderer/startup_deps.py`.
6. `renderer/test_env.py` — static template + auto-detected LLM stack.
7. `snapshot/store.py` + `snapshot/diff.py` → `renderer/delta.py`.
8. `renderer/undocumented.py` + `classifier.py` — misplaced files detection.
9. `agent_instructions.py` — update AGENTS.md + .cursor/rules markers.
10. `codemap readme` subcommand — update README.md markers.
11. `codemap.yml` GitHub Actions workflow + full `make codemap` target.

**Phase 2 — Bilingual (after Phase 1 stable):**

12. `snapshot/en_hashes.json` staleness tracking.
13. `codemap flag-stale-ru` subcommand.
14. `codemap translate` subcommand — calls Claude API with prompts from §13.3.
15. `content_check.py` — quality gate using Prompt 2 from §13.3.
16. `translate.yml` + `sync-content.yml` weekly workflows (or configure via Routines).

**Phase 3 — Import graph (nice to have):**

17. Import graph Mermaid diagram inside SYSTEM_MAP.md.

Each phase delivers standalone value. Phase 2 does not block Phase 1.

