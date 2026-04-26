# Secrets Protection System

> **Version:** 1.0.0  
> **Status:** Design  
> **Priority:** Must-Have for v1.0

## Overview

memoryHub needs built-in defense against accidentally storing secrets (API keys, passwords, tokens, etc.).

## Architecture

### Detection Pipeline

```
Write Request
  ↓
[1] Regex Patterns (AKIA*, ghp_, Bearer, etc)
  ↓
[2] Entropy Analysis (Shannon entropy > 4.5 bits)
  ↓
[3] Heuristics (base64 length, special patterns)
  ↓
Risk Score (0.0 - 1.0)
  ↓
Decision: ALLOW | WARN | BLOCK | QUARANTINE
```

### Detection Patterns

**AWS Keys:** `AKIA[0-9A-Z]{16}`  
**GitHub:** `ghp_[a-zA-Z0-9_]{36,255}`  
**OpenAI:** `sk-(proj-)?[a-zA-Z0-9]{20,}`  
**JWT:** `eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+`  
**PEM Keys:** `-----BEGIN (RSA|OPENSSH|PRIVATE) KEY-----`  
**Credit Cards:** `\b(?:\d{4}[-\s]?){3}\d{4}\b`  

### Risk Scoring

```
score = max(
  regex_confidence,          # 0.0 - 1.0
  entropy_score * 0.8,      # 0.0 - 1.0, capped
  heuristic_flags * 0.6     # 0.0 - 1.0
)
```

**Action Thresholds:**
- `score > 0.9` → BLOCK immediately
- `0.7 < score ≤ 0.9` → WARN + allow with override
- `0.5 < score ≤ 0.7` → FLAG for review
- `score ≤ 0.5` → ALLOW

### Response Masking

When secret detected, mask it on read:

```json
// Raw stored (if somehow saved)
{ "content": "api_key=sk-1234567890abcdef..." }

// When retrieved
{ "content": "api_key=[REDACTED:openai_key]" }

// With prefix/suffix
{ "content": "api_key=sk_****...cdef [REDACTED]" }
```

## Configuration

```yaml
secrets_protection:
  enabled: true
  sensitivity: "strict"  # strict, moderate, permissive
  
  patterns:
    aws_keys: true
    github_tokens: true
    openai_keys: true
    jwt: true
    pem_keys: true
    credit_cards: true
    generic_secrets: true
  
  actions:
    block_threshold: 0.9
    warn_threshold: 0.7
    log_threshold: 0.5
    
  override_key: "${MEMORYHUB_SECRETS_OVERRIDE_HMAC}"
  whitelist: []  # patterns to ignore
  
  masking:
    enabled: true
    strategy: "redacted"  # redacted, partial, full
```

## Cleanup & Audit

### Database Scanning

```bash
# Find potential secrets
SELECT id, content, confidence 
FROM memories 
WHERE content ILIKE '%AKIA%' 
   OR content ILIKE '%ghp_%'
LIMIT 100;

# Mask them
UPDATE memories 
SET content = REGEXP_REPLACE(
  content, 
  'ghp_[a-zA-Z0-9_]{36,}',
  '[REDACTED:github_token]'
)
WHERE id IN (...);

# Log action
INSERT INTO audit_log (action, detail, ...) 
VALUES ('SECRET_MASKING', '...');
```

### Alerting

- High confidence secrets found → Immediate alert
- Trend: spike in detection attempts → investigate
- Masked secrets → track for monitoring

## Testing

```python
# Should BLOCK
test_cases_block = [
    "aws_key=AKIAIOSFODNN7EXAMPLE",
    "token=ghp_1234567890123456789012345678901234567890",
    "-----BEGIN RSA PRIVATE KEY-----",
    "Bearer eyJhbGc...",
]

# Should WARN (false positive risk)
test_cases_warn = [
    "base64string=aGVsbG8gd29ybGQ=",
    "random_id=7f3e8c2a9d1b4",
]

# Should ALLOW
test_cases_allow = [
    "user_email=john@example.com",
    "config_value=production",
]
```

---

**Implementation:** ~20-30 hours  
**Priority:** Must-have before v1.0 launch
