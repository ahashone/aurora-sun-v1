# TODO -- Aurora Sun V1

> Max ~30 items. Completed items visible 1 session, then remove.
> **All Phases Complete (1-5).** 3036 tests passing, 88% coverage, 0 ruff, 0 mypy strict.
> **Sources:** 5 audits + 2 supplements (2026-02-15): GPT-5-Codex (67.3/100), Gemini short, Paranoid Security Codex (14), Gemini Verifier (6.65/10), Gemini Paranoid (42), Executive Summary (72.25/100), Gemini Paranoid fix-verification.

---

## Recently Completed

- [x] CRIT-1: Remove ALL plaintext fallbacks (fail-closed in prod) | crisis_service.py, revenue_tracker.py, money.py, session.py
- [x] CRIT-2: API Auth — catch-all auth middleware (deny by default), admin role check on /health/detailed, global exception handlers | api/__init__.py, dependencies.py, routes.py
- [x] CRIT-3: Webhook secret fail-closed in prod | webhook.py
- [x] CRIT-4: Fix create_app() indentation error — FastAPI app loads | api/__init__.py
- [x] HIGH-1: Fix env var mismatch AURORA_ENV → AURORA_ENVIRONMENT | docker-compose.prod.yml
- [x] HIGH-2: validate_secrets() already wired | confirmed
- [x] HIGH-9: Context-aware InputSanitizerDependency already exists | confirmed
- [x] HIGH-10: Validate CORS origins at startup, reject wildcard in prod | api/__init__.py
- [x] HIGH-11: GDPR export uses hashed user_id | gdpr.py
- [x] MED-1: Fix stale `signal` loop variable in crisis detection | crisis_service.py
- [x] MED-5: Replace silent except:pass with logging | encryption.py
- [x] MED-6: Fix README coverage (88%) + version (0.1.0) | README.md, src/__init__.py
- [x] MED-12: Fix crisis_service bugs (duplicate signal, NL hotline, hardcoded US) | crisis_service.py
- [x] MED-13: Consolidate _hash_uid → import from security.py | crisis_service.py
- [x] MED-17: Add global FastAPI exception handlers | api/__init__.py
- [x] MED-18: Restrict CORS allow_headers from `["*"]` to specific headers | api/__init__.py
- [x] LOW-1: Disable /docs + /redoc in production | api/__init__.py
- [x] LOW-2: Remove commented-out code | daily_workflow.py, daily_graph.py
- [x] LOW-3: Fix alembic.ini placeholder credentials | alembic.ini

## Open Items

### HIGH (Next sprint)

- [ ] HIGH-3: Wire API rate limiting + cost-based limits for LLM calls (create_security_middleware only adds headers) | security.py:1012-1041
- [ ] HIGH-4: Internal service TLS (redis://, http://qdrant, http://letta) + restrict monitoring ports | docker-compose.prod.yml
- [ ] HIGH-5: Fix User.name plaintext window — re-encrypt failure leaves PII in DB, use transaction or pre-generate ID | user.py:139-153, 253-259
- [ ] HIGH-6: Daily workflow DB persistence — remove NotImplementedError | daily_workflow.py:682
- [ ] HIGH-7: RIA service stubs — implement or remove from runtime path | ria_service.py:423-546
- [ ] HIGH-8: Add `processing_restriction` column to User model + Alembic migration (GDPR freeze/unfreeze broken) | gdpr.py:1135
- [ ] HIGH-12: Update cryptography from 42.0.8 to 46.0.5+ (known CVEs in older versions) | pyproject.toml
- [ ] HIGH-13: Apply EncryptedFieldDescriptor to all encrypted models (DRY — only goal.py uses it)
- [ ] PERF-002: Add Redis caching for user lookups | (every webhook hits PG)
- [ ] In-memory stores need Redis persistence in prod | (Codex A-03)
- [ ] BLOCKED: Module GDPR delete stubs need database session injection | (waiting for Ahash)

### MEDIUM (Backlog)

- [ ] MED-2: Backup encryption mandatory + pass DB creds via PGPASSFILE not URL | backup.sh:51, backup.py:320-330
- [ ] MED-3: Postgres exporter sslmode=disable → enable TLS | docker-compose.prod.yml:324
- [ ] MED-4: AI guardrails before LLM activation (prompt injection protection, output validation, PII masking) | webhook.py:439, ria_service.py:489
- [ ] MED-7: Add CVE/dependency scan + lock file for transitive deps | ci.yml, pyproject.toml
- [ ] MED-8: Boost test coverage — shutdown.py (23%), api/__init__.py (36%), session.py (64%)
- [ ] MED-9: Refactor GDPR bulk_delete (162 LOC, CC~46) | gdpr.py:591-752
- [ ] MED-10: Add AAD to all AESGCM encrypt calls | encryption.py:553, 577, 620
- [ ] MED-11: Migrate user salt storage from filesystem to DB-backed | encryption.py:360-370
- [ ] MED-14: GDPR compliance gaps: check_retention() placeholder, consent overwrites, no consent version expiry
- [ ] MED-15: Security event logging — dedicated SecurityEventLogger | no SIEM integration exists
- [ ] MED-16: Role assignment audit trail | rbac.py:420-450
- [ ] MED-19: Investigate transitive dep vulnerabilities (diskcache, pillow) | pyproject.toml
- [ ] Standardize on structured logging (structlog) — only 2/58 files use it
- [ ] PERF-008: Share vision/goal data across workflow state
- [ ] PERF-010: Bulk insert/update for batch operations

### LOW (When convenient)

- [ ] LOW-4: Audit unused dependencies (alembic, anthropic, openai, groq, dspy-ai) | pyproject.toml
- [ ] LOW-5: Sanitizer uses private Telegram object attrs (_text, _data) | webhook.py:150-210
- [ ] LOW-6: Add JWT token revocation mechanism (Redis-based blacklist) | auth.py
- [ ] LOW-7: Document Telegram bot token rotation procedure | docs/security/
- [ ] Add HSTS preload registration
- [ ] Implement formal threat model + regular red-team schedule

---

## Session Log

| Date | Task | Notes |
|------|------|-------|
| 2026-02-13 | Phase 1-2 Complete | Security, Foundation, Modules, Neurostate, Patterns |
| 2026-02-14 | Phase 2.5-5 Complete | Quality upgrade, all phases, 3035 tests |
| 2026-02-15 | 7 Audits Ingested | All findings consolidated → 4 crit, 16 high, 22 med, 9 low |
| 2026-02-15 | Hybrid Quality Fix | 19 items fixed (4 CRIT, 3 HIGH, 7 MED, 3 LOW), 3036 tests passing |
