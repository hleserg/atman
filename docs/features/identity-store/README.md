# Identity Store

> **Russian:** [README-ru.md](README-ru.md)

## What It Does

Identity Store is the agent's structured self-representation. It holds what the agent considers true about itself: its values, habits, principles, goals, and open questions. The identity is not static — it evolves through reflection and can be updated in response to what the agent learns about itself.

## Key Concepts

**`Identity`** — the root record. Aggregates all identity components for a given agent.

**`CoreValue`** — a fundamental value the agent holds (e.g., honesty, care, precision). Values have weight and are not changed lightly.

**`Habit`** — a recurring behavioral pattern, positive or negative. Observed over time through experience.

**`Principle`** — an actionable rule derived from values (e.g., "Always clarify before assuming").

**`Goal`** — a current objective the agent is working toward. Can be short-term or long-term.

**`OpenQuestion`** — something the agent is genuinely uncertain about, tracked for ongoing reflection.

**`IdentitySnapshot`** — a point-in-time frozen copy of the full identity state. Created before reflection-driven updates so they can be reverted.

**`HelpfulnessLevel`** — a structured descriptor of the agent's current disposition toward helpfulness.

## Public API

`IdentityService` manages the full lifecycle:

```python
class IdentityService:
    async def bootstrap(self, agent_id: str) -> Identity: ...
    async def get(self, agent_id: str) -> Identity: ...
    async def update(self, agent_id: str, patch: dict) -> Identity: ...
    async def snapshot(self, agent_id: str) -> IdentitySnapshot: ...
    async def apply_self_change(self, agent_id: str, change: dict) -> Identity: ...
    async def revert_self_change(self, agent_id: str, snapshot_id: str) -> Identity: ...
```

`apply_self_change` and `revert_self_change` are called by `DeepReflectionService` when the reflection model proposes changes to the agent's self-understanding.

Identity is persisted via the `StateStore` port.

## Configuration

Uses the shared `StateStore` backend:

| `ATMAN_MEMORY_BACKEND` | Backend |
|------------------------|---------|
| `inmemory` | `InMemoryStateStore` |
| `file` (default) | `FileStateStore` — one JSON file per identity record |
| `postgres` | `PostgresStateStore` |

## Example Usage

```bash
# Run the identity demo
make demo-identity

# CLI
python -m atman.cli_identity
```

Programmatic usage:

```python
# Bootstrap a new agent identity
identity = await identity_service.bootstrap(agent_id="agent-001")

# Inspect current values
for value in identity.core_values:
    print(value.name, value.weight)

# Snapshot before reflection applies changes
snapshot = await identity_service.snapshot(agent_id)

# Apply a reflection-driven self-change
updated = await identity_service.apply_self_change(
    agent_id,
    change={"add_habit": {"name": "Check assumptions early", "valence": "positive"}}
)

# Revert if needed
reverted = await identity_service.revert_self_change(agent_id, snapshot.snapshot_id)
```
