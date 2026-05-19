# Atman — System Architecture

## Overview

Atman is a psychological runtime layer for AI agents. It gives agents continuous identity, first-person memory, and structured self-reflection. It is not a replacement for an LLM — it is a layer that sits above one.

The lower agent acts. Atman exists.

The system follows a strict layered architecture: **Core** (domain logic) → **Ports** (interfaces) → **Adapters** (infrastructure) → **Agent layer** (Pydantic AI integration).

## Core Principles

- **Core has no external dependencies.** It never imports LLM clients or file I/O directly. All external calls go through ports (interfaces).
- **Ports define contracts.** Adapters implement them. Services use ports.
- **Clock is injected.** `datetime.now()` never appears in domain logic — `ClockPort` is passed in.
- **Storage is versioned.** All persistent structures carry a schema version for forward compatibility.
- **Eval is isolated.** Production users pay zero cost for eval infrastructure (see ADR-001).

## Component Map

### Domain Models

Located in `src/atman/core/models/`.

| File | Classes |
|------|---------|
| `fact.py` | `FactRecord`, `Relation` — verifiable facts and typed links between entities |
| `experience.py` | `SessionExperience`, `KeyMoment`, `FeltSense`, `ContextHalo`, `ReframingNote`, `EmotionalDepth`, `ReframingNoteAppendResult` — lived experience with salience decay (`mark_accessed()`, `calculate_current_salience()`) and session closure metadata |
| `identity.py` | `Identity`, `CoreValue`, `Habit`, `Principle`, `Goal`, `OpenQuestion`, `IdentitySnapshot`, `HelpfulnessLevel` — agent self-representation |
| `narrative.py` | `NarrativeDocument`, `NarrativeLayer`, `NarrativeThread`, `Eigenstate`, `LayerType` — self-narrative with CORE / RECENT / THREADS layers |
| `session.py` | `SessionContext`, `SessionEvent`, `KeyMomentInput`, `SessionResult`, `ActiveSessionSummary`, `Session` — session runtime and persistence models |
| `reflection.py` | `ReflectionLevel`, `PatternCandidate`, `PatternStatus`, `PatternType`, `ReflectionEvent`, `HealthAssessment`, `JahodaCriterion`, `CriterionAssessment`, `ReflectionRecord` — three-level reflection with Jahoda psychological health criteria |

### Ports

Located in `src/atman/core/ports/`. All are ABCs or Protocols — Core depends only on these, never on concrete implementations.

| File | Interface |
|------|-----------|
| `memory_backend.py` | `FactualMemory` (ABC) — factual memory CRUD and search |
| `state_store.py` | `StateStore` — storage for experience, identity, narrative, eigenstate, key moments, sessions |
| `clock.py` | `ClockPort` (Protocol) — domain clock; injected everywhere `datetime.now()` would appear |
| `affect.py` | `AffectPort` (Protocol) — async affect hook called on each session event |
| `reflection.py` | `ExperienceRepository`, `IdentityRepository`, `NarrativeRepository`, `ReflectionModel`, `PatternStore`, `ReflectionEventStore`, `HealthAssessmentStore` |
| `entity_registry.py` | `EntityRegistry` (ABC) — entity resolution with L1 / L2 / L3 cache tiers |
| `embedding.py` | `EmbeddingPort` (Protocol) — vector embedding interface |
| `skill_manager.py` | `SkillManagerPort` (Protocol) — skill lifecycle interface |
| `maintenance_queue.py` | `MaintenanceQueue` (ABC) — background job queue |
| `salience_decay.py` | `SalienceDecayService` (ABC) — key moment salience decay |
| `memory_guardian.py` | `MemoryGuardian` (ABC) — memory integrity checks |
| `linguistic.py` | `LinguisticAnalyzer` (ABC) — NER and linguistic analysis |
| `memory_reranker.py` | `MemoryReranker` (ABC) — re-ranking of retrieved memory results |

### Services

Located in `src/atman/core/services/`. Services contain domain logic and depend only on ports.

| Service | Responsibility |
|---------|----------------|
| `ExperienceService` | Experience lifecycle: capture, retrieve, close sessions |
| `IdentityService` | Identity lifecycle, bootstrap, snapshot, reflection self-apply (`apply_self_change` / `revert_self_change`) |
| `NarrativeService` | Narrative document management across CORE / RECENT / THREADS layers |
| `SessionManager` | Session runtime: `start_session`, `record_event` (with `AffectDetector` hook), `append_key_moment`, `finish_session` with eigenstate; optional journal-based crash recovery; optional `PostWriteScheduler` for maintenance jobs |
| `MicroReflectionService` | Post-session narrative update |
| `DailyReflectionService` | Pattern detection across recent experiences |
| `DeepReflectionService` | Deep analysis, entity relation mapping, merge candidate detection |
| `PassiveMemoryInjector` | Surfaces relevant facts and experiences via embedding similarity + BM25 |
| `ConflictDetector` | Detects contradictions between facts |
| `InMemorySalienceDecayService` | In-process salience decay for key moments |
| `MaintenanceWorker` | Claims and dispatches maintenance jobs from the queue |
| `AmbientMemoryService` | Entity-anchor parallel RAG for ambient context |

### Adapters

Located in `src/atman/adapters/`. Each adapter implements a port.

**Memory (`FactualMemory` port):**
- `InMemoryBackend` — ephemeral, for tests
- `FileBackend` — JSONL append-only file
- `PostgresFactualMemory` — PostgreSQL with full-text search

**Storage (`StateStore` port):**
- `InMemoryStateStore` — ephemeral
- `FileStateStore` — JSON files per record type + `key_moments.jsonl`
- `PostgresStateStore` — PostgreSQL

**Embeddings (`EmbeddingPort`):**
- `OllamaEmbeddingAdapter` — local Ollama server (default: bge-m3)
- `FlagEmbeddingAdapter` — BAAI/bge-m3 via FlagEmbedding library (1024d)
- `MockEmbeddingAdapter` — deterministic zeros for tests
- `BM25EmbeddingAdapter` — sparse BM25 retrieval

**Linguistic (`LinguisticAnalyzer` port):**
- `GLiNERPlusMiniLMAdapter` — GLiNER entity recognition + MiniLM
- `NoOpLinguisticAnalyzer` — pass-through, no analysis

**Entity registry (`EntityRegistry` port):**
- `InMemoryEntityRegistry`
- `PostgresEntityRegistry`

**Reflection model (`ReflectionModel` port):**
- `OpenAIReflectionModel` — any OpenAI-compatible API (llama-server, Ollama, etc.)
- `MockReflectionModel` — deterministic responses for tests

**Observability:**
- `adapters/observability/sentry.py` — opt-in Sentry SDK integration. No-op when `SENTRY_DSN` is absent. Tracks errors, routine spans, translation failures, session transactions, and maintenance spans. Environments: `dev`, `routine`, `ci`.

### Agent Layer

Located in `src/atman/adapters/agent/`.

| Component | Description |
|-----------|-------------|
| `AtmanRunner` / `AtmanTurn` | Pydantic AI agent runner with pre/post pipeline, RAG injection, skill trigger routing, and full session lifecycle |
| `AtmanDeps` | Dependency injection container carrying all ports and services |
| `factory.py` | Assembles the full stack from a workspace path + `AgentConfig` |

Agent tools exposed to the LLM:
- `record_key_moment` — save a key moment during a session
- `log_experience` — record a significant experience
- `restart_session` — gracefully restart the current session
- `wait_session` — suspend session and wait
- `resolve_pending_review` — mark a pending reflection review as resolved
- `request_reflection` — trigger an on-demand reflection cycle

### Skills

Located in `src/atman/skills/`.

| Component | Description |
|-----------|-------------|
| `SkillManager` | Full lifecycle: `invoke`, `mark_result`, `capture`, `process_session_skills`, `process_daily_skills`, `process_deep_skills` |
| `SkillManagerPort` | Canonical interface (in `core/ports/`) |
| `InMemorySkillStore` | Ephemeral skill store |
| `PostgresSkillStore` | Persistent skill store |

CLI: `atman-skills` — list, show, pin, unpin, invoke, and more.

## Data Flow

```
User/LLM turn
    │
    ▼
AtmanRunner (pre-pipeline)
    │  PassiveMemoryInjector → inject relevant facts + experiences into context
    │  AmbientMemoryService → entity-anchor RAG
    │
    ▼
LLM generates response
    │
    ▼
AtmanRunner (post-pipeline)
    │  SessionManager.record_event() → AffectPort hook
    │  SkillManagerPort → check skill triggers
    │  MaintenanceQueue → schedule background jobs
    │
    ▼
Session finish
    │  SessionManager.finish_session()
    │  MicroReflectionService → narrative update
    │  PostWriteScheduler → daily/deep reflection jobs
    │
    ▼
Persistent storage (StateStore + FactualMemory)
```

## External Dependencies

| Dependency | Role | Required |
|------------|------|----------|
| PostgreSQL | Factual memory, state, entity registry (when `ATMAN_MEMORY_BACKEND=postgres`) | No — file/inmemory backends available |
| llama-server or any OpenAI-compatible LLM | Reflection model and agent LLM | Yes |
| Ollama | Embedding generation (bge-m3) | No — FlagEmbedding or mock available |
| Sentry | Error tracking and performance monitoring | No — opt-in via `SENTRY_DSN` |
| Anthropic | Alternative LLM for reflection | No — opt-in via `ANTHROPIC_API_KEY` |

### Install Profiles

| Profile | Contents |
|---------|----------|
| `pip install atman` | Production runtime only |
| `pip install "atman[eval]"` | Core + eval deps (Alembic, SQLAlchemy, PostgreSQL) |
| `pip install "atman[dev]"` | Core + dev/test deps |
| `pip install "atman[all]"` | Everything |

The `eval/` module is isolated behind a lazy import guard. Production code never imports it. See ADR-001.
