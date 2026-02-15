# Sub-Processor Registry

> **Document Type:** Reference (Active)
> **Last Updated:** 2026-02-15
> **Owner:** Aurora Sun V1 Architecture
> **Reference:** ARCHITECTURE.md Section 10

---

## Overview

This document tracks all third-party processors that handle user data in the Aurora Sun V1 system. Every sub-processor must be documented here before being used in production.

**GDPR Compliance:** All sub-processors handling EU user data require a Data Processing Agreement (DPA) in place before processing begins.

---

## Sub-Processor Registry

| Sub-Processor | Purpose | Data Sent | Classification | DPA Required | Jurisdiction |
|--------------|---------|-----------|---------------|--------------|--------------|
| **Anthropic** (Claude Sonnet/Haiku) | Primary LLM for coaching, intent routing, coaching prompts | User messages (transient, not stored by provider) | SENSITIVE + ART. 9 | Yes | USA (SCCs in place) |
| **OpenAI** (GPT-4o Mini) | Fallback LLM when Anthropic unavailable | User messages (transient) | SENSITIVE + ART. 9 | Yes | USA (SCCs in place) |
| **Groq** (Whisper) | Voice transcription for audio input | Audio data (transient) | SENSITIVE | Yes | USA |
| **Telegram** | User interface, message delivery, bot interaction | Messages, user ID, basic profile info | SENSITIVE | Platform ToS | UAE / Russia / London |
| **Hetzner** | Infrastructure hosting (virtual machines, block storage) | All data at rest (encrypted) | SENSITIVE + ART. 9 + FINANCIAL | Yes | Germany (EU) |
| **Langfuse** | LLM tracing, observability, prompt management | Prompt/response pairs | SENSITIVE (must be anonymized) | Yes | EU (Germany) |

---

## Sub-Processor Details

### Anthropic (Claude Sonnet/Haiku)

- **Provider:** Anthropic PBC
- **Purpose:** Primary LLM for all coaching interactions, intent classification, and prompt generation
- **Data Classification:** SENSITIVE + ART. 9 (health-related conversations)
- **Data Flow:** User messages sent via API → processed → response returned → **not stored** by Anthropic
- **DPA Status:** Required - Pending Signature. Must be signed before processing real user Art. 9 data. Review Anthropic's DPA terms at [anthropic.com/legal](https://www.anthropic.com/legal)
- **Anonymization:** Messages may contain pseudonymized user identifiers. No PII should be sent.
- **Retention:** Transient only. No persistent storage by provider.

### OpenAI (Fallback LLM)

- **Provider:** OpenAI LLP
- **Purpose:** Fallback LLM when Anthropic is unavailable or rate-limited
- **Data Classification:** SENSITIVE + ART. 9 (health-related conversations)
- **Data Flow:** Same as Anthropic - transient API calls
- **DPA Status:** Required - Pending Signature. Must be signed before processing real user Art. 9 data. Uses OpenAI's DPA for Enterprise.
- **Anonymization:** Same rules as Anthropic - no PII in prompts.
- **Retention:** Transient only.

### Groq (Whisper)

- **Provider:** Groq LP
- **Purpose:** Fast voice transcription for audio messages from users
- **Data Classification:** SENSITIVE (voice biometric data)
- **Data Flow:** Audio file → Whisper API → transcript returned
- **DPA Status:** Required - Pending Signature. Must be signed before processing real user Art. 9 data. Verify Groq's DPA terms.
- **Retention:** Transient only. Audio not stored after transcription.

### Telegram

- **Provider:** Telegram Messenger Inc.
- **Purpose:** Primary user interface - bot commands, messages, inline keyboards
- **Data Classification:** SENSITIVE (user communications)
- **Data Flow:** User → Telegram Server → Aurora Webhook → Processing
- **DPA Status:** Platform Terms of Service applies. Telegram is not GDPR-compliant. **User data minimization critical.**
- **Jurisdiction:** HQ in Dubai (UAE), with operations in London/Russia
- **Data Stored by Telegram:** Messages, contacts, media (per Telegram's privacy policy)
- **Mitigation:** Minimize data sent to Telegram. Do not store message history unnecessarily.

### Hetzner (Infrastructure)

- **Provider:** Hetzner Online GmbH
- **Purpose:** Cloud infrastructure hosting - virtual servers, block storage, networking
- **Data Classification:** All classifications (SENSITIVE, ART.9, FINANCIAL)
- **Data Flow:** All application data at rest (database, Redis, files)
- **DPA Status:** DPA required. Hetzner offers DPA via their Privacy Policy and Terms of Service.
- **Jurisdiction:** Germany (EU) - complies with GDPR
- **Security:** Data encrypted at rest using LUKS. All SENSITIVE/ART.9 fields additionally encrypted via Aurora's EncryptionService.
- **Server Location:** Nuremberg (nbg1) datacenter

### Langfuse (Observability)

- **Provider:** Langfuse GmbH
- **Purpose:** LLM tracing, prompt management, observability dashboard
- **Data Classification:** SENSITIVE (must be anonymized before sending)
- **Data Flow:** Prompt/response pairs sent to Langfuse for debugging and optimization
- **DPA Status:** Required - Pending Signature. Must be signed before processing real user Art. 9 data. Langfuse is EU-based (Germany).
- **CRITICAL:** All data must be anonymized before export:
  - Remove user IDs, names, email addresses
  - Remove specific dates/times
  - Remove identifiable context (company names, specific goals)
  - Use session IDs instead of user identifiers

---

## Adding New Sub-Processors

### Rule: Ahash Approval Required

**Before adding ANY new sub-processor to Aurora Sun V1:**

1. **Document the processor** in this registry with all required fields
2. **Get Ahash's explicit approval** before implementation
3. **Verify DPA availability** - all sub-processors must provide DPA
4. **Classify the data** that will be sent to the new processor
5. **Update ARCHITECTURE.md** Section 10 with the new entry
6. **Update this document** with full details

### Checklist for New Sub-Processors

- [ ] Purpose documented
- [ ] Data sent clearly defined
- [ ] Classification assigned (PUBLIC/INTERNAL/SENSITIVE/ART_9_SPECIAL/FINANCIAL)
- [ ] DPA verified and in place
- [ ] Jurisdiction confirmed
- [ ] Ahash approval obtained
- [ ] ARCHITECTURE.md updated
- [ ] This registry updated

---

## Current DPA Status

| Sub-Processor | DPA Status | Agreement Date | Expiry | Deadline | Notes |
|--------------|------------|----------------|--------|----------|-------|
| Anthropic | **PENDING** — Needs Signature | - | - | Before first real user (Phase 3) | Review: [anthropic.com/legal](https://www.anthropic.com/legal). Enterprise DPA covers Art. 9 data |
| OpenAI | **PENDING** — Needs Signature | - | - | Before first real user (Phase 3) | Review: OpenAI Enterprise DPA. Required for fallback LLM path |
| Groq | **PENDING** — Needs Signature | - | - | Before voice feature launch | Review: Groq Terms. Voice = biometric data (Art. 9) |
| Telegram | Platform ToS (no DPA available) | N/A | N/A | N/A | Not GDPR-compliant — data minimization critical. Document residual risk in DPIA |
| Hetzner | **ACTIVE** | 2026-02-09 | Auto-renew | N/A | DPA via Privacy Policy + Terms. EU jurisdiction (compliant) |
| Langfuse | **PENDING** — Needs Signature | - | - | Before observability activation | EU-based (Germany). Must anonymize all trace data before export |

### MED-24: DPA Action Plan

**Blocker:** No real user Art. 9 data may be processed until DPAs are signed. Current dev/test data is synthetic.

| Priority | Action | Owner | Deadline |
|----------|--------|-------|----------|
| 1 | Sign Anthropic Enterprise DPA (primary LLM) | Ahash | Before Phase 3 user interviews |
| 2 | Sign Hetzner DPA addendum (confirm Art. 9 coverage) | Ahash | Before Phase 3 |
| 3 | Sign OpenAI Enterprise DPA (fallback LLM) | Ahash | Before fallback activation |
| 4 | Sign Langfuse DPA (observability) | Ahash | Before production tracing |
| 5 | Evaluate Groq DPA (voice transcription) | Ahash | Before voice feature launch |
| 6 | Document Telegram residual risk in DPIA | Engineering | Before Phase 3 |

**Note:** Telegram does not offer a GDPR-compliant DPA. Residual risk must be documented in DPIA with mitigations (data minimization, no PII storage, encryption).

---

## Data Flow Summary

```
User (Telegram)
    |
    v
[Encryption Layer] --> All SENSITIVE/ART.9/FIELDS encrypted
    |
    v
Aurora Sun App (Hetzner)
    |
    +--> Anthropic (API) --> Response (transient)
    |
    +--> OpenAI (API) --> Response (transient, fallback)
    |
    +--> Groq (API) --> Transcript (transient)
    |
    +--> Langfuse (tracing) --> Anonymized prompts/responses
    |
    v
Database (Hetzner) --> Encrypted at rest + field-level encryption
```

---

## Security Requirements

1. **No PII in LLM prompts** - Always anonymize before sending to Anthropic/OpenAI/Groq
2. **Langfuse anonymization** - Mandatory before any trace export
3. **Telegram data minimization** - Do not store message history; process and discard
4. **Field-level encryption** - All ART.9 and FINANCIAL fields encrypted via EncryptionService
5. **DPA renewal tracking** - Monitor expiry dates, renew before expiration

---

## References

- [ARCHITECTURE.md Section 10](/Users/ahasveros/Documents/#01 HOT/Claude Code/ravar-v7/aurora-sun-v1/ARCHITECTURE.md) - Security & Privacy Architecture
- [CLAUDE.md Security Section](/Users/ahasveros/Documents/#01 HOT/Claude Code/ravar-v7/aurora-sun-v1/CLAUDE.md) - Security requirements for sub-processors
- GDPR Article 28 - Processor requirements
- GDPR Article 9 - Special categories of personal data (Art. 9)

---

*This document is part of Aurora Sun V1's privacy compliance framework. Last reviewed: 2026-02-14*
