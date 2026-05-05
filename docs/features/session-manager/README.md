# Session Manager

**Status:** Implemented (WP-05)
**Purpose:** Session runtime that experiences sessions in real-time, not retrospectively

[[ru](README-ru.md)] — *Russian version*

---

## Overview

Session Manager is the session runtime that **lives through sessions**, not just packages them. It's the component that makes Atman an experiencer, not just a recorder.

**Core principle:** Experience is colored **in the moment**, not guessed later.

---

## What Session Manager Does

### At Session Start

1. **Loads personality context:**
   - Current identity (values, principles, goals, baseline)
   - Current narrative (core + recent layers)
   - Last eigenstate (where previous session ended)
   - Recent reflections summary (placeholder for future)

2. **Creates SessionContext** - complete "who I am right now" snapshot

### During Session

1. **Tracks raw events** from lower agent:
   - User messages, agent responses, decisions, conflicts, errors
   - Not all events become key moments - this is just tracking

2. **Captures key moments** with first-hand emotional coloring:
   - What happened + how I felt + why it matters + what changed
   - Emotional valence, intensity, depth **MUST be present**
   - If coloring couldn't be captured → `incomplete_coloring` flag

3. **Validates emotional coloring:**
   - Refuses key moments without emotions (unless `incomplete_coloring=True`)
   - This prevents fabricating emotions retrospectively

### At Session End

1. **Creates SessionExperience:**
   - Packages key moments (already colored)
   - Marks `recorded_by="session_manager"` (first-hand guarantee)
   - Sets importance/salience defaults
   - Stores in Experience Store

2. **Creates Eigenstate:**
   - Emotional tone, intensity, cognitive load
   - Open threads, dominant themes, unresolved tensions
   - Session summary and key insight
   - Used to start next session with context

3. **Stores both** and removes session from active tracking

---

## Architecture

### Domain Models

```python
# Session context at start
SessionContext {
    session_id: UUID
    identity: Identity              # Who I am
    narrative: NarrativeDocument    # My letter to self
    emotional_baseline: float       # Current baseline
    last_eigenstate: Eigenstate?    # Where I stopped last time
    recent_reflections_summary: str # What changed recently
}

# Raw events during session
SessionEvent {
    event_type: str        # user_message, decision, conflict, error
    description: str       # What happened
    metadata: dict         # Additional context
    marked_as_key_moment: bool  # Did this become key?
}

# Key moment input (REQUIRES emotional coloring)
KeyMomentInput {
    what_happened: str

    # HOW I FELT (mandatory)
    emotional_valence: float      # -1.0 to +1.0
    emotional_intensity: float    # 0.0 to 1.0
    depth: EmotionalDepth         # surface/meaningful/profound

    # WHY IT MATTERS
    why_it_matters: str
    values_touched: [str]
    principles_confirmed: [str]
    principles_questioned: [str]
    what_changed: str

    # HONEST FALLBACK
    incomplete_coloring: bool  # True if couldn't capture fully
}

# Session result
SessionResult {
    session_id: UUID
    events: [SessionEvent]
    key_moments: [KeyMoment]     # Already colored
    overall_emotional_tone: float
    key_insight: str
    alignment_check: bool        # Did experience match identity?
    incomplete_coloring: bool    # Any moments incomplete?
    eigenstate: Eigenstate       # State at end
}
```

### Session Manager API

```python
class SessionManager:
    def start_session(self, agent_id: UUID) -> SessionContext:
        """Load personality context and start session."""

    def record_event(self, session_id: UUID, event: SessionEvent) -> None:
        """Track raw event (not all become key moments)."""

    def record_key_moment(self, session_id: UUID, moment: KeyMomentInput) -> None:
        """Capture key moment with mandatory emotional coloring."""

    def finish_session(
        self,
        session_id: UUID,
        overall_emotional_tone: float = 0.0,
        key_insight: str = "",
        alignment_check: bool = True,
    ) -> SessionResult:
        """Create SessionExperience + Eigenstate and store both."""
```

---

## Key Design Principles

### 1. First-Hand Experience, Not Retrospective Guessing

```python
# ✅ CORRECT - captured in the moment
moment = KeyMomentInput(
    what_happened="User challenged my understanding",
    emotional_valence=-0.2,
    emotional_intensity=0.7,
    depth=EmotionalDepth.MEANINGFUL,
    why_it_matters="Made me question what I thought I knew",
)

# ❌ WRONG - would reject or require incomplete_coloring
moment = KeyMomentInput(
    what_happened="Something happened",
    emotional_valence=0.0,      # No emotion
    emotional_intensity=0.0,    # No intensity
    depth=EmotionalDepth.SURFACE,
    why_it_matters="...",
    incomplete_coloring=False,  # Claims coloring is complete
)
# → Raises ValueError: "no emotional coloring"
```

### 2. Incomplete Coloring is Honest, Not Failure

If emotional coloring couldn't be captured in the moment, mark it explicitly:

```python
moment = KeyMomentInput(
    what_happened="Session ended abruptly",
    emotional_valence=0.0,
    emotional_intensity=0.0,
    depth=EmotionalDepth.SURFACE,
    why_it_matters="Didn't have time to process",
    incomplete_coloring=True,  # Honest about limitation
)
```

This is **better** than fabricating emotions later.

### 3. Not All Events are Key Moments

Session Manager tracks everything but only significant moments get emotional coloring:

```python
# Regular event - just tracking
manager.record_event(session_id, SessionEvent(
    event_type="user_message",
    description="User asked about weather",
))

# Key moment - significant for identity
manager.record_key_moment(session_id, KeyMomentInput(
    what_happened="User challenged my core assumption",
    emotional_valence=-0.3,
    emotional_intensity=0.8,
    depth=EmotionalDepth.PROFOUND,
    why_it_matters="Forced me to reconsider fundamental belief",
))
```

### 4. Experience Store Gets Already-Colored Records

```python
# Session Manager stores experience with:
experience = SessionExperience(
    recorded_by="session_manager",  # Guarantees first-hand
    key_moments=[...],               # Already colored
    incomplete_coloring=True/False,  # Explicit about quality
)
```

Experience Processor (removed in redesign) never has to guess emotions.

---

## Running the Demo

### Quick Start

```bash
# Default (with pauses)
make demo-session

# Instant output (no pauses)
make demo-session-fast

# Or directly
python3 src/demo_session_manager.py
```

### What the Demo Shows

1. Creates test identity with values and goals
2. Creates narrative document (core + recent layers)
3. Starts session → SessionContext with personality
4. Records raw events from lower agent
5. Captures 2 key moments with first-hand emotional coloring
6. Finishes session → SessionExperience + Eigenstate
7. Verifies experience stored with `recorded_by="session_manager"`

**No external services required** - uses ephemeral temporary file storage (system temp directory with `atman-session-demo-*` prefix).

---

## Testing

```bash
# Run session manager tests
pytest tests/test_session_manager.py -v

# All tests
pytest tests/ -v
```

### Test Coverage

Tests verify:

✅ Start session returns context with identity & narrative
✅ Key moment without emotional coloring is rejected
✅ Key moment with `incomplete_coloring` flag is allowed
✅ Finish session creates SessionExperience & Eigenstate
✅ Original key moments don't mutate after storage
✅ Resource/token warnings can be key moments
✅ Multiple key moments in one session
✅ Eigenstate captures session state correctly

---

## Integration with Other Components

### Identity Store

Session Manager **reads** at start:

- Current identity (values, principles, emotional baseline)

Session Manager **writes** at start:

- `IdentitySnapshot` for provenance (who the agent was when the session began)

### Narrative Store

Session Manager **reads** at start:

- Current narrative (core + recent layers)

Session Manager **writes** after a successful `finish_session`:

- Updates the **recent** narrative layer with a short session summary (optimistic `updated_at` check on save to reduce silent overwrites)

### Experience Store

Session Manager **writes** at end:

- `SessionExperience` with `recorded_by="session_manager"` and a **deterministic** experience id derived from `session_id` so retries after partial persistence do not create duplicates
- This is the **only** component that writes first-hand experience

### Eigenstate

Session Manager **reads** the latest eigenstate **scoped by `identity_id`** when present so a switched identity in the same workspace does not inherit another agent’s cognitive snapshot.

### Reflection Engine

Session Manager **prepares** for reflection:

- Eigenstate provides starting point for next session
- Experience is already colored - no need to guess emotions later

---

## Differences from Original Design

**Before (Experience Processor):**

- Experience written raw to mem0
- Experience Processor would "guess" emotions later
- Reflection worked with fabricated feelings

**After (Session Manager):**

- Experience colored in real-time
- Session Manager is active experiencer
- Reflection works with authentic first-hand records
- `incomplete_coloring` flag for honesty about limitations

This redesign (28.04.2026) makes Atman's experience genuinely first-person.

---

## Common Patterns

### Pattern 1: Simple Session

```python
manager = SessionManager(state_store)

# Start
context = manager.start_session(agent_id)

# Experience something significant
manager.record_key_moment(context.session_id, KeyMomentInput(
    what_happened="...",
    emotional_valence=0.5,
    emotional_intensity=0.6,
    depth=EmotionalDepth.MEANINGFUL,
    why_it_matters="...",
))

# Finish
result = manager.finish_session(context.session_id)
```

### Pattern 2: Session with Events and Key Moments

```python
# Track everything
for event in lower_agent_events:
    manager.record_event(session_id, SessionEvent(...))

# But only significant moments get emotional coloring
if is_significant(event):
    manager.record_key_moment(session_id, KeyMomentInput(...))
```

### Pattern 3: Incomplete Coloring

```python
# If session ends abruptly or emotions unclear
manager.record_key_moment(session_id, KeyMomentInput(
    what_happened="...",
    emotional_valence=0.0,
    emotional_intensity=0.0,
    depth=EmotionalDepth.SURFACE,
    why_it_matters="...",
    incomplete_coloring=True,  # Honest about limitation
))
```

---

## Future Enhancements

- [ ] Reality Anchor integration (detect identity drift during session)
- [ ] Affective Regulation level 1 (acute self-regulation in session)
- [ ] Resource monitoring (token/memory warnings as key moments)
- [ ] Proactive key moment detection (suggest to lower agent)
- [ ] Session replay for reflection

---

## See Also

- [Experience Store](../experience-store/README.md) - where colored experiences live
- [Identity Store](../identity-store/README.md) - personality context
- [Reflection Engine](../reflection-engine/README.md) - deep meaning extraction
- [Work Package 05](../../development/work-packages/05-session-manager.md) - original spec
- [SYSTEM.md](../../architecture/SYSTEM.md) - full architecture
