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
    def bootstrap_identity(self, agent_id: UUID) -> Identity: ...
    def get_identity(self, agent_id: UUID) -> Identity | None: ...
    def add_core_value(self, agent_id: UUID, value: CoreValue) -> Identity: ...
    def add_principle(self, agent_id: UUID, principle: Principle) -> Identity: ...
    def add_habit(self, agent_id: UUID, habit: Habit) -> Identity: ...
    def add_goal(self, agent_id: UUID, goal: Goal) -> Identity: ...
    def create_snapshot(self, agent_id: UUID, description: str) -> IdentitySnapshot: ...
    def apply_self_change(self, agent_id: UUID, target_kind: SelfChangeTargetKind, payload: Any, source: SelfChangeSource) -> SelfAppliedChange: ...
    def revert_self_change(self, agent_id: UUID, change_id: UUID) -> Identity: ...
```

All methods are synchronous. `apply_self_change` and `revert_self_change` are called by `DeepReflectionService` when the reflection model proposes changes to the agent's self-understanding.

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
from uuid import UUID

agent_id = UUID("...")

# Bootstrap a new agent identity
identity = identity_service.bootstrap_identity(agent_id)

# Inspect current values
for value in identity.core_values:
    print(value.name, value.confidence)

# Snapshot before reflection applies changes
snapshot = identity_service.create_snapshot(agent_id, description="pre-reflection")

# Add a new principle
identity = identity_service.add_principle(
    agent_id,
    Principle(text="Always clarify before assuming.", source="reflection")
)
```
