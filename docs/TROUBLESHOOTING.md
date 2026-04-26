# memoryHub — Troubleshooting Guide

Quick diagnostics for common issues.  
See `ARCHITECTURE.md §12 Обработка ошибок и Graceful Degradation`.

---

## Quick Health Check

```bash
# Overall system
curl http://localhost:3000/v1/status | jq '.'

# Individual components
curl http://localhost:3000/v1/status | jq '.components | to_entries[] | select(.value.status != "healthy")'
```

---

## Trust Pipeline Issues

### Queue depth > 100 (WARNING threshold)

```bash
# Check queue
curl http://localhost:3000/v1/review/queue | jq '.total'

# See what's pending
curl "http://localhost:3000/v1/review/queue?limit=5" \
  -H "Authorization: Bearer ${MEMORYHUB_ADMIN_KEY}"

# Bulk approve from trusted agent (if appropriate)
curl -X POST http://localhost:3000/v1/review/bulk-approve \
  -H "Authorization: Bearer ${MEMORYHUB_ADMIN_KEY}" \
  -d '{"agent_id":"alfred","since":"2026-04-25T00:00:00Z"}'
```

**Cause:** Many records from low-credibility agent, or auto-approve threshold too high.  
**Fix:** Review and approve manually, or adjust `trust.human_review_threshold` in config.

### Quarantine growing unexpectedly

```bash
# Check quarantine size
curl http://localhost:3000/v1/quarantine | jq '.total'

# See high-severity items
curl "http://localhost:3000/v1/quarantine?severity=high" \
  -H "Authorization: Bearer ${MEMORYHUB_ADMIN_KEY}"

# Integrity violations specifically
curl "http://localhost:3000/v1/quarantine?reason=integrity_violation" \
  -H "Authorization: Bearer ${MEMORYHUB_ADMIN_KEY}"
```

**MH-002 (Integrity violation):** A record's HMAC checksum doesn't match. May indicate data tampering.  
Run manual rescan: `POST /v1/admin/rescan` (TODO: implement)

---

## Knowledge Graph Issues

### MH-003: Knowledge Graph unreachable

```bash
# Check KuzuDB process/file
ls -la ./data/kuzu/

# Component status
curl http://localhost:3000/v1/status | jq '.components.knowledge_graph'
```

**Behavior when KuzuDB is down:**  
Memory Store still works. New memories are stored but entities aren't extracted.  
Entity extraction will happen when KuzuDB recovers (backlog is processed).  
See `ARCHITECTURE.md §12 Graceful Degradation: Knowledge Graph`.

**Fix:** Check if data/kuzu/ directory exists and is readable. Restart service.

### Conflicts building up

```bash
# Unresolved conflicts
curl "http://localhost:3000/v1/graph/conflicts?resolved=false" \
  -H "Authorization: Bearer ${MEMORYHUB_API_KEY}" | jq '.total'
```

High conflict count may indicate:
- A specific agent is writing contradicting facts
- Entity extraction is linking unrelated entities
- Deliberate Memory Poisoning attempt

**Action:** Review conflicts and resolve them via Trust Pipeline.

---

## Rate Limiting Issues

### Getting 429 Too Many Requests

Check the `Retry-After` and `X-RateLimit-*` headers:

```bash
curl -v "http://localhost:3000/v1/memory/search?q=test" \
  -H "Authorization: Bearer ${MEMORYHUB_API_KEY}" 2>&1 | grep -E "(X-Rate|Retry)"
```

**Fix:** Reduce request frequency or request trust level upgrade for your agent.

---

## Database Issues

### SQLite integrity check

```bash
sqlite3 ./data/memoryhub.sqlite "PRAGMA integrity_check;"
# Expected: "ok"
```

### Database locked

If getting `database is locked` errors:
```bash
# Check WAL mode is enabled
sqlite3 ./data/memoryhub.sqlite "PRAGMA journal_mode;"
# Should return: "wal"

# If not: enable it
sqlite3 ./data/memoryhub.sqlite "PRAGMA journal_mode=WAL;"
```

### Disk space

```bash
du -sh ./data/memoryhub.sqlite ./data/kuzu/
df -h ./data/

# Cleanup archived records (older than 90 days)
# TODO: make maintenance-cleanup
```

---

## Backup & Recovery Issues

### Last backup > 24 hours ago (WARNING)

```bash
# Check backup status
curl http://localhost:3000/v1/status | jq '.components.dr_system'

# Check backup files
ls -la ./data/backups/

# Force backup
./scripts/backup.sh --type incremental
```

### MH-005: Backup verification failed

```bash
# Check backup integrity manually
sha256sum ./data/backups/incremental/memoryhub-*.enc | head -5

# Try to restore to temp dir for verification
./scripts/restore.sh --snapshot 2026-04-25T03:00:00Z \
  --dry-run --target /tmp/restore-test
```

---

## Telegram Alerts Not Arriving

```bash
# Check Telegram config
curl http://localhost:3000/v1/status | jq '.integrations.telegram'

# Verify bot token (should return bot info)
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"

# Test alert manually
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${ALERT_CHAT_ID}&text=memoryHub+test+alert"
```

---

## API Issues

### 401 Unauthorized

```bash
# Verify your key prefix
echo "${MEMORYHUB_API_KEY}" | cut -c1-20

# Key format should be: mhub_<env>_<prefix>_<token>
```

### 503 Service Unavailable with MH-001

Trust Pipeline queue is full. System is in degraded mode — new writes rejected.

```bash
# Queue size
curl http://localhost:3000/v1/review/queue | jq '.total'

# Bulk process (admin)
curl -X POST http://localhost:3000/v1/review/bulk-approve \
  -H "Authorization: Bearer ${MEMORYHUB_ADMIN_KEY}" \
  -d '{"all": true, "reason": "Emergency queue flush"}'
```

---

## Logs

```bash
# Docker
docker compose -f docker/docker-compose.yml logs -f api | grep -E "(ERROR|WARN)"

# Local binary
tail -f ./data/logs/memoryhub.log | grep -E "(ERROR|WARN)"

# Backup log
tail -f ./data/logs/backup.log
```

---

## Emergency Contacts

- **memoryHub system issues:** Alfred (AI assistant) or Сергей
- **Production server:** 192.168.1.51 (mac-mini)
- **Backup storage:** Backblaze B2 (see Bitwarden for credentials)

---

## See Also

- `ARCHITECTURE.md §12` — Graceful Degradation per component
- `ARCHITECTURE.md Appendix B` — Operational Runbook
- `docs/DEPLOYMENT.md` — Deployment guide
- `scripts/restore.sh` — Disaster recovery
