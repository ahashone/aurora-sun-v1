# TODO -- Aurora Sun V1

> Max ~30 items. Completed items visible 1 session, then remove.
> **All Phases Complete (1-5).** 3302 tests passing, 88% coverage, 0 ruff, 0 mypy strict.
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
- [x] HIGH-12: Update cryptography from 42.0.8 to >=46.0.0 | pyproject.toml
- [x] HIGH-20: Backup encryption for Neo4j/Qdrant — AES-256-GCM via _encrypt_backup_file | backup.py
- [x] PERF-002: Redis caching for user lookups | user_cache.py, webhook.py, test_user_cache.py
- [ ] BLOCKED: Module GDPR delete stubs need DB session injection | (waiting for Ahash)

## MEDIUM (Backlog)

- [x] MED-2: Backup encryption mandatory + PGPASSFILE | backup.py, backup.sh
- [x] MED-3: Postgres exporter sslmode → TLS (sslmode=prefer) | docker-compose.prod.yml
- [x] MED-4: AI guardrails — PromptInjectionDetector + OutputValidator + AIGuardrails facade + 136 tests | ai_guardrails.py, webhook.py, coaching_engine_full.py, ria_service.py
- [x] MED-7: CVE/dependency scan + lock file (pip-audit in CI) | ci.yml
- [x] MED-8: Test coverage gaps — shutdown.py, api/__init__.py, dependencies.py | test_shutdown.py, test_api_init.py, test_dependencies.py
- [ ] MED-9: Refactor god modules: gdpr.py (1141 LOC), money.py (1589 LOC), planning.py (1138 LOC)
- [x] MED-10: Add AAD to all AESGCM encrypt calls + fix field_name mismatches | encryption.py, session.py, crisis_service.py, revenue_tracker.py
- [ ] MED-11: Migrate user salt storage from filesystem to DB | encryption.py:360
- [x] MED-14: Fix GDPR consent overwrite to preserve audit trail | consent.py, test_consent.py
- [x] MED-15: Security event logging — SecurityEventLogger + SecurityEventType enum | security.py, webhook.py, auth.py
- [x] MED-20: Deduplicate segment config — single source in segment_context.py | config/segment.py, onboarding.py, user.py
- [x] MED-21: Fix API validation error detail leakage — generic message + server-side logging | dependencies.py
- [x] MED-22: Fix 14 salt-dir-dependent test failures | tests/conftest.py (AURORA_SALT_DIR → tmp_path)
- [x] MED-23: Fix 6 mypy strict errors in api/ — Generic[ModelType], typed call_next | dependencies.py, __init__.py
- [x] MED-24: DPA action plan with deadlines for all sub-processors | SUB-PROCESSOR-REGISTRY.md
- [x] MED-25: Crisis detection word boundary matching — regex \b guards | crisis_service.py
- [ ] MED-26: Reduce 105x `except Exception` + 45x `pass` — domain-specific exceptions | (Codex-Q5/S5)

## LOW (When convenient)

- [x] LOW-4: Audit unused runtime dependencies — removed 7 unused deps (anthropic, openai, groq, dspy-ai, pydantic-ai, letta-client, langfuse) | pyproject.toml
- [x] LOW-5: Sanitizer uses public API via _set_telegram_field helper | webhook.py
- [x] LOW-6: JWT token revocation mechanism (Redis blacklist) — jti claim + TokenBlacklist + 18 tests | auth.py, test_auth.py
- [x] LOW-7: Pin letta:latest → letta:0.6.5 | docker-compose.prod.yml
- [x] LOW-8: API integration tests — 43 tests with httpx AsyncClient | test_api_integration.py
- [x] LOW-9: Migrate from deprecated `safety check` to pip-audit | ci.yml
- [x] HSTS preload registration — already present in SecurityHeadersMiddleware | security.py
- [x] Formal threat model + red-team schedule — STRIDE analysis + quarterly schedule | docs/THREAT-MODEL.md

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
| 2026-02-15 | Audit Fixes Batch 3 | 3 items fixed (MED-8, MED-10, PERF-002), +85 tests, 3144 tests passing |
| 2026-02-15 | Audit Fixes Batch 4 | 11 items fixed (HIGH-12, MED-2/3/7/14/15/21/23/24, LOW-5/9), 3144 tests passing |
| 2026-02-15 | Audit Fixes Batch 5 | 8 items fixed (MED-4/22, LOW-4/6/8, HSTS, threat model), +158 tests, 3302 tests passing |
