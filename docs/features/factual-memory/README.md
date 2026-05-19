# Factual Memory

> **Russian:** [README-ru.md](README-ru.md)

## What It Does

Factual Memory stores verifiable, discrete facts about the world — things the agent knows to be true about people, places, events, or itself. These are not interpretations, feelings, or narratives: they are checkable statements.

Facts persist across sessions. When a new session begins, relevant facts are injected into the agent context by `PassiveMemoryInjector` using embedding similarity and BM25 retrieval.

## Key Concepts

**`FactRecord`** — a single verifiable fact. Contains the fact text, source, confidence, and timestamps. Has a schema version for forward compatibility.

**`Relation`** — a typed directed link between two entities (e.g., `Person A works_at Company B`). Stored alongside facts and used by the entity registry for relationship reasoning.

**`FactualMemory` port** — the interface all backends implement. Core logic depends only on this interface, never on a specific backend.

**Conflict detection** — `ConflictDetector` can scan for facts that contradict each other and surface them for resolution.

## Public API

The `FactualMemory` port defines:

```python
class FactualMemory(ABC):
    def add_fact(self, record: FactRecord) -> FactRecord: ...
    def get_fact(self, fact_id: UUID) -> FactRecord | None: ...
    def search(self, query: str, limit: int = 10) -> list[FactRecord]: ...
    def invalidate_fact(self, fact_id: UUID) -> bool: ...
    def list_recent(self, limit: int = 10) -> list[FactRecord]: ...
    def link(self, source_id: UUID, target_id: UUID, relation_type: str) -> bool: ...
```

## Configuration

Select the backend with the `ATMAN_MEMORY_BACKEND` environment variable:

| Value | Backend | Notes |
|-------|---------|-------|
| `inmemory` | `InMemoryBackend` | Ephemeral, resets on restart. Suitable for tests. |
| `file` | `FileBackend` | JSONL file in the workspace directory. Default. |
| `postgres` | `PostgresFactualMemory` | Requires `ATMAN_DB_URL`. |

When using the `postgres` backend, set one of:

```bash
ATMAN_DB_URL=postgresql://atman:secret@localhost:5432/atman
# or
DATABASE_URL=postgresql://atman:secret@localhost:5432/atman
```

## Example Usage

Start the interactive REPL:

```bash
atman
```

Run the demo:

```bash
make demo-factual
```

Programmatic usage:

```python
from atman.config import build_memory_backend

backend = build_memory_backend()  # reads ATMAN_MEMORY_BACKEND from env

fact = FactRecord(content="Alice is the lead engineer.", source="onboarding")
stored = backend.add_fact(fact)

results = backend.search("lead engineer")
```
