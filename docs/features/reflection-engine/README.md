# Reflection Engine

> **Russian:** [README-ru.md](README-ru.md)

## What It Does

The Reflection Engine processes accumulated experiences and generates structured insights about the agent's patterns, health, and development. It operates at three levels of depth, each with a different scope and trigger.

Reflection is not introspection performed during a conversation — it happens between sessions, as a distinct processing step.

## Three Levels

### Micro Reflection — `MicroReflectionService`

Runs after each session closes. Updates the RECENT layer of the narrative document with a synthesis of what happened. Lightweight: no pattern detection, no health scoring.

### Daily Reflection — `DailyReflectionService`

Runs once per day (or on demand). Scans recent `SessionExperience` records to detect emerging `PatternCandidate` objects. Each pattern has a `PatternType` (behavioral, relational, cognitive, etc.) and a `PatternStatus` (emerging, confirmed, resolved).

### Deep Reflection — `DeepReflectionService`

Runs weekly or on demand. Performs full structural analysis: entity relation mapping, merge candidate detection across experiences, and health assessment against Jahoda criteria. May propose changes to the agent's identity via `apply_self_change`.

## Key Concepts

**`PatternCandidate`** — a detected behavioral or cognitive pattern. Has a type, status, evidence references, and confidence score.

**`PatternStatus`** — `emerging` | `confirmed` | `resolved`. Patterns are promoted through statuses as evidence accumulates.

**`PatternType`** — classification of the pattern (behavioral, relational, cognitive, affective, etc.).

**`ReflectionEvent`** — a record of a single reflection run: what level, what was found, when it ran.

**`HealthAssessment`** — a structured assessment of the agent's psychological health using Jahoda's criteria.

**`JahodaCriterion`** — one of Marie Jahoda's six positive mental health criteria (e.g., self-acceptance, growth, autonomy, reality perception, environmental mastery, positive relations). Each criterion receives a `CriterionAssessment` with a score and reasoning.

**`ReflectionRecord`** — the persistent output of a completed reflection run, stored via `ReflectionEventStore`.

**`ReflectionModel` port** — the interface for the LLM-based reflection model. Implementations:
- `OpenAIReflectionModel` — calls any OpenAI-compatible endpoint
- `MockReflectionModel` — deterministic output for tests

## Public API

```python
from uuid import UUID
from datetime import datetime, timezone

# Micro reflection — run after session close (synchronous)
event = micro_service.reflect(session_id=session_id, agent_id=agent_id)

# Daily reflection — detect patterns for a given day
event = daily_service.reflect(date=datetime.now(timezone.utc))
for pattern in event.patterns_detected:
    print(pattern.type, pattern.status, pattern.confidence)

# Deep reflection — full structural analysis over a time window
event = deep_service.reflect(
    since=datetime(2026, 5, 1, tzinfo=timezone.utc),
    until=datetime(2026, 5, 19, tzinfo=timezone.utc),
)
```

All methods are synchronous.

## Configuration

```bash
# Reflection model backend: openai | anthropic | mock  (default: openai)
ATMAN_REFLECTION_BACKEND=openai

# LLM endpoint used by OpenAIReflectionModel
ATMAN_LLM_BASE_URL=http://localhost:8081/v1
ATMAN_LLM_MODEL=gemma3:27b-it-qat
```

## CLI

```bash
# Trigger a reflection manually
python -m atman.cli_reflection reflect micro --agent-id <uuid>
python -m atman.cli_reflection reflect daily --agent-id <uuid>
python -m atman.cli_reflection reflect deep --agent-id <uuid>

# Stream output live
python -m atman.cli_reflection reflect micro --live --agent-id <uuid>
```
