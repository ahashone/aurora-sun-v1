# TODO -- Aurora Sun V1

> Max ~30 items. Completed items visible 1 session, then remove.
> **All Phases Complete (1-5).** Full QA Audit complete. See QA-REPORT.md.

---

## Completed This Session

- [x] CODEX-CRIT-1: Wire SecurityHeaders middleware into FastAPI app | src/api/__init__.py, src/lib/security.py
- [x] CODEX-CRIT-2: Webhook fails closed when TELEGRAM_WEBHOOK_SECRET not set in prod | src/bot/webhook.py
- [x] SEC-001: Implement auth middleware on all API endpoints | src/api/__init__.py, src/api/auth.py
- [x] SEC-007: Add API rate limiting middleware | src/api/__init__.py, src/lib/security.py
- [x] SEC-008: Add HTTPS redirect middleware for production | src/infra/middleware.py, src/api/__init__.py
- [x] SEC-004: Sanitize all Telegram update fields (text, caption, callback, inline) | src/bot/webhook.py
- [x] CODEX-HIGH-1: Remove money.py plaintext fallback on encryption failure | src/modules/money.py
- [x] CODEX-HIGH-2: RIA service insecure HMAC fallback key hard-fails in prod | src/services/ria_service.py
- [x] PERF-001: Add eager loading (selectinload) to hot-path relationships | src/models/user.py
- [x] PERF-009: Implement lazy caching for decrypted field properties | src/models/user.py, goal.py, task.py, vision.py
- [x] PERF-003: Bulk GDPR delete for batched operations | src/lib/gdpr.py
- [x] CODEX-MED-5: Sanitize error messages in middleware logging | src/infra/middleware.py, health.py, backup.py, rbac.py
- [x] Build custom exception hierarchy (AuroraSunException) | src/lib/exceptions.py + 88 tests
- [x] Replace ~16 broad except catches with specific types | src/infra/*.py
- [x] REFACTOR-001: Extract GDPR methods to GDPRModuleMixin | src/core/gdpr_mixin.py, 9 modules updated
- [x] REFACTOR-002: Extract encryption property to EncryptedFieldDescriptor | src/lib/encrypted_field.py, src/models/goal.py
- [x] REFACTOR-005: Implement API response envelope pattern | src/api/schemas.py, src/api/routes.py
- [x] REFACTOR-011: Centralized error response builder with i18n | src/lib/errors.py (en/de/sr/el)
- [x] DRY: Extract _score_keyword_alignment helper in coherence.py | src/agents/aurora/coherence.py
- [x] DRY: Unified milestone detection loops via shared helper | src/agents/aurora/milestones.py
- [x] Magic numbers extracted to named constants | coherence.py, milestones.py, growth.py
- [x] Bounded caches: audit history + segment context caches (OrderedDict LRU) | coherence.py, segment_service.py
- [x] O(1) user_id index for growth tracker | src/agents/aurora/growth.py
- [x] Graceful shutdown handler for in-progress workflows | src/workflows/shutdown.py
- [x] SEC-006: Backup path validation for filenames | src/infra/backup.py
- [x] SideEffectExecutor.execute() as @abstractmethod | src/core/side_effects.py
- [x] Boost neurostate coverage 69% -> 96% (50 tests) | tests/src/models/test_neurostate_models.py
- [x] Boost onboarding coverage 68% -> 97% (25 tests) | tests/src/bot/test_onboarding.py
- [x] Boost onboarding_deep coverage 74% -> 100% (28 tests) | tests/src/modules/test_onboarding_deep.py
- [x] Fix deprecation warnings (datetime.utcnow -> datetime.now(UTC)) | side_effects.py, test_health.py, test_backup.py

---

## Open Items

### HIGH (Before Scaling)

- [ ] PERF-002: Add Redis caching for user lookups | (every webhook hits PG)
- [ ] In-memory stores need Redis persistence in prod | (Codex A-03)
- [ ] BLOCKED: Module GDPR delete stubs need database session injection | (waiting for Ahash)

### MEDIUM (Next Sprint)

- [ ] Standardize on structured logging (structlog) — only 2/58 files use it
- [ ] PERF-008: Share vision/goal data across workflow state
- [ ] PERF-010: Bulk insert/update for batch operations

### LOW (When Convenient)

- [ ] Add HSTS preload registration | (HSTS header set but not on preload list)
- [ ] Implement formal threat model + regular red-team schedule | (Tier 3)
- [ ] Security regression test suite in CI | (Tier 3)

---

## Session Log

| Date | Task | Notes |
|------|------|-------|
| 2026-02-13 | Phase 1 Complete | Security, Foundation, Modules, Workflow, Coaching |
| 2026-02-13 | Phase 2 Complete | Neurostate, Patterns, Energy, Crisis, Effectiveness |
| 2026-02-14 | Deep Audit Complete | 14 bugs, 514 lint errors, 689 tests |
| 2026-02-14 | Phase 2.5 Complete | Quality upgrade, mypy strict, 689 tests |
| 2026-02-14 | Security Fixes Complete | 17 findings fixed across 2 sessions |
| 2026-02-14 | Phase 3-5 Complete | 850+ new tests (1539 total), all audits pass |
| 2026-02-14 | Paranoid Audit Fix | 47 findings fixed, 2367 tests, 0 ruff/mypy errors |
| 2026-02-14 | Stabilization Sprint | 18 audit items fixed, 2583 tests, 0 ruff/mypy errors |
| 2026-02-14 | Full QA Audit | 8 phases, 115 new tests, 11 fixes, 2698 tests, 83% coverage |
| 2026-02-15 | Coverage Boost | encryption 92%, security 97%, gdpr 91%; 2931 tests, 0 failures |
| 2026-02-15 | Hybrid Quality Upgrade | 30+ items fixed, 3035 tests, 0 ruff, 0 mypy strict |
