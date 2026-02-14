# Changelog -- Aurora Sun V1

All notable changes to this project will be documented in this file.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Security

- **FINDING-004 (CRITICAL):** Crisis data leak fixed -- ART_9 user message context scrubbed from all logs, crisis events encrypted at rest (AES-256-GCM, `DataClassification.ART_9_SPECIAL`), country codes no longer logged (`crisis_service.py`)
- **FINDING-007 (HIGH):** Redis TLS support -- `rediss://` URLs now use proper certificate validation, `REDIS_TLS_CERT_PATH` env var for custom CA certs, both async and sync clients (`redis_service.py`)
- **FINDING-010 (HIGH):** Alembic migration model coverage -- added missing imports for `ConsentRecord`, 6 neurostate models (`SensoryProfile`, `MaskingLog`, `BurnoutAssessment`, `ChannelState`, `InertiaEvent`, `EnergyLevelRecord`), and `CapturedContent` so `--autogenerate` detects all tables (`migrations/env.py`)
- **FINDING-011 (HIGH):** Consent text accuracy -- replaced legally false claims in all 4 languages: "Encrypted end-to-end" changed to "Encrypted at rest (AES-256)", "Never shared with third parties" changed to "Processed by AI services (see /privacy for details)" (`onboarding.py`)
- **FINDING-012 (MEDIUM):** Rate limiter fail-closed mode -- `RateLimiter.check_rate_limit()` now accepts `fail_closed=True` to deny requests when both Redis and in-memory fallback are unavailable (`security.py`)
- **FINDING-014 (MEDIUM):** Revenue tracker encryption wired -- `save_entry()` encrypts with `DataClassification.FINANCIAL`, `get_balance()`/`get_entries()`/`export_user_data()` decrypt on read, graceful plaintext fallback in dev mode (`revenue_tracker.py`)
- **FINDING-008 (MEDIUM):** Dependency pinning -- added upper bounds to security-critical packages: `cryptography<43`, `sqlalchemy<2.1`, `redis<6`, `pydantic<3` (`pyproject.toml`)
- **FINDING-017 (LOW):** User IDs removed from all log output -- replaced with 12-char SHA-256 hash prefix via `hash_uid()`/`_hash_uid()` helpers across `crisis_service.py`, `security.py`, `webhook.py`

#### Previously fixed (Session 1, same commit)

- **FINDING-001:** Rate limiter tier wired to webhook
- **FINDING-002:** Consent gate placeholder replaced with ConsentService
- **FINDING-003:** 13 plaintext model fields encrypted (User, Goal, Vision, Task, DailyPlan, Neurostate, CapturedContent)
- **FINDING-006:** Webhook auth hardened (InputSanitizer, secret token, crisis detection before NLI)
- **FINDING-013:** Security utils wired into middleware
- Encryption dev mode: deterministic fallback key for development
- GDPR module: `str(e)` data leakage removed, duplicate `DataClassification` eliminated
- i18n: format string type guard added

### Changed

- `crisis_service.py`: `_crisis_log` now stores encrypted `EncryptedField` dicts instead of plaintext events; `get_crisis_history()` and `should_pause_workflows()` decrypt on read
- `revenue_tracker.py`: `_entries` now stores encrypted dicts; all read paths (`get_balance`, `get_entries`, `export_user_data`) decrypt transparently
- `security.py`: `check_rate_limit()` signature extended with `fail_closed: bool = False`; `hash_uid()` exported for cross-module use
- `redis_service.py`: `_tls_kwargs()` static method added; both `_ensure_async_client()` and `_get_sync_client()` pass TLS context
- `migrations/env.py`: 8 additional model imports for full autogenerate coverage

---

## [0.1.0] - 2026-02-13

### Added

- Initial project structure (Phase 1: Vertical Slice)
- Encryption foundation (AES-256-GCM, 3-tier envelope, HMAC-SHA256)
- GDPR foundation (RetentionPolicy, GDPRService, ConsentRecord)
- Input security (InputSanitizer, RateLimiter, MessageSizeValidator, SecurityHeaders)
- Telegram webhook handler with NLI routing scaffold
- Onboarding flow (language, name, segment, consent gate)
- Daily workflow engine (LangGraph state machine)
- Phase 2: Intelligence Layer (neurostate, patterns, energy, crisis, effectiveness)
- 689 tests (crisis, security, GDPR, consent, neurostate, segments)
- Phase 2.5: Hybrid Quality Upgrade (6 file rewrites, mypy --strict 0 errors)
