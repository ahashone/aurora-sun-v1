# Data Protection Impact Assessment (DPIA)

**Document:** DPIA-AURORA-SUN-V1-001
**Version:** 1.1
**GDPR Reference:** Art. 35
**Last Updated:** 2026-02-14

---

## Review Log

| Date | Phase | Reviewer | Key Changes |
|------|-------|----------|-------------|
| **2026-02-14** | **Phase 5 completion** | Aurora Sun Development Team | 47 security findings fixed; encryption fail-closed (all errors deny access); webhook secret validation enforced; JWT hardened (algorithm pinning, audience validation); GDPR deletion improved (cascade delete across all stores); all ART_9 fields confirmed encrypted at rest |
| 2026-02-13 | Initial assessment | Aurora Sun Development Team | Initial DPIA created |

**Next review:** Before production deployment.

---

## 1. Project Overview

Aurora Sun V1 is an AI coaching system designed for neurodivergent people. It provides personalized coaching across three core pillars: Vision-to-Task, Second Brain, and Money Management.

### 1.1 Processing Characteristics Requiring DPIA

| Criterion | Present | Notes |
|-----------|---------|-------|
| Art. 9 Health Data Processing | **Yes** | Mental health, neurotype data |
| Systematic Profiling | **Yes** | Pattern detection, behavioral analysis |
| Automated Decision-Making | **Yes** | Coaching interventions based on behavioral data |
| Large-scale Processing | **Yes** | Multiple data categories including special categories |
| New Technologies | **Yes** | AI coaching with neurotype-specific interventions |

### 1.2 System Architecture Summary

- **3 Pillars:** Vision-to-Task, Second Brain, Money Management
- **3 Agents:** Aurora (orchestration), TRON (security), Avicenna (money)
- **6 Services:** PostgreSQL, Redis, Neo4j, Qdrant, Letta, Telegram
- **8+ Modules:** capture, planning, review, money, onboarding, etc.

---

## 2. Processing Operations & Purposes

### 2.1 Core Processing Activities

| Operation | Purpose | Legal Basis | Data Categories |
|-----------|---------|-------------|-----------------|
| **Vision-to-Task Coaching** | Transform user visions into actionable tasks | Explicit Consent (Art. 9(2)(a)) | SENSITIVE, ART.9 |
| **Second Brain Capture** | Store and retrieve personal information | Explicit Consent (Art. 9(2)(a)) | SENSITIVE |
| **Money Management** | Track transactions and budgets | Explicit Consent (Art. 9(2)(a)) | FINANCIAL |
| **Neurostate Assessment** | Evaluate burnout type, sensory load, channel dominance | Explicit Consent (Art. 9(2)(a)) | ART.9 |
| **Pattern Detection** | Identify behavioral patterns (motifs, habits, inertia) | Explicit Consent (Art. 9(2)(a)) | ART.9, SENSITIVE |
| **Automated Interventions** | Trigger coaching actions based on state assessment | Explicit Consent (Art. 9(2)(a)) | ART.9 |

### 2.2 Data Flows

```
User (Telegram)
    |
    v
Aurora (Intent Routing) --> NLI Classification
    |
    +--> Vision Module (goals/visions)
    +--> Planning Module (tasks)
    +--> Review Module (reflections)
    +--> Money Module (transactions)
    +--> Second Brain (captured items)
    |
    v
Letta (Memory/Coaching Transcripts) - ART.9 encrypted
Neo4j (Relationships) - ART.9/SENSITIVE encrypted
PostgreSQL (Structured Data) - Field-level encryption
Qdrant (Embeddings) - Derived, user-scoped
Redis (Session) - TTL-bound, transient
```

---

## 3. Necessity & Proportionality Assessment

### 3.1 Data Necessity by Category

| Data Type | Why Necessary | Proportionality |
|-----------|--------------|-----------------|
| **User Identity (name, telegram_id)** | Account creation, message delivery | Minimal: hashed identifier, no unnecessary fields |
| **Vision Content** | Core coaching: vision → task transformation | Essential: user's stated goals |
| **Goals & Key Results** | Task decomposition from vision | Essential: core value proposition |
| **Tasks** | Action tracking, accountability | Essential: core value proposition |
| **Daily Reflections** | Burnout detection, coaching adaptation | Essential: mental state monitoring |
| **Sensory Profile** | Neurotype-specific intervention delivery | Essential: AU/AH segmentation |
| **Masking Logs** | Burnout type identification | Essential: prevent autistic burnout |
| **Channel State** | AuDHD channel dominance detection | Essential: intervention selection |
| **Inertia Events** | Neurotype-specific inertia handling | Essential: AD/AU differentiation |
| **Transactions** | Financial tracking, budgeting | Essential: money management feature |
| **Beliefs** | Cognitive restructuring support | Essential: CBT-based coaching |

### 3.2 Minimum Data Principle

- **No aggregation:** Data stays user-scoped; no cross-user analytics
- **No retention without purpose:** Every data type has a defined retention period
- **Encryption by default:** SENSITIVE+ requires encryption at rest
- **Consent-gated:** No data collection before explicit consent (Onboarding Step 4)
- **Purpose limitation:** Each data type tied to specific module, no drift

---

## 4. Risks to Data Subjects

### 4.1 Privacy Risks

| Risk | Severity | Likelihood | Affected Data |
|------|----------|------------|---------------|
| Unauthorized access to health data | **High** | Low | ART.9 (BurnoutAssessment, SensoryProfile) |
| Re-identification from pattern data | **Medium** | Low | ART.9 (Motif, Belief) |
| Cross-referencing via embeddings | **Medium** | Low | Qdrant vectors |
| Inference attacks on encrypted data | **Low** | Very Low | All encrypted fields |

### 4.2 Security Risks

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| Database breach | **High** | Low | AES-256-GCM encryption at rest |
| Key compromise | **High** | Very Low | Per-user keys, key rotation |
| LLM provider data handling | **Medium** | Low | Transient processing only, DPA in place |
| Telegram platform risks | **Medium** | Medium | Platform ToS compliance, no sensitive data in messages |

### 4.3 Autonomy Risks (Coaching Influence)

| Risk | Severity | Likelihood | Description |
|------|----------|------------|-------------|
| Behavioral manipulation | **Medium** | Low | Automated interventions based on neurostate |
| Over-reliance on AI coach | **Medium** | Medium | Dependency risk, mitigated by autonomy-first design |
| Paternalistic interventions | **Low** | Low | System proposes, user decides (core principle) |
| Shutdown misclassification | **Medium** | Low | Autistic shutdown vs. disengagement - separate protocols |

### 4.4 Risk Summary

| Category | Overall Assessment |
|----------|-------------------|
| **Privacy** | Low-Medium with current measures |
| **Security** | Low with encryption layers |
| **Autonomy** | Medium - requires ongoing oversight |
| **Overall** | **Acceptable with mitigation measures in place** |

---

## 5. Measures to Address Risks

### 5.1 Encryption (GDPR Art. 32)

| Layer | Technology | Scope |
|-------|------------|-------|
| **Transport** | HTTPS (Caddy) | All external traffic |
| **Transport** | Tailscale | SSH access |
| **Storage** | Hetzner disk encryption | Underlying disks |
| **Application** | AES-256-GCM | All SENSITIVE/ART.9/FINANCIAL fields |
| **Field-Level** | Per-user keys | SENSITIVE data |
| **Field-Level** | Per-user + field salt | ART.9 data |
| **Field-Level** | 3-tier envelope | FINANCIAL data |

**Implementation:** `src/lib/encryption.py` - EncryptionService class

### 5.2 Consent Architecture (GDPR Art. 7, 9)

```
Onboarding Flow (Phase 1.1):
    |
    +-- Step 1: Language selection
    +-- Step 2: Name
    +-- Step 3: Working style inference
    +-- Step 4: CONSENT GATE (MANDATORY)
    |       +-- Plain language: What data we collect
    |       +-- Plain language: Why (coaching requires understanding patterns)
    |       +-- Plain language: What we do NOT do (sell, share, aggregate)
    |       +-- Plain language: Your rights (export, delete, withdraw)
    |       +-- Explicit "I agree" required (no pre-checked boxes)
    |       +-- Store: consent_given_at, consent_version, consent_language
    |
    +-- Step 5: Confirmation → Bot active
```

### 5.3 Data Classification

| Classification | Definition | Encryption | Example |
|---------------|-----------|-----------|---------|
| **PUBLIC** | No user data | None | Feature flags |
| **INTERNAL** | System data, non-identifiable | None | InterventionTrace (anonymized) |
| **SENSITIVE** | User-identifiable, personal | AES-256-GCM | User, Task, Goal, CapturedItem |
| **ART.9 SPECIAL** | Health, mental state, neurotype | AES-256-GCM + field salt | Belief, SensoryProfile, BurnoutAssessment |
| **FINANCIAL** | Money, transactions | AES-256-GCM + 3-tier | Transaction, BudgetState |

### 5.4 Access Controls

| Role | Access Level | Authentication |
|------|-------------|----------------|
| **User** | Own data only | Telegram user_id |
| **Admin (Ahash)** | All data | Telegram admin + Tailscale SSH |
| **System** | User data within function scope | Service-level scoping |
| **Sub-Processors** | Transient (API calls only) | DPA agreements |

### 5.5 Retention Policies

| Data Category | Retention | Basis |
|---------------|-----------|-------|
| User account | Active + 30 days post-deletion | Account recovery |
| Coaching transcripts | Active + 30 days | Memory consolidation |
| Transactions | Indefinite (user-controlled) | User utility |
| Neurostate data | 90 days rolling | Intervention relevance |
| Pattern/motif data | User-controlled | User utility |
| Intervention traces | 30 days | Security audit |

### 5.6 Data Subject Rights

| Right | Implementation | Response Time |
|-------|---------------|---------------|
| **Access (Art. 15)** | Export all user data via bot command | 30 days |
| **Rectification (Art. 16)** | Edit command for specific fields | 30 days |
| **Erasure (Art. 17)** | "Delete my data" command, key destruction | 30 days |
| **Restriction (Art. 18)** | "Pause tracking" mode | 30 days |
| **Portability (Art. 20)** | JSON export, structured format | 30 days |
| **Objection (Art. 21)** | "Stop intervention X" command | Immediate |

---

## 6. Data Categories (Table-Level Classification)

### 6.1 SENSITIVE

| Table | Encrypted Fields | Justification |
|-------|-----------------|----------------|
| User | `name`, `telegram_id` (HMAC-SHA256 hashed) | PII identifier |
| Vision | `content` | Personal goals |
| Goal | `title`, `key_results` | Personal goals |
| Task | `title` | Personal tasks |
| Motif | `label`, `signals` | Psychological patterns |
| CapturedItem | `content` | May contain personal data |

### 6.2 ART.9 SPECIAL CATEGORIES

| Table | Encrypted Fields | Justification |
|-------|-----------------|----------------|
| DailyPlan | `reflection_text`, `morning_energy`, `evening_energy` | Mental state indicators |
| Habit | `identity_statement`, `cue`, `craving`, `response`, `reward` | Identity + behavioral health |
| Belief | `text` | Mental health: core beliefs |
| SensoryProfile | `baseline_thresholds`, `current_load`, `recovery_activities` | Neurotype health data |
| MaskingLog | `masking_type`, `context`, `estimated_cost` | Mental health: masking burden |
| BurnoutAssessment | `burnout_type`, `severity`, `indicators` | Mental health: burnout state |
| ChannelState | `dominant_channel`, `signals` | Neurotype state |
| InertiaEvent | `inertia_type`, `trigger`, `resolved_via` | Neurotype behavioral data |

### 6.3 FINANCIAL

| Table | Encrypted Fields | Justification |
|-------|-----------------|----------------|
| Transaction | `amount_encrypted`, `description_encrypted` | Financial data (3-tier envelope) |
| BudgetState | `safe_to_spend`, `total_committed` | Financial data |

### 6.4 INTERNAL (Non-Sensitive)

| Table | Classification | Justification |
|-------|---------------|----------------|
| BudgetCategory | INTERNAL | Non-sensitive metadata |
| InterventionTrace | INTERNAL | Anonymized system data |

---

## 7. Sub-Processors

| Sub-Processor | Purpose | Data Sent | Classification | DPA Status |
|---------------|---------|-----------|----------------|------------|
| **Anthropic** (Claude Sonnet/Haiku) | Coaching, intent routing | User messages (transient) | SENSITIVE + ART.9 | Required |
| **OpenAI** (fallback) | Fallback LLM | User messages (transient) | SENSITIVE + ART.9 | Required |
| **Groq** (Whisper) | Voice transcription | Audio (transient) | SENSITIVE | Required |
| **Telegram** | User interface | Messages, user ID | SENSITIVE | Platform ToS |
| **Hetzner** | Infrastructure hosting | All data (encrypted at rest) | All | Required |
| **Langfuse** | LLM tracing | Prompt/response pairs (anonymized) | SENSITIVE | Required |

### 7.1 Sub-Processor Requirements

- All sub-processors must have DPA in place before data transfer
- Transient processing only (no persistent storage by LLM providers)
- Anonymization required for Langfuse traces
- Regular review of sub-processor compliance

---

## 8. Data Subject Rights Implementation

### 8.1 Access Right (Art. 15)

- **Command:** `/export` or "Export my data"
- **Format:** JSON (machine-readable) + Markdown (human-readable)
- **Contents:** All data from all tables, decrypted for user

### 8.2 Rectification Right (Art. 16)

- **Command:** "Edit [field]" or "/edit field:value"
- **Scope:** Any SENSITIVE/ART.9/FINANCIAL field
- **Verification:** User confirmation required

### 8.3 Erasure Right (Art. 17)

- **Command:** "Delete my data" or "/delete"
- **Process:**
  1. Mark user as "pending deletion"
  2. Destroy all encryption keys (`EncryptionService.destroy_keys()`)
  3. Delete all records from PostgreSQL
  4. Delete all nodes from Neo4j
  5. Delete embeddings from Qdrant
  6. Delete memories from Letta
  7. Mark user as deleted
- **Retention:** Minimal audit log (user_id, deletion_date) for legal compliance

### 8.4 Restriction Right (Art. 18)

- **Command:** "Pause tracking"
- **Effect:**
  - Neurostate assessments paused
  - Pattern detection suspended
  - Coaching interventions disabled
  - Data retention continues (not deleted)

### 8.5 Portability Right (Art. 20)

- **Same as Access Right** - JSON export available
- **Format:** Structured, machine-readable (JSON)
- **Delivery:** Via Telegram bot

### 8.6 Objection Right (Art. 21)

- **Command:** "Don't [intervention_type]" or "/object [intervention]"
- **Effect:** Specific intervention type disabled
- **Scope:** Automated interventions only (not core features)

---

## 9. Approval Section

### 9.1 Assessment Details

| Field | Value |
|-------|-------|
| **Document ID** | DPIA-AURORA-SUN-V1-001 |
| **Version** | 1.0 |
| **Assessment Date** | 2026-02-13 |
| **Assessor** | Aurora Sun Development Team |
| **Project** | Aurora Sun V1 |
| **Status** | **PENDING** |

### 9.2 Phase Transition Reviews

| Phase | Date | Assessor | Status |
|-------|------|----------|--------|
| Phase 1.0 | -- | -- | Initial Assessment |
| Phase 2.0 | -- | -- | Required |
| Phase 3.0 | -- | -- | Required |
| Phase 4.0 | -- | -- | Required |

### 9.3 Approval Signatures

| Role | Name | Date | Signature |
|------|------|------|-----------|
| **Data Protection Officer** | [TBD] | -- | _____________ |
| **Project Lead** | Ahash | -- | _____________ |
| **Security Lead** | [TBD] | -- | _____________ |

---

## 10. Review Schedule

- **Initial Assessment:** Phase 1.0 completion
- **Phase Transition:** Before each phase deployment
- **Annual Review:** Every 12 months from initial approval
- **Trigger Event:** Any significant architectural change, new data category, or new sub-processor

---

## 11. Appendices

### Appendix A: Encryption Key Management

```
Key Hierarchy:
    |
    +-- Master Key (HSM/secure storage)
    |       |
    |       +-- User Key Derivation (per-user HKDF)
    |               |
    |               +-- SENSITIVE Key (AES-256)
    |               +-- ART.9 Key (AES-256 + field salt)
    |               +-- FINANCIAL Key (3-tier envelope)
    |
    +-- Key Rotation: Annual (or upon user request)
    +-- Key Destruction: On erasure request (GDPR Art. 17)
```

### Appendix B: Breach Response

See ARCHITECTURE.md Section 10.3 for full breach notification procedure.

```
Timeline:
- Contain: 0-1 hour
- Assess: 1-24 hours
- Notify Authority: Within 72 hours (Art. 33)
- Notify Users: Without undue delay if high risk (Art. 34)
```

### Appendix C: Consent Versioning

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-13 | Initial consent gate implementation |

---

**Document Control:**
- Created: 2026-02-13
- Last Modified: 2026-02-13
- Next Review: Phase 1.0 completion
