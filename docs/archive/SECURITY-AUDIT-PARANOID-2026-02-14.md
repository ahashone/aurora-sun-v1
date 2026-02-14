# Aurora Sun V1 — Paranoid Security Audit

**Date:** 2026-02-14
**Auditor:** Claude Code (Opus) — 5 parallel specialist agents + lead consolidation
**Scope:** Full codebase — 154 Python files, ~61,000 lines of code
**Classification:** CONFIDENTIAL — Owner (Ahash) only
**Mode:** READ-ONLY — No code changes made

---

## 1. Executive Summary

Aurora Sun V1 is an AI coaching application for neurodivergent people processing **GDPR Art. 9 special category health data** (neurotype profiles, mental health assessments, burnout indicators, sensory states, crisis signals). The system spans 5 databases (PostgreSQL, Redis, Neo4j, Qdrant, Letta), 3 AI agents, and integrates with external LLM providers (Anthropic, OpenAI, Groq).

This paranoid audit identified **47 unique findings** across all security domains:

| Severity | Count | Status |
|----------|-------|--------|
| **CRITICAL** | 12 | All unfixed |
| **HIGH** | 19 | All unfixed |
| **MEDIUM** | 11 | All unfixed |
| **LOW** | 5 | All unfixed |

**Overall Risk Assessment: HIGH** — Multiple critical findings allow authentication bypass, encryption defeat, injection attacks, and GDPR violations. The application **should not process real user health data** until CRITICAL findings are resolved.

**Top 3 Most Dangerous Findings:**
1. **FINDING-001:** Webhook secret loaded but never validated — anyone can inject fake Telegram updates
2. **FINDING-004:** Encryption silently falls back to plaintext on any exception — Art. 9 data stored unencrypted
3. **FINDING-002:** Hardcoded default JWT secret — complete authentication bypass

---

## 2. Threat Model

### 2.1 Asset Classification

| Asset | Classification | Location | Risk |
|-------|---------------|----------|------|
| Neurotype profiles (AD/AU/AH/NT/CU) | ART_9_SPECIAL | PostgreSQL | Extreme |
| Burnout assessments, sensory states | ART_9_SPECIAL | PostgreSQL | Extreme |
| Crisis signals (suicidal ideation) | ART_9_SPECIAL | In-memory + logs | Extreme |
| User coaching conversations | SENSITIVE | Redis, Letta | High |
| Knowledge graph (goals, beliefs, habits) | SENSITIVE | Neo4j, Qdrant | High |
| Financial data (Money module) | FINANCIAL | PostgreSQL (encrypted) | High |
| User names, Telegram IDs | SENSITIVE | PostgreSQL (should be encrypted/hashed) | High |
| API keys, master encryption key | INTERNAL | .env, keyring | Critical |
| Coaching effectiveness data | INTERNAL | PostgreSQL | Medium |

### 2.2 Attack Vectors

| Vector | Entry Point | Feasibility |
|--------|-------------|-------------|
| Fake Telegram updates | Webhook endpoint (no secret validation) | **Trivial** |
| JWT token forgery | REST API (hardcoded secret) | **Trivial** |
| Mock token endpoint | `/auth/token` (no authentication) | **Trivial** |
| Cypher injection | Neo4j queries via f-strings | Moderate |
| Prompt injection (future) | User messages → LLM context | Moderate |
| Knowledge graph poisoning | Second Brain captures → Qdrant/Neo4j | Moderate |
| Memory exhaustion DoS | Unbounded in-memory dicts | Easy |
| Encryption bypass | Dev mode fallback, plaintext on exception | Easy (config-dependent) |
| Data poisoning via RIA | False effectiveness/pattern reports | Moderate |
| Backup data theft | Unencrypted backup files on disk | Requires server access |

### 2.3 Attacker Profiles

| Profile | Motivation | Capabilities |
|---------|-----------|--------------|
| **External attacker** | Data theft, harassment of vulnerable users | HTTP requests, public endpoints |
| **Malicious user** | Data poisoning, system manipulation, impersonation | Telegram account, crafted messages |
| **Compromised dependency** | Supply chain attack, data exfiltration | Code execution within app context |
| **Insider with server access** | Data theft, surveillance | SSH, database access, log access |

---

## 3. Findings — CRITICAL

---

### FINDING-001: Webhook Secret Loaded But Never Validated
**Severity:** CRITICAL
**Category:** Authentication
**Files:** `src/bot/webhook.py:325-331`

**Description:** The Telegram webhook secret is loaded from environment but never actually passed to the Application builder. The `if webhook_secret:` block only logs a message — it never configures validation.

```python
# Line 325
webhook_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET")

# Line 328-331
builder = Application.builder().token(bot_token)
if webhook_secret:
    logger.info("Webhook secret token configured for request validation")
    # ← SECRET NEVER PASSED TO BUILDER
application = builder.build()
```

**Impact:** Any attacker can send fake Telegram updates to the webhook endpoint. They can impersonate any Telegram user, inject messages, trigger crisis workflows, exfiltrate data, or cause psychological harm to real users by manipulating their coaching context.

**Exploit:** `curl -X POST https://aurora-sun.example.com/webhook -d '{"update_id":1,"message":{"from":{"id":TARGET_USER},"text":"..."}}'`

---

### FINDING-002: Hardcoded Default JWT Secret Key
**Severity:** CRITICAL
**Category:** Authentication
**Files:** `src/api/auth.py:108-110`

**Description:** The AuthService falls back to a hardcoded string `"dev-secret-key-change-in-production"` if the environment variable is not set. The fallback appears twice (double `or`), making bypass guaranteed.

```python
self.secret_key: str = secret_key or os.getenv(
    "AURORA_API_SECRET_KEY", "dev-secret-key-change-in-production"
) or "dev-secret-key-change-in-production"
```

**Impact:** Complete authentication bypass. Any attacker can forge valid JWT tokens for any user by signing with this known default key. No environment variable is enforced at startup.

---

### FINDING-003: Mock Token Endpoint Without Authentication
**Severity:** CRITICAL
**Category:** Authentication
**Files:** `src/api/routes.py:103-119`

**Description:** The `/auth/token` endpoint returns tokens for any Telegram ID without verification. The comment acknowledges this is a placeholder but it's deployed code.

```python
@router.post("/auth/token")
async def get_auth_token(telegram_id: int) -> dict[str, Any]:
    """Get authentication token for a Telegram user."""
    # Placeholder - in production, verify Telegram user and issue JWT
    return {
        "access_token": f"mock_token_for_{telegram_id}",
        "token_type": "Bearer",
        "expires_in": 2592000,  # 30 days
    }
```

**Impact:** Any attacker can obtain a token for any user. Combined with FINDING-002, this provides complete account takeover for any user in the system.

---

### FINDING-004: Encryption Silently Falls Back to Plaintext on Exception
**Severity:** CRITICAL
**Category:** Data Protection / GDPR Art. 9
**Files:** `src/models/user.py:129-130`, `src/models/vision.py:112-113`, `src/models/goal.py:132-133,165-166`, `src/models/daily_plan.py:136-137`, `src/models/task.py`, `src/models/neurostate.py:154-155,250-251,364-365,397-398,568-569`

**Description:** Every encrypted field setter in every model catches `Exception` and silently stores data as plaintext. This defeats the entire encryption architecture.

```python
# user.py:121-130
try:
    encrypted = get_encryption_service().encrypt_field(
        value, int(self.id), DataClassification.SENSITIVE, "name"
    )
    setattr(self, '_name_plaintext', json.dumps(encrypted.to_db_dict()))
except Exception:
    setattr(self, '_name_plaintext', value)  # ← PLAINTEXT FALLBACK
```

**Impact:** Any encryption service failure (missing keys, corrupted keyring, import error, JSON error) causes ALL health data to be stored as readable plaintext in PostgreSQL. No audit trail of the failure. This applies to: user names, vision descriptions, goal descriptions, burnout assessments, sensory states, inertia events, masking logs, energy levels — all classified as SENSITIVE or ART_9_SPECIAL.

---

### FINDING-005: User Name Stored as Plaintext During Object Creation
**Severity:** CRITICAL
**Category:** Data Protection
**Files:** `src/models/user.py:117-120`

**Description:** When a User object is created (before DB INSERT assigns an ID), `self.id` is None, so the name setter stores plaintext. After INSERT, the plaintext remains — no post-INSERT encryption pass exists.

```python
if self.id is None:
    setattr(self, '_name_plaintext', value)  # PLAINTEXT — never re-encrypted
    return
```

**Impact:** Every new user's name is stored as plaintext in the database. The encryption was designed for `id`-based key derivation, but new users don't have IDs yet. There is no lifecycle hook to encrypt after INSERT.

---

### FINDING-006: Deterministic Dev Key Fallback in Encryption Service
**Severity:** CRITICAL
**Category:** Cryptography
**Files:** `src/lib/encryption.py:277-286`

**Description:** If `AURORA_DEV_MODE=1` is set, the master encryption key is a SHA-256 hash of a hardcoded string visible in source code.

```python
if os.environ.get("AURORA_DEV_MODE") == "1":
    return hashlib.sha256(b"aurora-sun-dev-key-DO-NOT-USE-IN-PRODUCTION").digest()
```

**Impact:** Anyone with source code access can compute the master key: `SHA256("aurora-sun-dev-key-DO-NOT-USE-IN-PRODUCTION")`. All user data encrypted under dev mode is trivially decryptable. If dev mode is accidentally enabled in production, ALL Art. 9 health data is compromised.

---

### FINDING-007: Deterministic Dev Hash Salt Fallback
**Severity:** CRITICAL
**Category:** Cryptography
**Files:** `src/lib/encryption.py:767-773`

**Description:** HashService falls back to a deterministic salt in dev mode, making HMAC-SHA256 hashes of Telegram IDs and IP addresses reversible.

```python
elif os.environ.get("AURORA_DEV_MODE") == "1":
    self._salt = hashlib.sha256(b"aurora-sun-dev-salt-DO-NOT-USE-IN-PRODUCTION").digest()
```

**Impact:** Telegram IDs (stored as HMAC hashes for pseudonymization) become rainbow-table-vulnerable. IP addresses in consent records become deanonymizable.

---

### FINDING-008: Cypher Injection via F-Strings in Neo4j Queries
**Severity:** CRITICAL
**Category:** Injection
**Files:** `src/services/knowledge/neo4j_service.py:226-228, 297, 366-374`

**Description:** Multiple Neo4j Cypher queries use f-strings to interpolate node types and labels, allowing Cypher injection.

```python
# Line 366-374
if node_types:
    labels = ":".join(str(nt) for nt in node_types)
    type_filter = f":{labels}"

query = (
    f"MATCH (n{type_filter} {{user_id: $user_id}}) "
    ...
    f"LIMIT {max_depth * 100}"
)
```

**Impact:** An attacker controlling `node_types` can inject arbitrary Cypher syntax, potentially accessing other users' data from the knowledge graph, modifying graph structure, or exfiltrating coaching data.

---

### FINDING-009: Raw User IDs in GDPR Logs
**Severity:** CRITICAL
**Category:** Information Disclosure / GDPR
**Files:** `src/lib/gdpr.py` — 15+ locations

**Description:** The GDPR service logs raw `user_id` integers throughout all operations (export, delete, freeze, unfreeze) despite a `hash_uid()` function existing in `src/lib/security.py`.

```python
logger.info(f"GDPR export completed for user {user_id}: {len(exports)} modules")
logger.info(f"GDPR deletion completed for user {user_id}: {deletion_report['overall_status']}")
logger.info(f"GDPR freeze completed for user {user_id}")
```

**Impact:** Log aggregation systems (ELK, CloudWatch, Datadog) store raw user IDs linked to GDPR operations. An attacker with log access can identify exactly which users requested deletion, export, or data freezes — correlating sensitive GDPR actions with specific individuals.

---

### FINDING-010: GDPR Deletion Cascade Incomplete Across 5 Databases
**Severity:** CRITICAL
**Category:** GDPR Art. 17
**Files:** `src/lib/gdpr.py:342-430`

**Description:** The `delete_user_data()` method iterates over 5 databases but catches exceptions per-database and continues. Partial deletions are marked as `"partial"` status — not failed. No atomic transaction spans all databases. Redis SCAN is not atomic (concurrent writes create new keys during scanning). Encryption key destruction is commented out ("handled separately").

```python
for module_name, module in self._modules.items():
    try:
        await module.delete_user_data(user_id)
    except Exception as e:
        logger.error(f"Module '{module_name}' deletion failed: {e}")
        # Continues to next module — partial deletion!
```

**Impact:** A user exercises Art. 17 right to erasure, but data remains in 1-4 databases. The system reports "partial" success. User believes data is deleted. Encrypted data remains with keys intact. Complete GDPR Art. 17 violation.

---

### FINDING-011: No DPA with LLM Sub-Processors
**Severity:** CRITICAL
**Category:** GDPR Art. 28
**Files:** `pyproject.toml` (dependencies), ARCHITECTURE.md (no sub-processor registry)

**Description:** The application integrates with Anthropic (Claude), OpenAI (GPT), and Groq (Whisper STT) as data processors. Mental health data may be sent to these APIs. No Data Processing Agreements (DPAs) are documented, no sub-processor registry exists, no data residency verification has been performed.

**Impact:** Sending Art. 9 health data to third-party LLM providers without DPAs violates GDPR Art. 28. The lack of a sub-processor registry means users cannot be informed about who processes their data (Art. 13/14 violation).

---

### FINDING-012: Database Ports Exposed Without TLS Enforcement
**Severity:** CRITICAL
**Category:** Infrastructure
**Files:** `docker-compose.prod.yml`

**Description:** Production Docker Compose exposes database ports (PostgreSQL 5432, Neo4j 7474/7687, Redis 6379) without enforcing TLS. Internal container traffic carries unencrypted Art. 9 health data.

**Impact:** Any attacker on the Hetzner network (or with container access) can sniff database traffic containing mental health data, neurotype profiles, crisis signals, and coaching conversations.

---

## 4. Findings — HIGH

---

### FINDING-013: Crisis Detection Blocked by Rate Limiting and Consent Gate
**Severity:** HIGH
**Category:** Safety / Architecture
**Files:** `src/bot/webhook.py:112-152`

**Description:** In the webhook handler, crisis detection (line 152) is called AFTER rate limiting (line 112) and consent gate (line 141). A comment at line 148 states "Crisis signals must NEVER be rate-limited or blocked" — but the code does exactly that.

**Impact:** A suicidal user who exceeds rate limits or hasn't completed onboarding will have their crisis message silently dropped. This is a **safety hazard** for vulnerable mental health users.

---

### FINDING-014: Unbounded In-Memory Rate Limit Dictionary (DoS)
**Severity:** HIGH
**Category:** Denial of Service
**Files:** `src/api/auth.py:111`

**Description:** `self._rate_limits: dict[int, RateLimitInfo] = {}` grows without bound. No eviction, no TTL, no size limit.

**Impact:** An attacker sending requests with different user IDs causes unbounded memory growth. After ~50K unique IDs, OOM kill crashes the entire application. No auto-recovery.

---

### FINDING-015: RBAC Decorators Trust Unvalidated Role Source
**Severity:** HIGH
**Category:** Authorization
**Files:** `src/infra/rbac.py:229-266`

**Description:** The `@require_permission` and `@require_role` decorators get the user's role from `kwargs.get("current_user_role")` without validating the source. If a caller passes `current_user_role=Role.ADMIN`, it's trusted implicitly.

**Impact:** Privilege escalation from USER to ADMIN if any API endpoint passes user-controlled data to decorated functions.

---

### FINDING-016: Custom JWT Implementation (Not PyJWT)
**Severity:** HIGH
**Category:** Cryptography
**Files:** `src/api/auth.py:137-221`

**Description:** JWT encoding/decoding is a custom implementation using manual base64 + HMAC. The code comments acknowledge "use PyJWT in production." Custom crypto is error-prone and may be vulnerable to signature-stripping, algorithm confusion, or timing attacks.

**Impact:** Potential token forgery or authentication bypass via implementation flaws in custom JWT code.

---

### FINDING-017: Unsanitized User Input in LLM Prompt Pipeline
**Severity:** HIGH
**Category:** Prompt Injection (Future)
**Files:** `src/services/coaching_engine_full.py:378-380,414,589-606`

**Description:** User messages are stored directly in `CoachingContext.message` without sanitization. While currently matched against hardcoded patterns, the infrastructure includes a PydanticAI tier (line 589-606) where `context.message` will be passed directly to Claude API.

**Impact:** When LLM integration is activated, prompt injection enables arbitrary LLM behavior manipulation, system prompt extraction, or coaching response hijacking for vulnerable users.

---

### FINDING-018: Knowledge Graph Content Injection via Second Brain
**Severity:** HIGH
**Category:** Data Poisoning / Indirect Prompt Injection
**Files:** `src/modules/second_brain.py:40-86,151`

**Description:** User-captured content (ideas, notes, insights) is stored verbatim in Neo4j and Qdrant without sanitization. Future knowledge retrieval (coaching_engine_full.py:661) will fetch this stored content and embed it in LLM prompts.

**Impact:** Delayed prompt injection — malicious content stored now will be executed when LLM integration is activated, affecting all future coaching interactions for that user.

---

### FINDING-019: Narrative Content Stored Without Sanitization
**Severity:** HIGH
**Category:** Data Poisoning
**Files:** `src/agents/aurora/narrative.py:253-264`

**Description:** `DailyNote.content` stores user input verbatim. Notes are included in chapters and serialized via `to_dict()`. When narrative context is fed to LLM for coaching generation, injection payloads execute.

---

### FINDING-020: No API Input Validation on REST Routes
**Severity:** HIGH
**Category:** Input Validation
**Files:** `src/api/routes.py:103-473`

**Description:** All REST API routes accept `dict[str, Any]` without Pydantic validation. No schema enforcement, no type checking, no field restrictions.

```python
@router.post("/visions")
async def create_vision(user_id: int, data: dict[str, Any]) -> dict[str, Any]:
    return {"id": 1, "user_id": user_id, **data}  # data passed as-is!
```

**Impact:** Type confusion, extra field injection, negative amount injection in financial module, business logic bypass.

---

### FINDING-021: Unencrypted In-Memory Crisis Log with Plaintext Fallback
**Severity:** HIGH
**Category:** Data Protection
**Files:** `src/services/crisis_service.py:318-320,627-675`

**Description:** Crisis events are stored in an unbounded in-memory dict. If encryption fails, crisis signals (including suicidal ideation) fall back to plaintext storage. The dict also has no eviction policy.

**Impact:** Art. 9 health data (crisis signals) stored unencrypted in memory. Unbounded growth leads to OOM. An attacker with process memory access reads sensitive mental health data.

---

### FINDING-022: ART_9 JSON Metadata Fields Not Encrypted
**Severity:** HIGH
**Category:** Data Protection
**Files:** `src/models/neurostate.py:297,430,436,499,607`

**Description:** Multiple JSON columns classified as ART_9_SPECIAL are stored as plaintext:
- `BurnoutAssessment.indicators` — burnout assessment data
- `ChannelState.channel_scores` — AuDHD channel dominance scores
- `ChannelState.supporting_signals` — behavioral signals
- `InertiaEvent.attempted_interventions` — autism inertia data
- `EnergyLevelRecord.behavioral_proxies` — energy inference data

**Impact:** Health assessment data readable in plaintext in PostgreSQL. GDPR Art. 9 violation.

---

### FINDING-023: Keyring Salt Storage with Silent Failures
**Severity:** HIGH
**Category:** Cryptography / Data Loss
**Files:** `src/lib/encryption.py:293-331`

**Description:** User-specific encryption salts are stored in keyring. If keyring is unavailable (containerized environment, no dbus), a NEW random salt is generated silently. Old salt is lost forever. User data encrypted with old salt becomes permanently undecryptable.

```python
except Exception:
    pass  # Best effort - no warning, no logging
```

**Impact:** Silent data loss. User's encrypted health data becomes unrecoverable if keyring service fails.

---

### FINDING-024: Master Key Validation Missing
**Severity:** HIGH
**Category:** Cryptography
**Files:** `src/lib/encryption.py:255-260`

**Description:** If `AURORA_MASTER_KEY` contains invalid base64, the error is silently caught and the system falls through to keyring or dev mode. No validation that the decoded key is exactly 32 bytes.

**Impact:** Typo in master key causes silent fallback to potentially insecure key source. Corrupted keys go undetected.

---

### FINDING-025: Effectiveness Data Manipulation for DSPy Poisoning
**Severity:** HIGH
**Category:** Data Poisoning
**Files:** `src/services/effectiveness.py:40-100`, `src/services/dspy_optimizer.py:73-97`

**Description:** Users can report false positive outcomes (TASK_COMPLETED, PATTERN_BROKEN) without verification. These feed into DSPy optimization traces that train the system. False data propagates to all users of the same segment.

**Impact:** Deployment of ineffective or harmful interventions to entire neurotype segments via poisoned training data.

---

### FINDING-026: Pattern Detection Data Poisoning
**Severity:** HIGH
**Category:** Data Poisoning
**Files:** `src/services/pattern_detection.py:39-69`

**Description:** `DetectedCycle` accepts user-submitted evidence and confidence scores without validation. False patterns feed into RIA proposals affecting all segment users.

---

### FINDING-027: Crisis Signal Abuse (Alert Fatigue)
**Severity:** HIGH
**Category:** Safety / Abuse
**Files:** `src/services/crisis_service.py:150-200`

**Description:** No rate limiting on crisis detection. An attacker can submit 1000s of false crisis signals, flooding admin notifications. Alert fatigue causes real crises to be ignored.

**Impact:** Real suicidal users may not receive timely intervention because admin is desensitized by false alarms.

---

### FINDING-028: Health Check Information Disclosure
**Severity:** HIGH
**Category:** Information Disclosure
**Files:** `src/infra/health.py:73-79`, `src/api/routes.py:86-100`

**Description:** Unauthenticated `/health` endpoint returns version info and detailed service status. Error messages may include database credentials.

---

### FINDING-029: Dependencies Not Pinned to Exact Versions
**Severity:** HIGH
**Category:** Supply Chain
**Files:** `pyproject.toml:9-51`

**Description:** Most dependencies use `>=` ranges. Pre-release dependencies (`pydantic-ai>=0.0.8`, `langgraph>=0.0.20`) have no stability guarantees. A compromised upstream version is auto-installed on next deploy.

---

### FINDING-030: Missing Startup Secrets Validation
**Severity:** HIGH
**Category:** Configuration
**Files:** `.env.example`

**Description:** No mechanism verifies that required secrets (AURORA_MASTER_KEY, AURORA_HMAC_SECRET, AURORA_API_SECRET_KEY, etc.) are set to non-empty, cryptographically random values before the application starts.

---

### FINDING-031: Sensitive Data in Application Logs
**Severity:** HIGH
**Category:** Information Disclosure
**Files:** `src/api/auth.py:134`, `src/services/crisis_service.py:332-383`, `src/lib/gdpr.py` (multiple)

**Description:** Raw user IDs logged in auth service. Crisis signals (suicidal ideation text) logged in plaintext. JWT tokens are base64 plaintext (not encrypted), so if logged during errors, all claims are immediately readable.

---

## 5. Findings — MEDIUM

---

### FINDING-032: Callback Data Injection in Onboarding
**Severity:** MEDIUM
**Category:** State Manipulation
**Files:** `src/bot/onboarding.py:387-425`

**Description:** Callback data uses `startswith()` matching and `replace()` extraction. While allowlists exist (mitigating factor), combined with FINDING-001 (no webhook secret), an attacker can craft arbitrary callback data.

---

### FINDING-033: Onboarding State Validation Missing
**Severity:** MEDIUM
**Category:** Business Logic
**Files:** `src/bot/onboarding.py:236-257`

**Description:** No server-side validation of state transitions. A user could manipulate Redis to jump from LANGUAGE to COMPLETED, bypassing the consent gate entirely.

**Impact:** GDPR consent bypass via state machine manipulation.

---

### FINDING-034: Session Metadata Not Encrypted
**Severity:** MEDIUM
**Category:** Data Protection
**Files:** `src/models/session.py:77`

**Description:** Session state and metadata stored as plaintext JSON despite potentially containing sensitive coaching context.

---

### FINDING-035: No Encryption Key Rotation Verification
**Severity:** MEDIUM
**Category:** Cryptography
**Files:** `src/lib/encryption.py:658-700`

**Description:** `rotate_key()` increments version for new operations but provides no mechanism to re-encrypt existing data. Compromised old keys still decrypt all historical data.

---

### FINDING-036: Backup Files Not Encrypted
**Severity:** MEDIUM
**Category:** Data Protection
**Files:** `src/infra/backup.py:105-128`

**Description:** `encrypt_backups=True` parameter is accepted but never implemented. PostgreSQL dumps stored as uncompressed SQL on disk.

---

### FINDING-037: SSRF in Health Check HTTP Calls
**Severity:** MEDIUM
**Category:** SSRF
**Files:** `src/infra/health.py:370-372`, `src/infra/backup.py:383-387`

**Description:** HTTP requests to configurable URLs (Qdrant, Letta) with no allowlist validation. If URLs are attacker-controlled, internal network scanning is possible.

---

### FINDING-038: Path Traversal in Backup Filenames
**Severity:** MEDIUM
**Category:** Path Traversal
**Files:** `src/infra/backup.py:164-168`

**Description:** `backup_name` parameter is not sanitized with `sanitize_path()`. An attacker controlling this parameter could write files outside the intended backup directory.

---

### FINDING-039: Rate Limit Configuration Too Permissive
**Severity:** MEDIUM
**Category:** Configuration
**Files:** `src/lib/security.py:301-331`

**Description:** API tier allows 100 req/min (1.67 req/sec) — sufficient for large-scale scraping. No rate limiting on webhook endpoint. No cost-based rate limiting integrated with LLM cost limiter.

---

### FINDING-040: Consent Text Hash Not User-Verifiable
**Severity:** MEDIUM
**Category:** GDPR
**Files:** `src/models/consent.py:609-614`

**Description:** Consent records store SHA-256 hash of consent text but not the text itself. GDPR exports include the hash but users cannot verify what they consented to.

---

### FINDING-041: GDPR Export Incomplete Without Verification
**Severity:** MEDIUM
**Category:** GDPR Art. 15
**Files:** `src/lib/gdpr.py:223-340`

**Description:** If any database export fails, errors are logged but export continues. User receives incomplete data without knowing. No record count comparison, no checksums, no completeness verification.

---

### FINDING-042: Qdrant Backup Uses HTTP Instead of HTTPS
**Severity:** MEDIUM
**Category:** Transport Security
**Files:** `src/infra/backup.py:363,449`

**Description:** Qdrant backup API calls use `http://localhost:6333` by default. Vector embeddings transmitted unencrypted.

---

## 6. Findings — LOW

---

### FINDING-043: Deterministic Field Salt Derivation
**Severity:** LOW
**Files:** `src/lib/encryption.py:386-388`

**Description:** Field salts derived from field name (SHA-256) instead of random. Reduces security margin against multi-field correlation attacks.

---

### FINDING-044: CI/CD Security Scans Not Enforced
**Severity:** LOW
**Files:** `.github/workflows/ci.yml:102-126`

**Description:** Bandit security scan uses `|| true` — failures don't break the build. Security findings accumulate without enforcement.

---

### FINDING-045: HSTS Without Preload Registration
**Severity:** LOW
**Files:** `src/infra/middleware.py:98-100`

**Description:** HSTS header includes `preload` directive but without actual HSTS preload list registration, first request remains vulnerable to downgrade attacks.

---

### FINDING-046: Retention Policy Magic Numbers
**Severity:** LOW
**Files:** `src/lib/gdpr.py:63-77`

**Description:** Retention policy uses `-1` for "indefinite" with unclear semantics. Could lead to data never being cleaned up.

---

### FINDING-047: RIA Cycle Log Not Tamper-Protected
**Severity:** LOW
**Files:** `src/services/ria_service.py:116-141`

**Description:** RIA cycle metrics stored without integrity protection. An attacker with database access could falsify learning metrics.

---

## 7. Abuse Scenario Assessment

| Scenario | Possible? | Severity | Entry Point | Notes |
|----------|-----------|----------|-------------|-------|
| **Fake Telegram updates** | YES | CRITICAL | Webhook (FINDING-001) | Trivial — no secret validation |
| **User impersonation** | YES | CRITICAL | JWT (FINDING-002,003) | Trivial — hardcoded secret + mock endpoint |
| **Admin impersonation** | YES | HIGH | RBAC (FINDING-015) | If `current_user_role` is caller-controlled |
| **Cost explosion** (10K LLM calls) | YES | HIGH | Webhook/API | Rate limits exist but too permissive |
| **Crisis alert flooding** | YES | HIGH | Webhook (FINDING-027) | No rate limit on crisis detection |
| **RIA/DSPy poisoning** | YES | HIGH | Effectiveness API (FINDING-025,026) | False outcomes poison training |
| **Knowledge graph poisoning** | YES | HIGH | Second Brain (FINDING-018) | Delayed prompt injection |
| **DoS via memory exhaustion** | YES | HIGH | API (FINDING-014) | Unbounded dicts in auth, crisis, TRON |
| **Cross-user data leakage** | PARTIAL | MEDIUM | Neo4j (FINDING-008) | Via Cypher injection |
| **Backup data theft** | YES | MEDIUM | Server SSH (FINDING-036) | Unencrypted backup files |
| **Consent bypass** | YES | MEDIUM | State machine (FINDING-033) | Redis manipulation |
| **Onboarding manipulation** | YES | MEDIUM | Callback injection (FINDING-032) | Via fake Telegram updates |

---

## 8. GDPR Compliance Status

| Article | Requirement | Status | Finding(s) |
|---------|-------------|--------|------------|
| **Art. 5(1)(f)** | Integrity and confidentiality | **VIOLATED** | FINDING-004,005,006,022,034 |
| **Art. 7** | Consent conditions | **AT RISK** | FINDING-033,040 |
| **Art. 9** | Special category data protection | **VIOLATED** | FINDING-004,006,022 |
| **Art. 13/14** | Information to data subject | **VIOLATED** | FINDING-011 (no sub-processor registry) |
| **Art. 15** | Right of access | **AT RISK** | FINDING-041 |
| **Art. 17** | Right to erasure | **VIOLATED** | FINDING-010 |
| **Art. 25** | Data protection by design | **AT RISK** | FINDING-004,005 (plaintext fallbacks) |
| **Art. 28** | Sub-processor agreements | **VIOLATED** | FINDING-011 |
| **Art. 32** | Security of processing | **VIOLATED** | FINDING-002,006,012,036 |
| **Art. 33** | Breach notification | **MISSING** | No incident response plan documented |
| **Art. 35** | DPIA | **INCOMPLETE** | DPIA not updated at phase transitions |

---

## 9. Prioritized Recommendations

### Tier 1: BEFORE ANY USER DATA (Block deployment)

| # | Action | Findings Addressed |
|---|--------|--------------------|
| 1 | **Validate webhook secret** — pass secret to Application builder, reject unsigned updates | FINDING-001 |
| 2 | **Remove hardcoded JWT secret** — require env var, fail startup if not set | FINDING-002,030 |
| 3 | **Remove mock token endpoint** — implement proper Telegram user verification | FINDING-003 |
| 4 | **Remove plaintext fallbacks** — fail loudly on encryption failure, never store plaintext | FINDING-004,005 |
| 5 | **Remove dev key/salt fallbacks** — fail if keys not available in non-dev mode | FINDING-006,007 |
| 6 | **Parameterize Neo4j queries** — replace all f-string Cypher with parameter binding | FINDING-008 |
| 7 | **Move crisis detection before rate limiting** — in webhook handler flow | FINDING-013 |
| 8 | **Hash user IDs in all logs** — use existing `hash_uid()` everywhere | FINDING-009,031 |
| 9 | **Add startup secrets validation** — verify all env vars set and non-empty | FINDING-030 |
| 10 | **Enforce TLS on all database connections** | FINDING-012 |

### Tier 2: WITHIN 1 WEEK (High priority)

| # | Action | Findings Addressed |
|---|--------|--------------------|
| 11 | Replace unbounded in-memory dicts with bounded LRU/Redis | FINDING-014,021 |
| 12 | Encrypt all ART_9 JSON metadata fields | FINDING-022 |
| 13 | Implement atomic GDPR deletion across all 5 databases | FINDING-010 |
| 14 | Add Pydantic validation to all REST API routes | FINDING-020 |
| 15 | Use PyJWT library instead of custom JWT implementation | FINDING-016 |
| 16 | Add input sanitization for all user content before LLM context | FINDING-017,018,019 |
| 17 | Document DPAs with LLM sub-processors | FINDING-011 |
| 18 | Add rate limiting to token endpoint and webhook | FINDING-014,027,039 |

### Tier 3: WITHIN 1 MONTH (Before production)

| # | Action | Findings Addressed |
|---|--------|--------------------|
| 19 | Pin all dependencies to exact versions, add `pip-audit` to CI | FINDING-029 |
| 20 | Implement backup encryption | FINDING-036,042 |
| 21 | Add key rotation with re-encryption workflow | FINDING-035 |
| 22 | Implement server-side onboarding state validation | FINDING-033 |
| 23 | Store user salts in DB as backup (encrypted with master key) | FINDING-023 |
| 24 | Validate master key format on load (must be exactly 32 bytes) | FINDING-024 |
| 25 | Enforce Bandit in CI (remove `|| true`) | FINDING-044 |
| 26 | Add data outcome verification for effectiveness reports | FINDING-025,026 |
| 27 | Include consent text in GDPR exports (alongside hash) | FINDING-040 |
| 28 | Add export completeness verification | FINDING-041 |

---

## 10. Appendices

### Appendix A: Files Audited

**Manually reviewed (lead auditor):**
- `src/bot/webhook.py` — Telegram entry point
- `src/api/auth.py` — REST API authentication
- `src/lib/encryption.py` — Core encryption service
- `src/lib/security.py` — Input sanitization, rate limiting
- `src/lib/gdpr.py` — GDPR compliance
- `src/infra/rbac.py` — Role-based access control
- `src/infra/middleware.py` — Security headers, cost limiting
- `src/services/knowledge/neo4j_service.py` — Knowledge graph
- `src/services/coaching_engine.py` — Basic coaching engine
- `src/services/coaching_engine_full.py` — Full coaching engine
- `src/services/ria_service.py` — Self-learning agent

**Agent-reviewed (5 parallel specialists):**
- All 154 Python files in `src/`
- `docker-compose.prod.yml`
- `pyproject.toml`
- `.env.example`
- `.github/workflows/ci.yml`
- All model files (`src/models/*.py`)
- All service files (`src/services/*.py`)
- All infrastructure files (`src/infra/*.py`)
- All module files (`src/modules/*.py`)
- All agent files (`src/agents/**/*.py`)

### Appendix B: Audit Methodology

1. **Reconnaissance:** File count, line count, dependency inventory
2. **5 Parallel Specialist Agents:**
   - Agent 1: Authentication, Input Validation, Injection (15 findings)
   - Agent 2: Encryption, Data Protection, Logging (19 findings)
   - Agent 3: LLM/AI Risks, Prompt Injection (15 findings)
   - Agent 4: API Security, Rate Limiting, Abuse (8 findings)
   - Agent 5: Infrastructure, Dependencies, Compliance (20 findings)
3. **Lead Deep-Dive:** Manual review of 11 critical files
4. **Consolidation:** Deduplication, severity normalization, cross-referencing

### Appendix C: What Was NOT Audited

- Server configuration (Caddy, fail2ban, Tailscale) — requires SSH access
- Live network traffic — requires runtime environment
- Penetration testing — read-only audit
- Third-party service configurations (Hetzner, Telegram API settings)
- Database contents — no live database access
- Secret values — only structure and handling audited

---

*End of Paranoid Security Audit. No code was modified during this audit.*
*Report location: `docs/archive/SECURITY-AUDIT-PARANOID-2026-02-14.md`*
