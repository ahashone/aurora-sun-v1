# TODO -- Aurora Sun V1

> Max ~30 items. Completed items visible 1 session, then remove.
> **All Phases Complete (1-5).** 3059 tests passing, 88% coverage, 0 ruff, 0 mypy strict.
> **Audit sources (2026-02-15):** Paranoid Security Codex (16 findings), GPT-5-Codex (65.8/100, 21 findings), + 5 earlier audits.
> **Full audit reports:** `AUDIT_REPORT_2026-02-15_Gemini.md`, `AUDIT_REPORT_2026-02-15_gpt-5-codex.md`

---

## CRITICAL (Deployment Blockers)

- [x] CRIT-5: Encrypt Habit fields — EncryptedFieldDescriptor on all 6 fields | habit.py, test_habit.py
- [x] CRIT-6: Fix Redis state serialization — AuroraJSONEncoder for dataclasses/datetime/enum/set | redis_service.py, test_redis_service.py, test_state_store.py
- [x] CRIT-7: Wire Telegram production flow — NLI routing + DB session injection + intent detection | webhook.py, test_webhook.py
- [x] CRIT-8: Fix auth token endpoint — JWT generation via AuthService | routes.py, test_routes.py

## HIGH (Next Sprint)

- [x] HIGH-3 (partial): Redis URL auth fix in docker-compose | docker-compose.prod.yml
- [x] HIGH-13: EncryptedFieldDescriptor on all encrypted models (6 models, 4 files) | belief.py, motif.py, capture.py, second_brain.py
- [x] HIGH-14: Fix key rotation — rotate_key() now persists salt to filesystem | encryption.py
- [x] HIGH-15: Dev fallback key raises RuntimeError in prod/staging | ria_service.py
- [x] HIGH-16: Add load_dotenv() before create_app() | main.py
- [x] HIGH-17: destroy_keys() securely deletes salt files | encryption.py
- [x] HIGH-18: JWT aud/iss claims in encode + validated in decode | auth.py
- [x] HIGH-19: Session plaintext fallback removed | session.py, test_session.py
- [x] HIGH-3 (remaining): Wire API rate limiting — RateLimitMiddleware in security.py | security.py, test_security.py
- [x] HIGH-4: Restrict monitoring ports — expose-only in docker-compose.prod.yml | docker-compose.prod.yml
- [x] HIGH-5: Fix User.name plaintext window — before_insert event pre-generates ID | user.py, test_consent.py, test_high5_fix.py
- [x] HIGH-6: Daily workflow DB persistence — upsert logic in save_daily_plan | daily_workflow.py
- [x] HIGH-7: RIA service stubs — added logger warnings to all phase methods | ria_service.py
- [x] HIGH-8: Add processing_restriction column (GDPR Art. 18 freeze/unfreeze) | user.py
- [ ] HIGH-12: Update cryptography from 42.0.8 to 46.0.5+ | pyproject.toml
- [x] HIGH-20: Backup encryption for Neo4j/Qdrant — AES-256-GCM via _encrypt_backup_file | backup.py
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
- [x] MED-20: Deduplicate segment config — single source in segment_context.py | config/segment.py, onboarding.py, user.py
- [ ] MED-21: Fix API validation error detail leakage | dependencies.py:143 (Codex-S4)
- [ ] MED-22: Fix 14 salt-dir-dependent test failures | test_encryption.py, test_money.py (Codex-T1)
- [ ] MED-23: Fix 6 mypy strict errors in api/ | dependencies.py, __init__.py (Codex)
- [ ] MED-24: DPA status pending for sub-processors | SUB-PROCESSOR-REGISTRY.md (Paranoid-013)
- [x] MED-25: Crisis detection word boundary matching — regex \b guards | crisis_service.py
- [ ] MED-26: Reduce 105x `except Exception` + 45x `pass` — domain-specific exceptions | (Codex-Q5/S5)

## LOW (When convenient)

- [ ] LOW-4: Audit unused runtime dependencies | pyproject.toml
- [ ] LOW-5: Sanitizer uses private Telegram attrs | webhook.py:150
- [ ] LOW-6: JWT token revocation mechanism (Redis blacklist) | auth.py
- [x] LOW-7: Pin letta:latest → letta:0.6.5 | docker-compose.prod.yml
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
| 2026-02-15 | Audit Fixes Batch 1 | 10 items fixed (2 CRIT, 8 HIGH, 1 LOW), 3054 tests passing |
| 2026-02-15 | Audit Fixes Batch 2 | 11 items fixed (2 CRIT, 6 HIGH, 2 MED, 1 infra), 3059 tests passing |
