# Experience Store

> **Russian:** [README-ru.md](README-ru.md)

## What It Does

Experience Store archives the agent's first-person lived experiences. It stores not facts and not analysis, but *what the agent actually experienced* — the texture of interactions, emotional tone, and turning points.

Experiences are the raw material for reflection. `MicroReflectionService` reads them after each session; `DailyReflectionService` scans them for patterns; `DeepReflectionService` uses them for structural analysis.

## Key Concepts

**`KeyMoment`** — a first-class standalone record representing a significant moment within a session. Has a salience score that decays over time. Two key methods:
- `mark_accessed()` — call when this moment is retrieved; updates last-accessed timestamp
- `calculate_current_salience(now)` — returns current salience value accounting for time decay

**`SessionExperience`** — a read-only view over a closed session, assembled from its key moments and metadata. Not mutated after session close.

**`FeltSense`** — the agent's pre-verbal, intuitive sense of a situation. A qualitative descriptor attached to moments and experiences.

**`ContextHalo`** — ambient contextual information surrounding a session: environment, recent state, external factors.

**`ReframingNote`** — a retrospective note added to a key moment, providing new interpretation in light of later events. Appended via `ReframingNoteAppendResult`.

**`EmotionalDepth`** — a structured descriptor of the emotional weight of an experience.

**`SalienceDecayService`** — port that governs how salience diminishes as key moments age. Default implementation: `InMemorySalienceDecayService`.

## Public API

Experiences are stored and retrieved via `StateStore`:

```python
class StateStore(ABC):
    async def save_key_moment(self, moment: KeyMoment) -> None: ...
    async def get_key_moment(self, moment_id: str) -> KeyMoment | None: ...
    async def list_key_moments(self, session_id: str) -> list[KeyMoment]: ...
    async def save_session_experience(self, exp: SessionExperience) -> None: ...
    async def get_session_experience(self, session_id: str) -> SessionExperience | None: ...
```

Higher-level orchestration is in `ExperienceService`:

```python
class ExperienceService:
    async def capture_key_moment(self, session_id: str, input: KeyMomentInput) -> KeyMoment: ...
    async def close_session(self, session_id: str) -> SessionExperience: ...
    async def retrieve_recent(self, limit: int) -> list[SessionExperience]: ...
```

## Configuration

Experience Store uses the same `StateStore` backend as the rest of the system:

| `ATMAN_MEMORY_BACKEND` | Backend |
|------------------------|---------|
| `inmemory` | `InMemoryStateStore` |
| `file` (default) | `FileStateStore` — JSON files + `key_moments.jsonl` |
| `postgres` | `PostgresStateStore` |

## Example Usage

```bash
# Run the experience demo
make demo-experience

# CLI (if available)
python -m atman.cli_experience
```

Programmatic usage:

```python
# During a session — record a key moment
moment_input = KeyMomentInput(
    description="User shared a long-standing frustration about team communication.",
    felt_sense=FeltSense(quality="heavy, important"),
    salience=0.85,
)
moment = await experience_service.capture_key_moment(session_id, moment_input)

# After session close — retrieve the experience
exp = await experience_service.close_session(session_id)

# Later — check how salient that moment still is
current_salience = moment.calculate_current_salience(now=clock.now())
```
