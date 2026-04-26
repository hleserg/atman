# Data Classification System

## Classification Levels

### 🟢 PUBLIC (Level 0)
- **Access:** Any authenticated agent
- **Encryption:** Database-level (default)
- **Retention:** Standard
- **Examples:** Public entities, shared knowledge, general facts

### 🟡 INTERNAL (Level 1)
- **Access:** Agents within same owner/team
- **Encryption:** Content-level AES-256-GCM
- **Retention:** Per policy (default 2 years)
- **Examples:** Team memories, shared insights, agent interactions

### 🔴 CONFIDENTIAL (Level 2)
- **Access:** Only data owner
- **Encryption:** Per-record DEK, full encryption
- **Retention:** Per policy with explicit deletion
- **Audit:** All reads logged with HMAC
- **Examples:** Personal data, sensitive conversations, PII

### ⚫ SECRET (Level 3)
- **Access:** Only vault_read role
- **Encryption:** Maximum (HSM if available)
- **Retention:** TTL 7-30 days, hard delete
- **Audit:** All operations logged
- **Examples:** API keys, passwords, tokens, private keys

## Auto-Classification Rules

1. **Secret Detection** (highest priority)
   - Regex patterns + entropy → SECRET
   
2. **Explicit Tag**
   - `#confidential` → CONFIDENTIAL
   - `#secret` → SECRET
   
3. **Source-based**
   - operator_input → min CONFIDENTIAL
   - api_write → INTERNAL
   
4. **Content Analysis**
   - Contains PII → CONFIDENTIAL
   - Contains personal data → CONFIDENTIAL
   
5. **Default**
   - New memory → INTERNAL
   - Shared memory → PUBLIC

## Handling Per Level

| Aspect | PUBLIC | INTERNAL | CONFIDENTIAL | SECRET |
|--------|:---:|:---:|:---:|:---:|
| Encryption | DB | Content | Per-record | Per-record + HSM |
| Key Rotation | Standard | Standard | Monthly | Per-use |
| Backup | Yes | Yes | Yes | Separate |
| Audit | Summary | Full | Full | Strict |
| TTL | None | 2yr | Explicit | 7-30d |
| Access Log | No | No | Yes | Yes |

## Implementation Tasks

1. **DB Schema** (~1 hour)
   - Add classification_level column
   - Add classification_timestamp
   
2. **Auto-Classifier** (~2 hours)
   - Implement rule engine
   - Integration with write middleware

3. **Access Control** (~1.5 hours)
   - Filter results based on agent role
   - Enforce visibility rules

4. **Audit & TTL** (~1 hour)
   - Hard delete for SECRET after TTL
   - Audit trail for downgrades

---

**Estimated effort:** 5.5 hours  
**Priority:** Must-have for v1.0
