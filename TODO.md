# TODO -- Aurora Sun V1

> Max ~30 items. Completed items visible 1 session, then remove.
> Format: `- [ ] Task (→ ROADMAP X.Y, SW-N)`

---

## Phase 1: Vertical Slice

### 1.0 Security Foundation

- [x] Create encryption.py: EncryptionService (encrypt_field, decrypt_field, rotate_key, destroy_keys) (→ ROADMAP 1.0, SW-15)
- [x] Define data classification enum: PUBLIC, INTERNAL, SENSITIVE, ART_9_SPECIAL, FINANCIAL (→ ROADMAP 1.0)
- [x] Implement per-user encryption key generation on user creation (→ ROADMAP 1.0)
- [x] Implement AES-256-GCM field-level encryption for SENSITIVE/ART.9 fields (→ ROADMAP 1.0)
- [x] Implement 3-tier envelope encryption for FINANCIAL fields (→ ROADMAP 1.0)
- [x] Implement HMAC-SHA256 hashing for PII identifiers (telegram_id, name) (→ ROADMAP 1.0)
- [ ] Write unit tests: encrypt→decrypt roundtrip, key rotation, key destruction (→ ROADMAP 1.0)
- [x] Create ConsentRecord model (consent_version, language, timestamp, text_hash) (→ ROADMAP 1.0, SW-15)
- [x] Implement consent gate in onboarding flow (explicit, not skippable, translated) (→ ROADMAP 1.0, SW-13)
- [x] Implement consent withdrawal handler (→ ROADMAP 1.0, SW-15)
- [x] Implement consent version tracking (→ ROADMAP 1.0)
- [x] Extend Module Protocol: freeze_user_data(), unfreeze_user_data() (→ ROADMAP 1.0, SW-15)
- [x] Define retention policy config per data classification (→ ROADMAP 1.0)
- [x] Implement data export format: JSON, machine-readable (→ ROADMAP 1.0, SW-15)
- [ ] Create docs/DPIA.md: Initial Data Protection Impact Assessment (→ ROADMAP 1.0)
- [x] Implement input sanitization middleware (XSS, SQL injection, path traversal) (→ ROADMAP 1.0)
- [x] Implement per-user rate limiting (message frequency + LLM cost) (→ ROADMAP 1.0)
- [x] Implement message size limits at NLI layer (→ ROADMAP 1.0)
- [x] Implement voice message limits (60s / 10MB) (→ ROADMAP 1.0)
- [ ] Document Sub-processor registry (Anthropic, OpenAI, Groq, Telegram, Hetzner, Langfuse) (→ ROADMAP 1.0)
- [ ] Document breach notification procedure (→ ROADMAP 1.0)
- [ ] Document data classification matrix for all Phase 1 tables (→ ROADMAP 1.0)

---

## Session Log

| Date | Task | Notes |
|------|------|-------|
| 2026-02-13 | Created Git repo + folder structure | Initial commit pushed to GitHub |
