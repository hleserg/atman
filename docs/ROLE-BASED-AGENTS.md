# Role-Based Agent System

## 7 Agent Roles

### 🔍 READER
- **Can:** GET /memory/*, GET /memory/search
- **Cannot:** Write, delete, modify
- **Use case:** Read-only clients, analytics agents

### ✍️ WRITER
- **Can:** POST /memory (with trust pipeline)
- **Cannot:** Delete, modify trust scores
- **Use case:** Agents that generate new facts, memories

### 🧹 CURATOR
- **Can:** Soft DELETE, REINDEX, mark as stale
- **Cannot:** Hard delete, modify confidence
- **Trigger:** low_confidence_count > 100 OR stale_facts > 50%
- **Use case:** Cleanup, archival, organization

### 📊 AUDITOR
- **Can:** GET /audit/*, GET /metrics/*, analysis
- **Cannot:** Write, delete, modify
- **Trigger:** recall_quality < 60% OR anomalies detected
- **Use case:** Quality monitoring, compliance

### 🔧 MAINTAINER
- **Can:** BACKUP, RESTORE, index optimization
- **Cannot:** Read/write memory, security decisions
- **Trigger:** Scheduled (daily 03:00) OR backup_age > 24h
- **Use case:** Operational maintenance, disaster recovery

### 📚 LEARNER
- **Can:** POST /feedback, update confidence scores
- **Cannot:** Delete, override decisions
- **Trigger:** hallucination_count > 5 OR correction signal received
- **Use case:** Feedback loop, credibility updates

### 🎼 ORCHESTRATOR
- **Can:** Schedule other roles, manage workflows
- **Cannot:** Execute privileged operations alone
- **Use case:** Workflow automation, coordinated actions

## Permissions Matrix

| Role | GET /memory | POST /memory | DELETE | GET /audit | POST /feedback |
|------|:---:|:---:|:---:|:---:|:---:|
| READER | ✅ | ❌ | ❌ | ❌ | ❌ |
| WRITER | ✅ | ✅ | ❌ | ❌ | ❌ |
| CURATOR | ✅ | ❌ | ✅ | ✅ | ❌ |
| AUDITOR | ✅ | ❌ | ❌ | ✅ | ❌ |
| LEARNER | ✅ | ❌ | ❌ | ✅ | ✅ |
| MAINTAINER | ❌ | ❌ | ❌ | ✅ | ❌ |
| ORCHESTRATOR | ❌ | ❌ | ❌ | ✅ | ❌ |

## Trigger-Based Execution

### Metrics that trigger roles

```yaml
CURATOR:
  triggers:
    - low_confidence_count > 100
    - stale_facts_percent > 50
    - audit_actions: [soft_delete, reindex]

AUDITOR:
  triggers:
    - recall_quality_trend down 20% (7 days)
    - anomaly_score > 0.8
    - coverage_gap detected

LEARNER:
  triggers:
    - hallucination_count > 5 (per day)
    - correction_signal received
    - credibility_decay detected

MAINTAINER:
  triggers:
    - Scheduled (daily 03:00)
    - backup_age > 24 hours
    - disk_usage > 80%
```

## Role Composition Rules

### ✅ Allowed Combinations
- `READER + LEARNER` (read and improve)
- `WRITER + LEARNER` (write and self-improve)
- `CURATOR + AUDITOR` (cleanup with oversight)
- `AUDITOR + ORCHESTRATOR` (monitoring + coordination)

### ❌ Forbidden Combinations
- `WRITER + CURATOR` (conflict of interest)
- `AUDITOR + MAINTAINER` (independent oversight)
- `LEARNER + MAINTAINER` (backup integrity)

## Autonomy Rules

```
1. Validate trigger condition
2. Check credentials (API key, role permissions)
3. Apply guardrails (safety limits)
4. Acquire lock (if needed)
5. Execute action (with rollback capability)
6. Log & monitor (audit trail)
```

**Guardrails:**
- CURATOR: Cannot delete facts with confidence > 0.9
- LEARNER: Cannot lower confidence below 0.1
- MAINTAINER: Cannot modify backups after 30 days

## Conflict Resolution

### Priority System
```
SAFETY > PERFORMANCE > AVAILABILITY
WRITER > CURATOR > LEARNER
```

### Lock Mechanism
```
SOFT:       Warn, continue (advisory)
HARD:       Block, retry later (required)
EXCLUSIVE:  Only one role active (critical ops)
```

### Voting (for high-risk operations)
```
If CURATOR wants to delete 1000+ facts:
  - AUDITOR validates (quality impact)
  - ORCHESTRATOR approves (timing)
  - Majority vote decides
```

## Monitoring & Observability

### Role Health Score (0-100)

```python
score = (
  success_rate * 50 +
  latency_score * 30 +
  error_count_penalty * 20
)
```

### Dashboard Metrics

```yaml
role_metrics:
  WRITER:
    - facts_written (daily)
    - avg_confidence (new facts)
    - hallucination_rate
  
  CURATOR:
    - facts_deleted
    - avg_confidence (before/after)
    - reindex_time
  
  LEARNER:
    - corrections_processed
    - credibility_updates
    - confidence_changes
```

### Alerting

- Role success rate < 95% → investigate
- Role latency spike > 2x baseline → check
- Role error rate > 5% → escalate

---

**Implementation:** ~12-14 hours for v1.1  
**Priority:** Should-have after v1.0 stabilizes
