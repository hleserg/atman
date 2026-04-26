# Incident Response Plan

## Incident Classification

### P0 — CRITICAL
**Response Time:** Immediate (< 5 min)  
**Examples:** Data breach, key compromise, service down, mass unauthorized access

### P1 — HIGH
**Response Time:** < 30 min  
**Examples:** Unauthorized access (1 agent), secret leak, DDoS

### P2 — MEDIUM
**Response Time:** < 2 hours  
**Examples:** Failed backup, elevated error rates, anomaly detection trigger

### P3 — LOW
**Response Time:** < 24 hours  
**Examples:** Non-critical audit findings, performance degradation

## Detection & Alerting

### Monitors

```sql
-- Unauthorized access attempts
SELECT COUNT(*) as failures
FROM audit_log
WHERE action = 'AUTH_FAIL'
  AND ts > now() - interval '1 hour'
HAVING COUNT(*) > 10  -- ALERT if > 10 failures/hour
```

```sql
-- Bulk deletion
SELECT COUNT(*) as deletes
FROM audit_log
WHERE action = 'DELETE'
  AND ts > now() - interval '1 hour'
HAVING COUNT(*) > 100  -- ALERT if > 100 deletes/hour
```

```sql
-- Secret detection
SELECT COUNT(*) as secrets_found
FROM secrets_scan_log
WHERE ts > now() - interval '1 hour'
  AND confidence > 0.8
HAVING COUNT(*) > 5  -- ALERT if > 5 high-confidence secrets
```

## Response Playbooks

### Data Breach

1. **Detect:** Unauthorized access logs, failed/unusual queries
2. **Containment:**
   - Immediately revoke affected API keys
   - Activate database read-only mode
   - Snapshot current state for forensics
3. **Assessment:**
   - What data was accessed?
   - For how long?
   - By which agents?
4. **Recovery:**
   - Restore from clean backup
   - Re-encrypt with new keys
   - Resume operations

### Unauthorized Access (Agent X reading Agent Y's data)

1. **Detect:** audit_log shows cross-agent access
2. **Response:**
   - Revoke Agent X credentials immediately
   - Audit Agent Y's data for changes
   - Check if Agent X is compromised
3. **Mitigation:**
   - Generate new API key for Agent X
   - Re-verify Agent X identity/authorization
4. **Follow-up:**
   - Post-mortem analysis
   - Update RBAC rules if needed

### Key Compromise (API key leaked in GitHub)

1. **Detect:** gitleaks scan, HackerNews mention, our monitoring
2. **Immediate Action:**
   - Revoke leaked key (set is_active = 0)
   - Generate new key for affected agent
3. **Cleanup:**
   - Remove from git history (force push)
   - Scan S3/backups for same pattern
4. **Notify:**
   - Affected agent (brief)
   - Security team (full report)

### Secret Leak (Password found in memory)

1. **Detect:** Secrets detection system
2. **Mask:**
   - Automatically mask in database
   - Log incident with HMAC
3. **Cleanup:**
   - Scan for other instances
   - Check if in backups
4. **Alert:**
   - Operator review
   - Potential credential rotation needed

## Communication Templates

### P0 — Critical Incident

```
[CRITICAL] memoryHub Incident
Time: [timestamp]
Status: Investigating
Impact: [describe]
ETA: [estimated resolution]

Updates every 10 minutes.
```

### P1 — High Priority

```
[HIGH] memoryHub Alert
Incident: [description]
Severity: P1 (Response < 30 min)
Status: In Progress

Details: [...]
Action: [what we're doing]
```

## Post-Incident

1. **Document:**
   - What happened
   - When (start/end times)
   - Root cause
   - Impact assessment

2. **Post-Mortem Meeting (within 24 hours):**
   - Timeline
   - Contributing factors
   - Action items (prevent recurrence)
   - Owner assignments

3. **Follow-Up:**
   - Fix issues
   - Update runbooks
   - Improve monitoring

---

**Implementation:** 8-12 hours (scripts + automation + testing)  
**Priority:** Must-have before v1.0 launch
