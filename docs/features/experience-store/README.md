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

Key moments are stored via `StateStore`:

```python
class StateStore(ABC):
    def create_key_moment(self, key_moment: KeyMoment) -> KeyMoment: ...
    def store_key_moment(self, key_moment: KeyMoment) -> KeyMoment: ...  # idempotent upsert
    def get_key_moment(self, moment_id: UUID) -> KeyMoment | None: ...
    def list_key_moments(self, session_id: UUID | None = None) -> list[KeyMoment]: ...
    def mark_moment_accessed(self, moment_id: UUID) -> None: ...
```

Session experiences (closed session views) are stored via `StateStore`:

```python
class StateStore(ABC):
    def create_experience(self, record: ExperienceRecord) -> ExperienceRecord: ...
    def get_experience(self, experience_id: UUID) -> ExperienceRecord | None: ...
    def list_recent_experiences(self, limit: int = 10) -> list[ExperienceRecord]: ...
```

Higher-level orchestration is in `ExperienceService`:

```python
class ExperienceService:
    def create_experience(self, record: ExperienceRecord) -> ExperienceRecord: ...
    def get_experience(self, experience_id: UUID) -> ExperienceRecord | None: ...
    def add_reframing_note(self, experience_id: UUID, note: ReframingNote) -> ...: ...
    def search_by_session(self, session_id: UUID, limit: int = 10) -> list[ExperienceRecord]: ...
    def list_recent(self, limit: int = 10) -> list[ExperienceRecord]: ...
```

All methods are synchronous.

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
from uuid import UUID
from datetime import datetime, timezone

# Key moments are appended during a session via SessionManager
session_manager.append_key_moment_input(session_id, KeyMomentInput(
    what_happened="User shared a long-standing frustration about team communication.",
    emotional_valence=-0.4,
    emotional_intensity=0.8,
    depth=EmotionalDepth.MEANINGFUL,
    why_it_matters="Long-standing frustration signals a trust issue worth exploring.",
))

# After session close — retrieve recent experiences
experiences = experience_service.list_recent(limit=5)

# Check current salience of a stored moment
moment = state_store.get_key_moment(moment_id)
current_salience = moment.calculate_current_salience(now=datetime.now(timezone.utc))
moment.mark_accessed()
```
