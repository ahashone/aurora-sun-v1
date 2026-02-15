# TODO -- Aurora Sun V1

> Max ~30 items. Completed items visible 1 session, then remove.
> **All Phases Complete (1-5).** 3036 tests passing, 88% coverage, 0 ruff, 0 mypy strict.
> **Audit sources (2026-02-15):** Paranoid Security Codex (16 findings), GPT-5-Codex (65.8/100, 21 findings), + 5 earlier audits.
> **Full audit reports:** `AUDIT_REPORT_2026-02-15_Gemini.md`, `AUDIT_REPORT_2026-02-15_gpt-5-codex.md`

---

## CRITICAL (Deployment Blockers)

- [x] CRIT-5: Encrypt Habit fields (identity_statement, cue, craving, response, reward) — Art.9 data in plaintext | habit.py, test_habit.py (Paranoid-002)
- [ ] CRIT-6: Fix Redis state serialization — BoundedStateStore writes non-JSON-serializable dataclasses → TypeError | state_store.py, redis_service.py:89 (Codex-A5)
- [ ] CRIT-7: Wire Telegram production flow — DB session injection + real NLI routing (currently echo scaffold) | webhook.py:344,443 (Codex-A3)
- [ ] CRIT-8: Fix auth token endpoint — logically blocked (public route depends on get_current_user_id) + NOT_IMPLEMENTED | routes.py:179, dependencies.py:96 (Codex-A4/S1)

## HIGH (Next Sprint)

- [ ] HIGH-3: Wire API rate limiting + Redis URL auth fix (missing password → in-memory fallback) | security.py:1012, docker-compose.prod.yml (+ Paranoid-006)
- [ ] HIGH-4: Internal service TLS + restrict monitoring ports | docker-compose.prod.yml
- [ ] HIGH-5: Fix User.name plaintext window — transaction or pre-generate ID | user.py:139-153
- [ ] HIGH-6: Daily workflow DB persistence — remove NotImplementedError | daily_workflow.py:682
- [ ] HIGH-7: RIA service stubs — implement or remove from runtime path | ria_service.py:423-546
- [ ] HIGH-8: Add processing_restriction column + Alembic migration (GDPR freeze/unfreeze) | gdpr.py:1135
- [ ] HIGH-12: Update cryptography from 42.0.8 to 46.0.5+ | pyproject.toml
- [ ] HIGH-13: Apply EncryptedFieldDescriptor to all encrypted models (DRY) | belief.py, motif.py, capture.py, second_brain.py
- [ ] HIGH-14: Fix key rotation regression — old data still decryptable after rotate_key(), 2 test failures | encryption.py:798 (Codex-S2)
- [ ] HIGH-15: Remove dev fallback key "dev-only-insecure-key" in RIA integrity path | ria_service.py:292 (Codex-S3)
- [ ] HIGH-16: Add load_dotenv() to runtime — README setup fails without it | main.py (Codex-D1)
- [ ] HIGH-17: destroy_keys() must delete salt files (AURORA_SALT_DIR) — GDPR erasure incomplete | encryption.py:823 (Paranoid-004)
- [ ] HIGH-18: JWT aud/iss validation — DPIA claims it, code doesn't do it | auth.py:208 (Paranoid-008)
- [ ] HIGH-19: Remove session_metadata plaintext fallback — force migration | session.py:88,138 (Paranoid-009)
- [ ] HIGH-20: Backup encryption for Neo4j/Qdrant (only PG/Redis encrypted) | backup.py:457,536 (Paranoid-005)
- [ ] PERF-002: Redis caching for user lookups | (every webhook hits PG)
- [ ] BLOCKED: Module GDPR delete stubs need DB session injection | (waiting for Ahash)

## MEDIUM (Backlog)

- [ ] MED-2: Backup encryption mandatory + PGPASSFILE | backup.sh, backup.py:320
- [ ] MED-3: Postgres exporter sslmode → TLS | docker-compose.prod.yml:324
- [ ] MED-4: AI guardrails before LLM activation (prompt injection, output validation) | webhook.py:439, ria_service.py:489
- [ ] MED-7: CVE/dependency scan + lock file (pip-audit in CI) | ci.yml, pyproject.toml
- [ ] MED-8: Test coverage gaps — shutdown.py (23%), api/__init__.py (36%), dependencies.py (35%)
- [ ] MED-9: Refactor god modules: gdpr.py (1141 LOC), money.py (1589 LOC), planning.py (1138 LOC)
- [ ] MED-10: Add AAD to all AESGCM encrypt calls | encryption.py:553,577,620
- [ ] MED-11: Migrate user salt storage from filesystem to DB | encryption.py:360
- [ ] MED-14: GDPR compliance gaps: retention placeholder, consent overwrites
- [ ] MED-15: Security event logging — SecurityEventLogger | no SIEM
- [ ] MED-20: Deduplicate segment config to single source | segment_context.py:22, config/segment.py:23, onboarding.py:74 (Codex-A2)
- [ ] MED-21: Fix API validation error detail leakage | dependencies.py:143 (Codex-S4)
- [ ] MED-22: Fix 14 salt-dir-dependent test failures | test_encryption.py, test_money.py (Codex-T1)
- [ ] MED-23: Fix 6 mypy strict errors in api/ | dependencies.py, __init__.py (Codex)
- [ ] MED-24: DPA status pending for sub-processors | SUB-PROCESSOR-REGISTRY.md (Paranoid-013)
- [ ] MED-25: Crisis detection substring-based — false positive risk | crisis_service.py:177 (Paranoid-014)
- [ ] MED-26: Reduce 105x `except Exception` + 45x `pass` — domain-specific exceptions | (Codex-Q5/S5)

## LOW (When convenient)

- [ ] LOW-4: Audit unused runtime dependencies | pyproject.toml
- [ ] LOW-5: Sanitizer uses private Telegram attrs | webhook.py:150
- [ ] LOW-6: JWT token revocation mechanism (Redis blacklist) | auth.py
- [ ] LOW-7: Pin letta:latest container tag | docker-compose.prod.yml (Codex)
- [ ] LOW-8: API integration tests with TestClient | (Codex)
- [ ] LOW-9: Migrate from deprecated `safety check` to `safety scan` | (Paranoid-015)
- [ ] Add HSTS preload registration
- [ ] Formal threat model + red-team schedule

---

## Session Log

| Date | Task | Notes |
|------|------|-------|
| 2026-02-13 | Phase 1-2 Complete | Security, Foundation, Modules, Neurostate, Patterns |
| 2026-02-14 | Phase 2.5-5 Complete | Quality upgrade, all phases, 3035 tests |
| 2026-02-15 | 7 Audits Ingested | All findings consolidated → 4 crit, 16 high, 22 med, 9 low |
| 2026-02-15 | Hybrid Quality Fix | 19 items fixed (4 CRIT, 3 HIGH, 7 MED, 3 LOW), 3036 tests passing |
| 2026-02-15 | Audit Round 2 | +2 audits ingested (Paranoid Codex, GPT-5-Codex), 25 new items added |
