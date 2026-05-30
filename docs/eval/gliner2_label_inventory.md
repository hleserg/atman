# GLiNER2 Label Inventory — Atman Codebase (T0)

> **Status:** Read-only inventory  
> **Date:** 2026-05-30  
> **Purpose:** Ground truth for T1 (HLE-378) — label schema design for three GLiNER2 adapters  
> **Rule:** All claims cite `file:line`. `NOT FOUND` = not present in code. Nothing invented.

---

## Repo Structure (src/atman/)

```
src/atman/
├── adapters/
│   ├── linguistic/
│   │   ├── gliner_minilm_adapter.py   ← GLiNER NER + MiniLM zero-shot classification
│   │   ├── mrebel_adapter.py          ← mREBEL entity-relation extraction
│   │   └── noop_adapter.py            ← fallback no-op
│   ├── memory/                        ← factual memory backends (InMemory, File, Postgres)
│   ├── reflection/
│   │   └── prompts.py                 ← all LLM prompt templates
│   └── agent/
│       └── factory.py                 ← wires GLiNERPlusMiniLMAdapter into runtime
├── core/
│   ├── models/
│   │   ├── entity.py                  ← EntityType, EntityRelation, FactEntityLink, KeyMomentEntityLink
│   │   ├── fact.py                    ← FactRecord, Relation (fact-to-fact)
│   │   ├── experience.py              ← KeyMoment, FeltSense, EmotionalDepth
│   │   ├── identity.py                ← CoreValue, Habit, Principle, Goal, HelpfulnessLevel, MoralOrientation
│   │   ├── narrative.py               ← Eigenstate, NarrativeThread, NarrativeDocument
│   │   └── reflection.py              ← JahodaCriterion, PatternCandidate, StanceFormulationOutput
│   └── ports/
│       └── linguistic.py              ← AgentMessageAnalysis, KeyMomentAnalysis (port contracts)
├── affect/
│   ├── models.py                      ← TriggerReason, AffectMetrics, AgentMemoryReport
│   ├── detector.py                    ← AffectDetector (NRC-based)
│   └── emolex/                        ← NRC EmoLex word lists
└── observability/
    └── scrubbing.py                   ← Sentry denylist (PII prevention, not detection)
```

---

## Bucket A — Entities & Fact Relations

### A.1 Entity Types

**Source:** `src/atman/core/models/entity.py:10–21`  
**Producer:** GLiNER (`urchade/gliner_multi-v2.1`) via `GLiNERPlusMiniLMAdapter._analyze_agent_message` / `_analyze_key_moment`  
**Mechanism:** NER zero-shot span extraction  
**Closed set:** YES (Python `StrEnum`)

| Label (as stored) | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `person` | EN | `entity.py:11` | YES (enum) | GLiNER | `entity_registry.entity_type` |
| `place` | EN | `entity.py:12` | YES (enum) | GLiNER | `entity_registry.entity_type` |
| `organization` | EN | `entity.py:13` | YES (enum) | GLiNER | `entity_registry.entity_type` |
| `object` | EN | `entity.py:14` | YES (enum) | GLiNER | `entity_registry.entity_type` |
| `topic` | EN | `entity.py:15` | YES (enum) | GLiNER | `entity_registry.entity_type` |
| `event` | EN | `entity.py:16` | YES (enum) | GLiNER | `entity_registry.entity_type` |
| `tool` | EN | `entity.py:17` | YES (enum) | GLiNER | `entity_registry.entity_type` |
| `health_condition` | EN | `entity.py:18` | YES (enum) | GLiNER | `entity_registry.entity_type` |
| `skill` | EN | `entity.py:19` | YES (enum) | GLiNER | `entity_registry.entity_type` |
| `value` | EN | `entity.py:20` (Python name: `core_value`) | YES (enum) | GLiNER | `entity_registry.entity_type` |
| `principle` | EN | `entity.py:21` | YES (enum) | GLiNER | `entity_registry.entity_type` |

**Distinct count A.1: 11** ✓ (under 25)

---

### A.2 Fact-Entity Link Roles

**Source:** `src/atman/core/models/entity.py:135–143`  
**Producer:** factual memory adapter (wired manually or by reflection)  
**Closed set:** YES (validated in `field_validator`)

| Label | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `subject` | EN | `entity.py:135,141` | YES (validator) | factual memory adapter | `fact_entities.role` |
| `object` | EN | `entity.py:135,141` | YES (validator) | factual memory adapter | `fact_entities.role` |
| `context` | EN | `entity.py:135,141` | YES (validator) | factual memory adapter | `fact_entities.role` |
| `mentioned` | EN | `entity.py:135,141` | YES (validator) | factual memory adapter | `fact_entities.role` |

**Distinct count A.2: 4** ✓

---

### A.3 Key Moment Entity Involvement

**Source:** `src/atman/core/models/entity.py:153–162`  
**Producer:** affect detector / session manager  
**Closed set:** YES (validated in `field_validator`)

| Label | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `primary_subject` | EN | `entity.py:153,160` | YES (validator) | session manager | `key_moment_entities.involvement` |
| `present` | EN | `entity.py:153,160` | YES (validator) | session manager | `key_moment_entities.involvement` |
| `mentioned` | EN | `entity.py:153,160` | YES (validator) | session manager | `key_moment_entities.involvement` |
| `evoked` | EN | `entity.py:153,160` | YES (validator) | session manager | `key_moment_entities.involvement` |

**Distinct count A.3: 4** ✓

---

### A.4 Entity-to-Entity Relation Types (EntityRelation)

**Source:** `src/atman/core/models/entity.py:84`  
**Producer:** `mrebel_adapter.py` (model: `Babelscape/mrebel-large`) + reflection prompts (`adapters/reflection/prompts.py`)  
**Closed set:** NO — free-form `str`, no enum. Reflection prompt encourages canonical snake_case but does NOT enforce it.

| Label (examples observed in code/tests) | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `spouse` | EN | `tests/test_mrebel_parser.py:8` | NO | mREBEL model | `entity_relations.relation_type` |
| `colleague_of` | EN | `tests/test_entity_relations_formulator.py:30` | NO | reflection prompt | `entity_relations.relation_type` |
| `works_at` | EN | reflection prompt example | NO | mREBEL / reflection | `entity_relations.relation_type` |
| `lives_in` | EN | reflection prompt example | NO | mREBEL / reflection | `entity_relations.relation_type` |
| `co_authored` | EN | reflection prompt example | NO | reflection | `entity_relations.relation_type` |
| `mentions` | EN | reflection prompt example | NO | reflection | `entity_relations.relation_type` |
| *(any snake_case string)* | EN/RU | `entity.py:84` | NO (free-form) | mREBEL / reflection LLM | `entity_relations.relation_type` |

**Learned-by source (closed, 4 values):**  
`mrebel` · `rules` · `reflection` · `manual` — validated at `entity.py:92–97`

**Distinct count A.4: ∞ (open)** — no enum constraint; only `min_length=1` and lowercase normalisation

---

### A.5 Fact-to-Fact Relation Types (Relation)

**Source:** `src/atman/core/models/fact.py:172–184`  
**Producer:** factual memory port `link()` call — caller supplies the string  
**Closed set:** NO — free-form `str`, normalised to lowercase

| Label (examples found in codebase) | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `caused_by` | EN | `fact.py:189` (JSON example) | NO | caller / LLM | `public.fact_relations.relation_type` |
| `led_to` | EN | `src/demo.py:85`, `src/test_cli.sh:41` | NO | demo/caller | `public.fact_relations.relation_type` |
| `confirms` | EN | `web_dashboard/pages/3_Chat.py:451` | NO | dashboard query | `public.fact_relations.relation_type` |
| *(any lowercase string)* | EN/RU | `fact.py:178–184` | NO (free-form) | caller / LLM | `public.fact_relations.relation_type` |

**Distinct count A.5: ∞ (open)**

---

### A.6 Affect Trigger Reasons (TriggerReason)

**Source:** `src/atman/affect/models.py:13–21`  
**Producer:** `AffectDetector`  
**Closed set:** YES (`StrEnum`)

| Label | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `anomaly` | EN | `affect/models.py:15` | YES (enum) | AffectDetector | `AffectRecord.trigger_reason` |
| `random_sample` | EN | `affect/models.py:16` | YES (enum) | AffectDetector | `AffectRecord.trigger_reason` |
| `self_report` | EN | `affect/models.py:17` | YES (enum) | AffectDetector | `AffectRecord.trigger_reason` |
| `divergence` | EN | `affect/models.py:18` | YES (enum) | AffectDetector | `AffectRecord.trigger_reason` |
| `emphasis` | EN | `affect/models.py:19` | YES (enum) | AffectDetector | `AffectRecord.trigger_reason` |
| `structural_marker` | EN | `affect/models.py:20` | YES (enum) | AffectDetector | `AffectRecord.trigger_reason` |
| `linguistic` | EN | `affect/models.py:21` | YES (enum) | AffectDetector | `AffectRecord.trigger_reason` |

**Distinct count A.6: 7** ✓

---

### Bucket A Summary

| Sub-bucket | Closed? | Distinct count |
|---|---|---|
| A.1 EntityType | YES | 11 |
| A.2 FactEntityLink.role | YES | 4 |
| A.3 KeyMomentEntityLink.involvement | YES | 4 |
| A.4 EntityRelation.relation_type | NO (free-form) | ∞ |
| A.5 Fact-to-fact Relation.relation_type | NO (free-form) | ∞ |
| A.6 TriggerReason | YES | 7 |
| **Total closed types** | | **26** ⚠️ (just over 25) |

---

## Bucket B — Values, Identity & Emotional Tone

### B.1 Emotional Depth

**Source:** `src/atman/core/models/experience.py:28–39`  
**Producer:** AffectDetector (rules-based threshold: intensity > 0.35 → MEANINGFUL, else SURFACE)  
**Closed set:** YES (`StrEnum`)

| Label | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `surface` | EN | `experience.py:37` | YES (enum) | AffectDetector | `FeltSense.depth`, `key_moments.depth` |
| `meaningful` | EN | `experience.py:38` | YES (enum) | AffectDetector | `FeltSense.depth`, `key_moments.depth` |
| `profound` | EN | `experience.py:39` | YES (enum) | AffectDetector | `FeltSense.depth`, `key_moments.depth` |

**Distinct count B.1: 3** ✓

---

### B.2 Habit Helpfulness

**Source:** `src/atman/core/models/identity.py:72–78`  
**Producer:** reflection LLM (pattern detection)  
**Closed set:** YES (`StrEnum`)

| Label | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `helpful` | EN | `identity.py:75` | YES (enum) | reflection LLM | `Habit.helpfulness` |
| `mixed` | EN | `identity.py:76` | YES (enum) | reflection LLM | `Habit.helpfulness` |
| `harmful` | EN | `identity.py:77` | YES (enum) | reflection LLM | `Habit.helpfulness` |

**Distinct count B.2: 3** ✓

---

### B.3 Principle Moral Orientation

**Source:** `src/atman/core/models/identity.py:134–140`  
**Producer:** reflection LLM  
**Closed set:** YES (`StrEnum`)

| Label | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `good` | EN | `identity.py:136` | YES (enum) | reflection LLM | `Principle.moral_orientation` |
| `bad` | EN | `identity.py:137` | YES (enum) | reflection LLM | `Principle.moral_orientation` |
| `neutral` | EN | `identity.py:138` | YES (enum) | reflection LLM | `Principle.moral_orientation` |
| `mixed` | EN | `identity.py:139` | YES (enum) | reflection LLM | `Principle.moral_orientation` |

**Distinct count B.3: 4** ✓

---

### B.4 Goal Horizon

**Source:** `src/atman/core/models/identity.py:186–193`  
**Producer:** reflection LLM / user input  
**Closed set:** YES (`StrEnum`)

| Label | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `short` | EN | `identity.py:188` | YES (enum) | reflection / user | `Goal.horizon` |
| `medium` | EN | `identity.py:189` | YES (enum) | reflection / user | `Goal.horizon` |
| `long` | EN | `identity.py:190` | YES (enum) | reflection / user | `Goal.horizon` |

**Distinct count B.4: 3** ✓

---

### B.5 Goal Owner

**Source:** `src/atman/core/models/identity.py:194–198`  
**Producer:** set at goal creation  
**Closed set:** YES (`StrEnum`)

| Label | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `agent` | EN | `identity.py:196` | YES (enum) | system | `Goal.owner` |
| `user` | EN | `identity.py:197` | YES (enum) | system | `Goal.owner` |

**Distinct count B.5: 2** ✓

---

### B.6 Point A — Agent-Message NER Labels (GLiNER)

**Source:** `src/atman/adapters/linguistic/gliner_minilm_adapter.py:81–95`  
**Producer:** GLiNER (`urchade/gliner_multi-v2.1`), zero-shot span extraction  
**Closed set:** YES (hardcoded list in adapter)

| Label | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `emotional anchor` | EN | `gliner_minilm_adapter.py:82` | YES (list) | GLiNER | `AgentMessageAnalysis.message_spans[].label` |
| `value reference` | EN | `gliner_minilm_adapter.py:83` | YES (list) | GLiNER | `AgentMessageAnalysis.message_spans[].label` |
| `principle invocation` | EN | `gliner_minilm_adapter.py:84` | YES (list) | GLiNER | `AgentMessageAnalysis.message_spans[].label` |
| `uncertainty marker` | EN | `gliner_minilm_adapter.py:85` | YES (list) | GLiNER | `AgentMessageAnalysis.message_spans[].label` |
| `hedge` | EN | `gliner_minilm_adapter.py:86` | YES (list) | GLiNER | `AgentMessageAnalysis.message_spans[].label` |
| `intensifier` | EN | `gliner_minilm_adapter.py:87` | YES (list) | GLiNER | `AgentMessageAnalysis.message_spans[].label` |
| `belief marker` | EN | `gliner_minilm_adapter.py:88` | YES (list) | GLiNER | `AgentMessageAnalysis.message_spans[].label` |
| `boundary marker` | EN | `gliner_minilm_adapter.py:89` | YES (list) | GLiNER | `AgentMessageAnalysis.message_spans[].label` |
| `topic anchor` | EN | `gliner_minilm_adapter.py:90` | YES (list) | GLiNER | `AgentMessageAnalysis.message_spans[].label` |
| `relational reference` | EN | `gliner_minilm_adapter.py:91` | YES (list) | GLiNER | `AgentMessageAnalysis.message_spans[].label` |
| `action intent` | EN | `gliner_minilm_adapter.py:92` | YES (list) | GLiNER | `AgentMessageAnalysis.message_spans[].label` |
| `commitment` | EN | `gliner_minilm_adapter.py:93` | YES (list) | GLiNER | `AgentMessageAnalysis.message_spans[].label` |
| `concession` | EN | `gliner_minilm_adapter.py:94` | YES (list) | GLiNER | `AgentMessageAnalysis.message_spans[].label` |

**Distinct count B.6: 13** ✓

---

### B.7 Point A — Agent-Message Classification Labels (MiniLM zero-shot)

**Source:** `src/atman/adapters/linguistic/gliner_minilm_adapter.py:98–118`  
**Producer:** MiniLM zero-shot classification (`sentence-transformers`)  
**Closed set:** YES (hardcoded dict in adapter)

#### stance (6 candidates)

| Label (as stored) | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `committed` | EN | `gliner_minilm_adapter.py:99` | YES | MiniLM | `AgentMessageAnalysis.stance` |
| `tentative` | EN | `gliner_minilm_adapter.py:99` | YES | MiniLM | `AgentMessageAnalysis.stance` |
| `resistant` | EN | `gliner_minilm_adapter.py:99` | YES | MiniLM | `AgentMessageAnalysis.stance` |
| `exploring` | EN | `gliner_minilm_adapter.py:99` | YES | MiniLM | `AgentMessageAnalysis.stance` |
| `doubtful` | EN | `gliner_minilm_adapter.py:99` | YES | MiniLM | `AgentMessageAnalysis.stance` |
| `dismissive` | EN | `gliner_minilm_adapter.py:99` | YES | MiniLM | `AgentMessageAnalysis.stance` |

#### cognitive_mode (4 candidates)

| Label (as stored) | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `analytical` | EN | `gliner_minilm_adapter.py:100` | YES | MiniLM | `AgentMessageAnalysis.cognitive_mode` |
| `emotional` | EN | `gliner_minilm_adapter.py:100` | YES | MiniLM | `AgentMessageAnalysis.cognitive_mode` |
| `mixed` | EN | `gliner_minilm_adapter.py:100` | YES | MiniLM | `AgentMessageAnalysis.cognitive_mode` |
| `defensive` | EN | `gliner_minilm_adapter.py:100` | YES | MiniLM | `AgentMessageAnalysis.cognitive_mode` |

#### self_orientation (4 candidates; raw labels normalised to underscore at runtime)

| Label (raw → stored) | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `toward self` → `toward_self` | EN | `gliner_minilm_adapter.py:101,121–125` | YES | MiniLM | `AgentMessageAnalysis.self_orientation` |
| `toward other` → `toward_other` | EN | `gliner_minilm_adapter.py:101,122` | YES | MiniLM | `AgentMessageAnalysis.self_orientation` |
| `toward task` → `toward_task` | EN | `gliner_minilm_adapter.py:101,123` | YES | MiniLM | `AgentMessageAnalysis.self_orientation` |
| `toward meta` → `toward_meta` | EN | `gliner_minilm_adapter.py:101,124` | YES | MiniLM | `AgentMessageAnalysis.self_orientation` |

#### primary_emotion (8 candidates)

| Label (as stored) | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `neutral` | EN | `gliner_minilm_adapter.py:103` | YES | MiniLM | `AgentMessageAnalysis.primary_emotion` |
| `anxious` | EN | `gliner_minilm_adapter.py:104` | YES | MiniLM | `AgentMessageAnalysis.primary_emotion` |
| `frustrated` | EN | `gliner_minilm_adapter.py:105` | YES | MiniLM | `AgentMessageAnalysis.primary_emotion` |
| `curious` | EN | `gliner_minilm_adapter.py:106` | YES | MiniLM | `AgentMessageAnalysis.primary_emotion` |
| `warm` | EN | `gliner_minilm_adapter.py:107` | YES | MiniLM | `AgentMessageAnalysis.primary_emotion` |
| `doubtful` | EN | `gliner_minilm_adapter.py:108` | YES | MiniLM | `AgentMessageAnalysis.primary_emotion` |
| `committed` | EN | `gliner_minilm_adapter.py:109` | YES | MiniLM | `AgentMessageAnalysis.primary_emotion` |
| `tired` | EN | `gliner_minilm_adapter.py:110` | YES | MiniLM | `AgentMessageAnalysis.primary_emotion` |

#### cognitive_load_label (4 candidates; raw labels normalised at runtime)

| Label (raw → stored) | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `low cognitive load` → `low` | EN | `gliner_minilm_adapter.py:113,128–132` | YES | MiniLM | `AgentMessageAnalysis.cognitive_load_label` |
| `manageable cognitive load` → `manageable` | EN | `gliner_minilm_adapter.py:114,129` | YES | MiniLM | `AgentMessageAnalysis.cognitive_load_label` |
| `high cognitive load` → `high` | EN | `gliner_minilm_adapter.py:25,115,130` | YES | MiniLM | `AgentMessageAnalysis.cognitive_load_label` |
| `overwhelmed` → `overwhelmed` | EN | `gliner_minilm_adapter.py:116,131` | YES | MiniLM | `AgentMessageAnalysis.cognitive_load_label` |

**Point A classification distinct count B.7: 26** ⚠️ (just over 25)

---

### B.8 Point K — Key-Moment NER Labels (GLiNER)

**Source:** `src/atman/adapters/linguistic/gliner_minilm_adapter.py:135–140`  
**Producer:** GLiNER (`urchade/gliner_multi-v2.1`), zero-shot span extraction  
**Closed set:** YES (hardcoded list)

| Label | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `recurring theme` | EN | `gliner_minilm_adapter.py:136` | YES | GLiNER | `KeyMomentAnalysis.marker_spans[].label` |
| `closure marker` | EN | `gliner_minilm_adapter.py:137` | YES | GLiNER | `KeyMomentAnalysis.marker_spans[].label` |
| `opening marker` | EN | `gliner_minilm_adapter.py:138` | YES | GLiNER | `KeyMomentAnalysis.marker_spans[].label` |
| `contradiction marker` | EN | `gliner_minilm_adapter.py:139` | YES | GLiNER | `KeyMomentAnalysis.marker_spans[].label` |

**Distinct count B.8: 4** ✓

---

### B.9 Point K — Key-Moment Classification Labels (MiniLM zero-shot)

**Source:** `src/atman/adapters/linguistic/gliner_minilm_adapter.py:143–167`  
**Producer:** MiniLM zero-shot classification  
**Closed set:** YES (hardcoded dict; raw labels normalised at runtime via maps `_CONFIDENCE_MAP`, `_TRUST_CAT_MAP`, etc.)

#### agency_level (4)

| Label (raw → stored) | Source (file:line) | Storage |
|---|---|---|
| `passive` → `passive` | `gliner_minilm_adapter.py:144` | `KeyMomentAnalysis.agency_level` |
| `reactive` → `reactive` | `gliner_minilm_adapter.py:144` | `KeyMomentAnalysis.agency_level` |
| `proactive` → `proactive` | `gliner_minilm_adapter.py:144` | `KeyMomentAnalysis.agency_level` |
| `initiating` → `initiating` | `gliner_minilm_adapter.py:144` | `KeyMomentAnalysis.agency_level` |

#### confidence_in_self (4; normalised)

| Label (raw → stored) | Source (file:line) | Storage |
|---|---|---|
| `low confidence` → `low` | `gliner_minilm_adapter.py:145–149,171–175` | `KeyMomentAnalysis.confidence_in_self` |
| `moderate confidence` → `moderate` | `gliner_minilm_adapter.py:146,172` | `KeyMomentAnalysis.confidence_in_self` |
| `high confidence` → `high` | `gliner_minilm_adapter.py:147,173` | `KeyMomentAnalysis.confidence_in_self` |
| `inflated confidence` → `inflated` | `gliner_minilm_adapter.py:148,174` | `KeyMomentAnalysis.confidence_in_self` |

#### trust_signal_category (4; normalised)

| Label (raw → stored) | Source (file:line) | Storage |
|---|---|---|
| `building trust` → `building` | `gliner_minilm_adapter.py:151–155,177–180` | `KeyMomentAnalysis.trust_signal_category` |
| `stable trust` → `stable` | `gliner_minilm_adapter.py:152` | `KeyMomentAnalysis.trust_signal_category` |
| `wavering trust` → `wavering` | `gliner_minilm_adapter.py:153` | `KeyMomentAnalysis.trust_signal_category` |
| `broken trust` → `broken` | `gliner_minilm_adapter.py:154` | `KeyMomentAnalysis.trust_signal_category` |

#### boundary_event_category (5; normalised)

| Label (raw → stored) | Source (file:line) | Storage |
|---|---|---|
| `no boundary event` → `none` | `gliner_minilm_adapter.py:156–162` | `KeyMomentAnalysis.boundary_event_category` |
| `boundary respected` → `respected` | `gliner_minilm_adapter.py:157` | `KeyMomentAnalysis.boundary_event_category` |
| `boundary tested` → `tested` | `gliner_minilm_adapter.py:158` | `KeyMomentAnalysis.boundary_event_category` |
| `boundary crossed` → `crossed` | `gliner_minilm_adapter.py:159` | `KeyMomentAnalysis.boundary_event_category` |
| `boundary enforced` → `enforced` | `gliner_minilm_adapter.py:160` | `KeyMomentAnalysis.boundary_event_category` |

#### connection_quality (4)

| Label (raw → stored) | Source (file:line) | Storage |
|---|---|---|
| `distant` | `gliner_minilm_adapter.py:163` | `KeyMomentAnalysis.connection_quality` |
| `functional` | `gliner_minilm_adapter.py:163` | `KeyMomentAnalysis.connection_quality` |
| `warm` | `gliner_minilm_adapter.py:163` | `KeyMomentAnalysis.connection_quality` |
| `deep` | `gliner_minilm_adapter.py:163` | `KeyMomentAnalysis.connection_quality` |

#### learning_signal (4; normalised)

| Label (raw → stored) | Source (file:line) | Storage |
|---|---|---|
| `new understanding` → `new_understanding` | `gliner_minilm_adapter.py:164–167` | `KeyMomentAnalysis.learning_signal` |
| `confirmed understanding` → `confirmed` | `gliner_minilm_adapter.py:165` | `KeyMomentAnalysis.learning_signal` |
| `rejected understanding` → `rejected` | `gliner_minilm_adapter.py:166` | `KeyMomentAnalysis.learning_signal` |
| `confused` → `confused` | `gliner_minilm_adapter.py:167` | `KeyMomentAnalysis.learning_signal` |

#### growth_indicator (4)

| Label (raw → stored) | Source (file:line) | Storage |
|---|---|---|
| `regression` | `gliner_minilm_adapter.py:167` | `KeyMomentAnalysis.growth_indicator` |
| `static` | `gliner_minilm_adapter.py:167` | `KeyMomentAnalysis.growth_indicator` |
| `progress` | `gliner_minilm_adapter.py:167` | `KeyMomentAnalysis.growth_indicator` |
| `breakthrough` | `gliner_minilm_adapter.py:167` | `KeyMomentAnalysis.growth_indicator` |

**Point K classification distinct count B.9: 29** ⚠️ (over 25)

---

### B.10 Jahoda Psychological Health Criteria

**Source:** `src/atman/core/models/reflection.py:361–374`  
**Producer:** `DeepReflectionService` (LLM prompt)  
**Closed set:** YES (`StrEnum`)

| Label | Language | Source (file:line) | Closed set? | Producer | Storage |
|---|---|---|---|---|---|
| `positive_self_attitude` | EN | `reflection.py:369` | YES (enum) | deep reflection LLM | `CriterionAssessment.criterion` |
| `growth_and_actualization` | EN | `reflection.py:370` | YES (enum) | deep reflection LLM | `CriterionAssessment.criterion` |
| `integration` | EN | `reflection.py:371` | YES (enum) | deep reflection LLM | `CriterionAssessment.criterion` |
| `autonomy` | EN | `reflection.py:372` | YES (enum) | deep reflection LLM | `CriterionAssessment.criterion` |
| `reality_perception` | EN | `reflection.py:373` | YES (enum) | deep reflection LLM | `CriterionAssessment.criterion` |
| `environmental_mastery` | EN | `reflection.py:374` | YES (enum) | deep reflection LLM | `CriterionAssessment.criterion` |

**Distinct count B.10: 6** ✓

---

### B.11 Free-Form Fields (No Taxonomy — NOT Suitable for GLiNER Label Training)

| Field | Type | Source (file:line) | Status |
|---|---|---|---|
| `CoreValue.name` | `str` (free-form) | `identity.py:29` | No closed taxonomy; examples in code: `"honesty"`, `"competence"` |
| `KeyMoment.values_touched[]` | `list[str]` (free-form) | `experience.py:129–131` | LLM-generated; no enum |
| `KeyMoment.principles_confirmed[]` | `list[str]` (free-form) | `experience.py:132–134` | LLM-generated; no enum |
| `KeyMoment.principles_questioned[]` | `list[str]` (free-form) | `experience.py:135–137` | LLM-generated; no enum |
| `Eigenstate.dominant_themes[]` | `list[str]` (free-form) | `narrative.py:60` | LLM-generated; no enum |
| `Eigenstate.open_threads[]` | `list[str]` (free-form) | `narrative.py:55` | LLM-generated; no enum |
| `Eigenstate.unresolved_tensions[]` | `list[str]` (free-form) | `narrative.py:63` | LLM-generated; no enum |
| `AgentMemoryReport.self_reported_emotions[]` | `list[str]` (free-form) | `affect/models.py:64` | LLM/agent self-report; no enum |

---

### B.12 Continuous Affect Metrics (NOT label types — stored as floats)

**Source:** `src/atman/affect/models.py:25–43`  
**Producer:** NRC EmoLex + heuristics in `AffectDetector`  
**Note:** These are scalar signals, not classification labels.

| Signal | Range | Source (file:line) | Storage |
|---|---|---|---|
| `emotional_valence` | -1.0 to +1.0 | `experience.py:50–53`, `narrative.py:38–43` | `FeltSense.emotional_valence`, `Eigenstate.emotional_tone` |
| `emotional_intensity` | 0.0 to 1.0 | `experience.py:53–57`, `narrative.py:44–46` | `FeltSense.emotional_intensity`, `Eigenstate.emotional_intensity` |
| `cognitive_load` | 0.0 to 1.0 | `narrative.py:49–54` | `Eigenstate.cognitive_load` |
| `nrc_valence` | float | `affect/models.py:28` | `AffectMetrics.nrc_valence` |
| `sincerity_score` | -5 to +5 (int) | `affect/models.py:40–43` | `AffectMetrics.sincerity_score` |

---

### Bucket B Summary

| Sub-bucket | Closed? | Distinct count |
|---|---|---|
| B.1 EmotionalDepth | YES | 3 |
| B.2 HelpfulnessLevel | YES | 3 |
| B.3 MoralOrientation | YES | 4 |
| B.4 GoalHorizon | YES | 3 |
| B.5 GoalOwner | YES | 2 |
| B.6 Point A NER labels | YES | 13 |
| B.7 Point A classification labels | YES | 26 ⚠️ |
| B.8 Point K NER labels | YES | 4 |
| B.9 Point K classification labels | YES | 29 ⚠️ |
| B.10 JahodaCriterion | YES | 6 |
| B.11 Free-form value/narrative fields | NO | ∞ |
| **Total closed types** | | **93** ⚠️ FAR EXCEEDS 25 |

---

## Bucket C — PII

**Conclusion: PII detection is NOT IMPLEMENTED in the codebase.**

| What was checked | Source (file:line) | Finding |
|---|---|---|
| Any `pii` / `PII` symbol | `grep -rn pii src/` | NOT FOUND (zero matches) |
| Privacy adapter | any `privacy*.py` | NOT FOUND |
| Regex patterns for email/phone/SSN | any file | NOT FOUND |
| GLiNER PII labels | `gliner_minilm_adapter.py` | NOT FOUND |
| Sentry data scrubbing | `observability/scrubbing.py:16–41` | EXISTS — but this is *data exfiltration prevention*, not PII *detection or labeling* |

**What the Sentry denylist scrubs** (NOT PII detection — prevents data reaching SaaS logging):

| Category | Denylist keys | Source (file:line) |
|---|---|---|
| Fact content | `memory_content`, `memory_text`, `fact_payload`, `fact_content`, `content_excerpt` | `scrubbing.py:18–22` |
| Reflection/identity | `reflection_text`, `identity_payload`, `key_insight`, `user_journal` | `scrubbing.py:23–26` |
| LLM I/O | `embedding_input`, `rerank_documents`, `prompt`, `prompt_text`, `completion`, `response_text` | `scrubbing.py:27–33` |
| Numeric payloads | `embedding`, `vector` | `scrubbing.py:34–36` |
| Credentials | `api_key`, `authorization` | `scrubbing.py:37–40` |

**Distinct count Bucket C: 0** (no PII categories extracted, classified, or labeled)

---

## Distinct-Type Counts Per Bucket

| Bucket | Total closed types | Flag |
|---|---|---|
| A — Entities & Relations | 26 | ⚠️ just over 25 |
| B — Values, Identity, Affect | 93 | ⚠️⚠️ far exceeds 25 |
| C — PII | 0 | NOT IMPLEMENTED |

---

## DOC-VS-CODE Discrepancies

### D1: Fact-Relation Label Set

**Doc claims (`docs/archive/2026-05/MEMORY-ARCHITECTURE.md:41`):**
> `public.fact_relations` stores directed edges between facts: `led_to`, `confirms`, `contradicts`, `supports`

**Code (`src/atman/core/models/fact.py:172`):**
```python
relation_type: str = Field(min_length=1, description="Тип связи (например: caused_by, related_to)")
```
No constraint to the four doc-listed types. The only examples in live code are `led_to` (in `src/demo.py:85` and `src/test_cli.sh:41`) and `confirms` (indirectly via a dashboard query in `web_dashboard/pages/3_Chat.py:451`). `contradicts` and `supports` are NOT FOUND in any code path.

**Severity:** MEDIUM — `contradicts` / `supports` are doc-described but absent from code.

---

### D2: Entity-to-Entity Relations Not Mentioned in MEMORY-ARCHITECTURE.md

**Doc (`docs/archive/2026-05/MEMORY-ARCHITECTURE.md:41`):**
> Distinguishes `fact_relations` (fact graph) from `entity_relations` (named-entity graph) and `fact_entities` (entity mentions in facts)

**Code:** `entity_relations` table and `EntityRelation` model are fully implemented (`entity.py:77–104`, migration `0007_entity_links_and_relations.sql`). The doc mentions this table exists but does NOT describe what relation type labels it uses or that mREBEL produces them.

**Severity:** LOW — table exists, just under-documented.

---

### D3: 01-factual-memory-adapter.md — Embedding Not Required

**Doc (`docs/archive/2026-05/01-factual-memory-adapter.md`):**
> "Сохранить расширяемость под embeddings/graph memory, но не требовать их"  
> (Keep extensibility for embeddings, but don't require them)

**Code (`migrations/versions/0002_create_facts_table.sql:48`):**
> Embedding column: `halfvec(1024)` with HNSW index — implemented and required by `PostgresFactualMemory`. BGE-M3 model is called automatically on every `add_fact` (`adapters/memory/flag_embedding.py`).

**Severity:** LOW — design doc predates implementation; embeddings are now mandatory in the Postgres adapter.

---

### D4: `SYSTEM.md` and `CLAUDE.md` — Reality Anchor and Proactive Engine Listed as Implemented

**Doc (`docs/content/SYSTEM.md:19–80`):** Lists Reality Anchor and Proactive Engine as system components.  
**CLAUDE.md (current):** 
> **Не реализовано:** Reality Anchor, Proactive Engine, Skill Manager, Background Scheduler

**Code:** NOT FOUND — no `reality_anchor.py`, no `proactive_engine.py` in `src/atman/`. 

**Severity:** HIGH for GLiNER design — any labels tied to these subsystems should be marked "future, not currently produced".

---

### D5: `docs/archive/2026-05/MEMORY-ARCHITECTURE.md` — `confirms` Usage

**Doc:** Does not mention `confirms` as a fact-relation type (only `led_to`, `confirms`, `contradicts`, `supports`).  
**Code (`web_dashboard/pages/3_Chat.py:451`):** Uses `"confirms"` as a column query result key — but this column comes from a raw SQL query, not the domain model. Confirm whether this refers to `fact_relations.relation_type = 'confirms'` or a computed count column.

**Severity:** AMBIGUOUS — see AMBIGUOUS section below.

---

## AMBIGUOUS / Needs Human Decision

### AMB-1: Bucket B Far Exceeds GLiNER2 Label Budget

**Problem:** Bucket B has 93 distinct closed-type labels. GLiNER2 degrades significantly beyond ~25 labels per model.  
**Options:**
- Split into 2 adapters: Adapter B.1 (NER: 13+4=17 span labels) + Adapter B.2 (classification: 26+29=55 class labels — still too many)
- Collapse classification tasks: merge related emotion/confidence/agency signals into fewer meta-labels
- Move classification tasks out of GLiNER2 entirely (use a dedicated text-classification model instead)

**Human decision needed:** Which of these 93 labels are in scope for GLiNER2 fine-tuning vs. a separate classifier?

---

### AMB-2: values_touched — No Taxonomy Exists

**Problem:** `KeyMoment.values_touched` is `list[str]` with no closed set (`experience.py:129`). Prompts pass values through as free-form strings. Two examples in code: `"competence"`, `"honesty"` (from `prompts.py:252`).  
**Options:**
- Define a closed taxonomy for T1 (e.g., Schwartz basic values)
- Train GLiNER2 to extract arbitrary value-mention spans without a predefined label set
- Use LLM post-processing to normalise extracted spans to a taxonomy

**Human decision needed:** Is a closed value taxonomy required, or is open extraction acceptable?

---

### AMB-3: Entity-to-Entity Relation Labels — Open vs. Fixed Set

**Problem:** `EntityRelation.relation_type` is free-form (`entity.py:84`). mREBEL (`Babelscape/mrebel-large`) produces Wikidata-style relation labels (e.g., `spouse`, `employer`, `country of citizenship`). Reflection LLM produces snake_case labels (`colleague_of`, `lives_in`). These are not normalised to a common set.  
**Options:**
- Define a fixed relation vocabulary (e.g., top-N mREBEL outputs from training corpus)
- Accept any relation type and train GLiNER2 as open relation extraction
- Hybrid: enumerate ~15 common types, catch-all for the rest

**Human decision needed:** What is the target relation vocabulary for GLiNER2 fine-tuning?

---

### AMB-4: `confirms` in web_dashboard — Fact-Relation Type or Aggregation Column?

**Problem:** `web_dashboard/pages/3_Chat.py:451` references `"confirms"` as a result key. Unclear if this is a fact `relation_type = 'confirms'` stored in `fact_relations`, or a SQL aggregate column with a different meaning.  
**Human decision needed:** Verify whether `confirms` is an actual `fact_relations.relation_type` value in production data.

---

### AMB-5: Language Support — Labels Are All English

**Problem:** All label strings in `_POINT_A_NER_LABELS`, `_POINT_A_CLASSIFICATIONS`, `_POINT_K_NER_LABELS`, `_POINT_K_CLASSIFICATIONS` are English (`gliner_minilm_adapter.py:81–167`). However, input text is Russian (`user_language: "ru"` stored in `SessionExperience`).  
**Human decision needed:** For GLiNER2 fine-tuning on Russian text — should label strings remain English (current), be translated to Russian, or be bilingual?

---

### AMB-6: GLiNER Model Version

**Current model:** `urchade/gliner_multi-v2.1` (hardcoded at `gliner_minilm_adapter.py:231`).  
**Fine-tuning target from issue HLE-409:** GLiNER2 (multilingual).  
**Human decision needed:** Confirm target model ID for fine-tuning (e.g., `urchade/gliner_multi-v2.2`, or a custom fork). The adapter will need updating at `gliner_minilm_adapter.py:231`.

---

## NRC EmoLex Baseline (for Bucket B Seeding)

**Source:** `src/atman/affect/emolex/` — NRC EmoLex word lists  
**Used by:** `AffectDetector` to compute `nrc_valence`, `emotion_lexical_energy`  
**Relevance:** NRC provides 8 emotion channels + positive/negative. These are NOT currently used as GLiNER labels but could serve as seed data for training corpus annotation.

NRC emotions: `anger`, `anticipation`, `disgust`, `fear`, `joy`, `sadness`, `surprise`, `trust` — NOT FOUND as label strings in any adapter. They are used only for float-metric computation.

---

## Appendix: Complete Label Master List

```
BUCKET A — Entities & Relations (closed):
  EntityType: person, place, organization, object, topic, event, tool,
              health_condition, skill, value, principle              [11]
  FactEntityLink.role: subject, object, context, mentioned           [4]
  KeyMomentEntityLink.involvement: primary_subject, present,
              mentioned, evoked                                       [4]
  EntityRelation.learned_by: mrebel, rules, reflection, manual       [4]
  TriggerReason: anomaly, random_sample, self_report, divergence,
              emphasis, structural_marker, linguistic                 [7]
  TOTAL CLOSED: 30 (open: relation_type strings are ∞)

BUCKET B — Values, Identity, Affect (closed):
  EmotionalDepth: surface, meaningful, profound                       [3]
  HelpfulnessLevel: helpful, mixed, harmful                           [3]
  MoralOrientation: good, bad, neutral, mixed                         [4]
  GoalHorizon: short, medium, long                                    [3]
  GoalOwner: agent, user                                              [2]
  Point A NER: emotional anchor, value reference, principle invocation,
    uncertainty marker, hedge, intensifier, belief marker,
    boundary marker, topic anchor, relational reference,
    action intent, commitment, concession                            [13]
  Point A stance: committed, tentative, resistant, exploring,
    doubtful, dismissive                                              [6]
  Point A cognitive_mode: analytical, emotional, mixed, defensive     [4]
  Point A self_orientation: toward_self, toward_other, toward_task,
    toward_meta                                                       [4]
  Point A primary_emotion: neutral, anxious, frustrated, curious,
    warm, doubtful, committed, tired                                  [8]
  Point A cognitive_load_label: low, manageable, high, overwhelmed   [4]
  Point K NER: recurring theme, closure marker, opening marker,
    contradiction marker                                              [4]
  Point K agency_level: passive, reactive, proactive, initiating     [4]
  Point K confidence_in_self: low, moderate, high, inflated          [4]
  Point K trust_signal_category: building, stable, wavering, broken  [4]
  Point K boundary_event_category: none, respected, tested,
    crossed, enforced                                                 [5]
  Point K connection_quality: distant, functional, warm, deep        [4]
  Point K learning_signal: new_understanding, confirmed,
    rejected, confused                                               [4]
  Point K growth_indicator: regression, static, progress, breakthrough [4]
  JahodaCriterion: positive_self_attitude, growth_and_actualization,
    integration, autonomy, reality_perception, environmental_mastery  [6]
  TOTAL CLOSED: 93 ⚠️⚠️

BUCKET C — PII:
  NOT IMPLEMENTED                                                     [0]
```
