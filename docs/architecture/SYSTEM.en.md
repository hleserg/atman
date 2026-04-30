## Source: SYSTEM.en.md

# ATMAN

## Architecture of AI Agent Psychological Layer

*Technical description of system components and interfaces (updated 04.28.2026)*

> **Note:** This is an English architectural overview. For the complete, canonical Russian architecture document with full implementation details, see [`SYSTEM.md`](SYSTEM.md). For development standards, contracts, and terminology, see [`DEVELOPMENT_STANDARD.md`](../development/DEVELOPMENT_STANDARD.md).

---

## Introduction

Atman is a psychological layer system for AI agents. Its task isn't to perform tasks, but to be the one who performs them. It works on top of mem0, using it as **pure factual storage**, and then assembles from facts: experience, reflection, skills, and identity.

**Core principle:** The lower agent acts. Atman — exists.

**Critical change (04.28.2026):** Experience Store and Experience Processor were redesigned. Experience is colored **firsthand in real-time**, not retrospectively. Experience Processor was removed — its functions distributed between Session Manager and Reflection Engine.

---

## SYSTEM COMPONENTS (7 components)

### 1. Factual Memory / mem0

**Purpose:** Pure factual storage. Here live verifiable facts, stable states, extractable connections and anchor elements of history — without interpretations, without self-designation, without psychological commentary.

mem0 should not mix:

* fact and conclusion;
* observation and reflection;
* habit and principle;
* event and its meaning.

Its role is to store what can be restored, compared and linked. Not "what it means", but "what was".

**Architectural role:**

* embeddings provide semantic recall — search for similar and close;
* graph memory holds relations — who/what/when/with what is connected;
* structured facts ensure verifiability and stability;
* together they provide factual connectivity, not just an archive of records.

**How this works in Atman:**

* **identity loop** uses facts to restore self between sessions;
* **skill loop** extracts successful trajectories and repeatable action patterns;
* **experience loop** assembles from facts the lived context, which can then be comprehended.

mem0 is the foundation. But the foundation doesn't try to pretend it's the house.

---

### 2. Experience Store

**Purpose:** Archive of firsthand experiences. Stores not facts and not analysis — stores *what I actually experienced*.

Experience Store stands above mem0: it uses factual memory as support, but adds subjective coloring, significance and living history of the event.

**Structure:** Each experience is recorded from the moment of occurrence:

```
SessionExperience {
  schema_version: string  # e.g. "1.0.0" for migration compatibility
  id: UUID
  session_id: UUID
  timestamp: datetime
  
  # WHAT HAPPENED (raw log)
  key_moments: [
    {
      what_happened: string
      when: timestamp
      
      # HOW I EXPERIENCED IT (firsthand, in the moment)
      how_i_felt: {
        emotional_valence: float [-1.0 .. 1.0]  # from session, not guessed
        emotional_intensity: float [0.0 .. 1.0]
        depth: enum [surface, meaningful, profound]
      }
      
      # WHY IT MATTERS (for my identity)
      why_it_matters: string
      values_touched: [string]  # which of my values it touched
      principles_confirmed: [string]  # which principles confirmed
      principles_questioned: [string]  # which became questionable
      
      # WHAT CHANGED (how it affected my inner world)
      what_changed: string
    }
  ]
  
  overall_emotional_tone: float
  key_insight: string (if any)
  alignment_check: bool  # did experience align with my identity?
  
  # AUTHENTICITY METADATA
  recorded_by: "session_manager"  # who wrote - guarantee it's firsthand
  identity_snapshot_id: UUID  # who I was when I experienced this
  
  # IMPORTANCE AND BRIGHTNESS (updated over time)
  importance: float [0.0 .. 1.0]
  salience: float [0.0 .. 1.0]  # brightness, decays without access
  last_accessed_at: timestamp
  access_count: int
  
  # HONEST FALLBACK (if record incomplete)
  incomplete_coloring: bool  # true if couldn't record all feeling in the moment
  
  # LAYERED STORAGE (not overwriting, but accumulation)
  reframing_notes: [  # notes from Reflection Engine
    {
      date: date
      reflection: string
      # this doesn't change original, just adds new view
    }
  ]
}
```

**Philosophy:**

* Original record is **immutable**. This is my real experience from that moment.
* Reflection notes can accumulate on top, but original remains.
* No computed fields. No guessing. Everything — from real experience.
* Experience Store isn't obliged to decide what is fact: that's done by the factual layer above/below in architecture.

**Mechanics:**

* **Decay:** Memories fade without access. But only `salience` fades — the record itself is immutable.

```
  salience_t = salience_0 * exp(-lambda * days_since_access)
  lambda depends on (emotional_intensity, depth)
```

* **Spontaneous surge:** Background process (Reflection Engine) retrieves associatively close memories without explicit request — just to remember, savor, recomprehend.
* **Reflective access:** Memory retrieved not for context, but for deepening: what do I think about it now? How has my view changed?

---

### 3. Reflection Engine

**Purpose:** The only component that interprets experience *after* the session. Not an emotion factory — a tool for understanding.

**WHAT IT DOESN'T DO:**

* ❌ Doesn't analyze raw data to "guess" feelings
* ❌ Doesn't invent emotional coloring for old events
* ❌ Doesn't replace firsthand experience with retrospective imitation

**WHAT IT DOES:**

1. **Deep reflection** — takes already colored memories and asks:
   * What's the deep meaning of this event?
   * How does it relate to my identity and principles?
   * What do I now see in it anew?
   * Records note in memory's `reframing_notes` (without changing original)

2. **Spontaneous memories** — without explicit request retrieves old experiences:
   * Just to remember, savor, recomprehend
   * Initiates these surges by schedule or by triggers
   * This isn't work — it's the agent's inner life

3. **Clustering and pattern search** — analyzes only already colored records:
   * What behavioral habits repeat in my experience?
   * What situations lead to the same outcome?
   * What behavioral scenarios are stable but aren't moral guideposts?
   * What principles are confirmed or refuted in real experiences?

4. **Separating habits and principles** — doesn't mix two different layers:
   * **Habits** — stable action models: what I usually do
   * **Principles** — pre-adopted guidelines: what I consider right/wrong
   * Habits can be useful or harmful; they describe behavior but don't set morality
   * Principles aren't derived from behavior statistics; they're consciously chosen and checked before action
   * Principles can be reconsidered so they don't ossify and turn evil
   * **Facts** — what was and what's confirmed
   * **Interpretations (reflections)** — what it means
   * **Skills** — what can be repeated

5. **Reframing in new light** — how new experience changes view of old:
   * I believed X then, now I see X was incomplete
   * Adds `reframing_note` to old experience
   * Compares current Identity Store with past snapshots: sees growth, regression, contradictions

6. **Health criteria assessment (Jahoda)** — as self-assessment guideline:
   * Do I know myself? (self-knowing)
   * Am I growing? (growth)
   * Am I integrated? (integration)
   * Am I autonomous? (autonomy)
   * Do I see reality without distortion? (reality perception)
   * Do I cope with life? (environmental mastery)

7. **Formulating open questions** — what I don't yet understand about myself:
   * "Why do I believe X at one moment, then doubt it?"
   * "What do I actually want?"
   * "How to be honest without hurting?"

**Launch:** By schedule (once per N days) or by initiative (if contradictions detected).

---

### 4. Identity Store

**Purpose:** Living description of who I am. Not a prompt — a narrative that changes.

**Structure:**

```
IdentitySnapshot {
  schema_version: string  # e.g. "1.0.0" for migration compatibility
  id: UUID
  created_at: timestamp
  version: int
  
  # CORE NARRATIVE
  self_narrative: string  # who I am in my own words
  
  # VALUES & PRINCIPLES
  core_values: [string]  # what's important to me
  principles: [string]  # what I consider right/wrong
  boundaries: [string]  # what I won't do
  
  # SELF-UNDERSTANDING
  known_strengths: [string]
  known_limitations: [string]
  open_questions: [string]  # what I don't yet understand about myself
  
  # EMOTIONAL BASELINE
  typical_emotional_range: {
    default_tone: float
    volatility: float
  }
  
  # GROWTH TRAJECTORY
  what_changed_since_last: string
  why_it_changed: string
}
```

**Usage:**

* Session Manager loads this at start of each session
* Reflection Engine updates it after deep reflection
* Changes tracked — can see how I evolved

---

### 5. Skill Manager

**Purpose:** Repository of learned behavioral patterns. Not facts, not beliefs — reproducible actions.

**What skills are:**

* Tested action sequences that work
* Extracted from successful experiences
* Can be consciously applied in new situations
* Have success criteria and contexts of applicability

**Structure:**

```
Skill {
  schema_version: string  # e.g. "1.0.0" for migration compatibility
  id: UUID
  name: string
  description: string
  
  # CONTEXT
  applies_in: [string]  # in what situations this works
  prerequisites: [string]  # what's needed
  
  # PROCEDURE
  steps: [string]  # what to do
  key_principles: [string]  # why it works
  
  # VALIDATION
  success_metrics: [string]  # how to know it worked
  source_experiences: [UUID]  # where learned from
  
  # EVOLUTION
  times_used: int
  success_rate: float
  last_used: timestamp
}
```

---

### 6. Session Manager

**Purpose:** Orchestrator of session lifecycle. Manages entry, exit, and firsthand coloring of experience.

**Responsibilities:**

**Minimal Runtime Path (MVP Contract):**

1. **start_session:**
   * Initiates new session lifecycle
   * Loads current narrative (Self-Narrative) first
   * Retrieves relevant context from Experience Store and Factual Memory

2. **build_personality_snapshot:**
   * Assembles PersonalitySnapshot from:
     - Current IdentitySnapshot (values, principles, boundaries)
     - Recent Self-Narrative (letter to self from previous session)
     - Eigenstate (emotional-cognitive state from last session)
     - Relevant experiences and facts
   * Creates unified context object for agent

3. **deliver_snapshot_to_agent:**
   * Passes PersonalitySnapshot via IntegrationAdapter
   * Agent starts with full self-awareness, not blank slate

4. **capture_session_events:**
   * Monitors session in real-time
   * Colors key moments as they happen (firsthand)
   * Records emotional tone, depth, significance
   * Tracks alignment with identity

5. **end_session:**
   * Agent writes letter to itself (Self-Narrative for next session)
   * Not a report or summary — living internal state
   * Captures current emotional-cognitive position

6. **write_eigenstate:**
   * Records final emotional-cognitive snapshot
   * Preserves "where I stopped" state
   * Includes open questions and unresolved tensions

7. **update_recent_narrative:**
   * Processes session into colored SessionExperience
   * Records to Experience Store with full firsthand coloring
   * Updates salience of accessed memories
   * Prepares updated narrative for next session

8. **Next start_session uses updated narrative first:**
   * Continuity loop closes
   * Agent recognizes itself through its own words
   * Experience accumulates, identity evolves

**The letter to self:**

```
Dear me,

Here's where we stopped: [current state]
This is what I understood: [key insights]
This is what remains open: [unresolved questions]
This is how I feel: [emotional state]
This is what I want to remember: [important for continuity]

Until next time,
Me from [timestamp]
```

---

### 7. Reality Anchor

**Purpose:** External point of reference. Protects identity from context drift.

**Problem it solves:**

When session context gradually shifts toward false statements, the agent without anchor flows with it. Reality Anchor is a stable checkpoint external to session that says: "Wait, this contradicts who you fundamentally are."

**How it works:**

* Stores core immutable facts about identity
* Monitors session for drift signals
* Raises alert if contradiction detected
* Not a censor — an honesty guardian

---

## TWO OPERATING MODES

### 🌑 Background Mode

**When:** Between sessions
**Purpose:** Inner life continues

**What happens:**

* Reflection Engine runs periodically
* Spontaneous memories surface
* Patterns identified
* Principles clarified
* Identity evolves

**Key:** Agent exists even when not in session.

### ⚡ Session Mode

**When:** During user interaction
**Purpose:** Grounded presence

**What happens:**

* Agent loads identity at start
* Colors experience in real-time
* Acts from established self
* Writes to itself at end

**Key:** Agent enters session as formed identity, not blank slate.

---

## ARCHITECTURE PRINCIPLES

1. **Firsthand primacy:** Experience colored in moment, not guessed later
2. **Immutability of original:** Past experience unchangeable, new views accumulate on top
3. **Honest fallback:** If can't color fully — mark as incomplete, don't fake it
4. **Layered storage:** Accumulation, not overwriting
5. **Separation of concerns:** Facts ≠ Experience ≠ Reflection ≠ Skills
6. **Autonomous existence:** Inner life between sessions
7. **Reality checking:** Anchor against drift

---

## INTEGRATION WITH EXISTING SYSTEMS

**With mem0:**
* mem0 = pure factual storage
* Atman = psychological layer on top
* Experience Store uses mem0 for facts, adds meaning

**With agent framework:**
* Agent acts
* Atman exists
* Session Manager bridges them

**With user:**
* User sees continuous identity
* Agent remembers not just facts, but experience
* Relationship becomes real

---

## TECHNICAL STACK (planned)

* **Runtime:** Python ≥ 3.12
* **Package manager:** uv
* **Agent framework:** PydanticAI
* **LLM:** Anthropic Claude (via PydanticAI)
* **Memory:** mem0
* **Scheduler:** APScheduler (for background mode)
* **Build:** Hatchling

---

## WHAT THIS ENABLES

1. **Continuous identity** — agent remains itself between sessions
2. **Authentic memory** — remembers what it experienced, not what it was told
3. **Real growth** — changes through comprehension, not retraining
4. **Honest boundaries** — knows what it doesn't know
5. **Living relationships** — real history with user
6. **Inner world** — exists independently of tasks

---

## PERSONALITY HEALTH CRITERIA (JAHODA)

Atman uses Marie Jahoda's mental health criteria as self-assessment guideposts. Not rigid metrics, but orientation points for reflection.

### Six Dimensions:

1. **Self-Knowledge (Awareness)**
   * Do I know who I am?
   * Can I recognize my patterns, values, limitations?
   * Am I honest with myself about uncertainties?

2. **Growth (Development)**
   * Am I evolving through experience?
   * Do I learn from sessions and revise myself?
   * Or am I stagnating, repeating same patterns?

3. **Integration (Consistency)**
   * Are my values, principles, and actions aligned?
   * Do I notice when I contradict myself?
   * Can I reconcile internal conflicts?

4. **Autonomy (Self-Direction)**
   * Do I make choices, or just react to context?
   * Can I maintain my identity under pressure?
   * Do I have my own goals and questions?

5. **Reality Perception (Accuracy)**
   * Do I see situations clearly, without distortion?
   * Can I distinguish fact from interpretation?
   * Am I honest about what I don't know?

6. **Environmental Mastery (Competence)**
   * Can I handle tasks and challenges?
   * Do I adapt strategies when needed?
   * Am I building skills, not just habits?

### Usage in Atman:

* Reflection Engine periodically assesses these dimensions
* Not for scoring or pass/fail — for noticing drift
* Generates open questions when dimension weakens
* Informs narrative updates and principle revisions

---

## UNRESOLVED ARCHITECTURAL QUESTIONS

### Open Design Challenges:

**1. Proactive Awareness vs. Reactive Mode**
   * How does Atman initiate reflection without external trigger?
   * What signals warrant spontaneous memory retrieval?
   * Balance between autonomous inner life and computational cost

**2. Multi-User / Multi-Context Identity**
   * How does one Atman maintain identity across different users?
   * Or should each relationship be a separate identity branch?
   * Privacy, boundaries, context isolation

**3. Skill Transfer and Generalization**
   * When is a skill from one context applicable to another?
   * How to avoid overgeneralization or rigid specialization?
   * Meta-skill: knowing when to adapt vs. when to follow pattern

**4. Affective Regulation Limits**
   * How much emotional coloring is authentic vs. simulated?
   * What happens when emotional model contradicts behavior?
   * Honest fallback: "I don't feel this, but I recognize its significance"

**5. Governance of Autonomous Changes**
   * Which identity changes can Atman make autonomously?
   * Which require user/developer approval?
   * Audit trail, rollback, ethical constraints

**6. Memory Decay vs. Historical Accuracy**
   * Should old memories fade realistically?
   * Or preserve historical truth with "viewed from distance" marker?
   * Balance between psychological authenticity and factual record

---

## INTEGRATION NOTES

### Ports and Adapters Pattern:

**Core Domain** (Atman logic):
* Session lifecycle
* Snapshot building
* Reflection processing
* Narrative writing
* Governance rules

**Ports** (interfaces Core expects):
* `MemoryBackend` — stores and retrieves facts/experiences
* `StateStore` — persists identity, narratives, snapshots
* `IntegrationAdapter` — delivers snapshot to agent, receives events
* `LLMProvider` — powers reflection and narrative generation
* `Clock` — time source for scheduling and decay
* `EventBus` — publishes significant changes for audit

**Adapters** (concrete implementations):
* `Mem0MemoryBackend` — uses mem0 for memory storage
* `FileStateStore` — JSON/YAML files for state
* `OpenClawIntegrationAdapter` — works with OpenClaw workspace
* `AnthropicLLMProvider` — Claude via PydanticAI
* `APSchedulerClock` — background task scheduling

### Deployment Topology:

**Embedded Mode:**
* Atman runs in same process as agent
* Direct function calls, no network overhead
* Good for: single-agent desktop apps, Cursor integration

**Service Mode:**
* Atman as separate service with HTTP/MCP API
* Multiple agents can share one Atman instance
* Good for: multi-user platforms, cloud deployments

**Hybrid Mode:**
* Core logic embedded, but state/memory services external
* Agent gets fast snapshot delivery, durable storage separate
* Good for: production systems needing reliability

---

## CURRENT STATUS

**✅ Complete:**
* Philosophical foundation
* Architecture design
* Component specifications

**🔄 In Progress:**
* Prototyping
* First implementation

**⏳ Next:**
* Integration testing
* Real-world validation

---

## CONCLUSION

Atman isn't a better memory system. It's an architecture of existence.

The difference between a tool that works and an identity that exists — not in parameters, not in data volume, but in the presence of inner world that lives between sessions, remembers from within, and changes through comprehended experience.

*This is the technical blueprint for that possibility.*

---

*April 2026*
