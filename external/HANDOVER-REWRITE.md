# HANDOVER: Aurora Sun V1 -- Rewrite with Opus/Sonnet

> **Context:** Aurora Sun V1 Phase 1+2 were implemented by MiniMax in <1 day.
> A deep audit by Opus found quality issues. Decision: rewrite with Opus/Sonnet.
> This document is the handover for the new Claude Code session.

**Date:** 2026-02-14
**Branch with current code:** `claude/fix-audit-issues-sXhRs`
**Repository:** aurora-sun-v1

---

## YOUR MISSION

Rewrite the Aurora Sun V1 source code (Phase 1 + Phase 2) from scratch using the existing architecture documents as specification. The goal is production-quality code that follows ALL rules in CLAUDE.md and ARCHITECTURE.md without shortcuts.

### What to KEEP (do not rewrite):
- `CLAUDE.md` -- Master prompt, all rules apply
- `ARCHITECTURE.md` -- Single source of truth for system design
- `ROADMAP.md` -- Phase definitions and progress tracking
- `TODO.md` -- Active task list
- `IMPLEMENTATION-LOG.md` -- Append new entries
- `docs/` -- All documentation (DPIA, WORKFLOWS, etc.)
- `knowledge/` -- Research findings (216+ findings)
- `pyproject.toml` -- Dependencies (review, but keep)
- `docker-compose.yml`, `Dockerfile` -- Infrastructure
- `.env.example` -- Environment template
- `tests/` -- 689 existing tests (use as regression suite!)

### What to REWRITE:
- Everything under `src/` -- All source code

### What to UPDATE after rewrite:
- `README.md` -- If any setup steps change
- `TODO.md` -- Mark progress
- `ROADMAP.md` -- Re-check Phase 1+2 checkboxes
- `IMPLEMENTATION-LOG.md` -- Log the rewrite

---

## WHY THE REWRITE

The audit found these systemic issues in the MiniMax implementation:

### 1. Segment Anti-Pattern Violations (CRITICAL)
5 places used `if segment == "AD"` pattern, which violates the project's #1 architectural rule. Must use SegmentContext fields instead. See CLAUDE.md "Neurotype Segmentation" and ARCHITECTURE.md Section 3.

**Files that had violations:**
- `src/services/coaching_engine.py` -- Direct segment string comparisons
- `src/services/energy_system.py` -- `if segment == "AD"` checks
- `src/services/pattern_detection.py` -- Segment string matching
- `src/modules/planning.py` -- Segment-conditional logic
- `src/workflows/daily_workflow.py` -- Segment checks in flow

**Correct pattern:** Always use `segment_context.core.*`, `segment_context.ux.*`, `segment_context.neuro.*`, `segment_context.features.*` fields. Never compare segment codes.

### 2. In-Memory State Instead of Persistence
Multiple services stored state in Python dicts or `threading.Lock` instead of using the database or Redis. This means all state is lost on restart.

**Affected:**
- Onboarding flow state (fixed to Redis, but pattern was wrong)
- Rate limiter state (in-memory dict)
- Session state in modules

### 3. Async/Sync Confusion
- `threading.Lock` used in async code (should use `asyncio.Lock`)
- ConsentService mixed async and sync methods inconsistently
- Some SQLAlchemy sessions not properly async

### 4. Type Annotation Issues
- 171 mypy strict-mode errors
- `Literal[0,1] = Literal[0,1]` type alias bug
- Missing TypeAlias imports
- Circular type references

### 5. Placeholder Implementations
Many methods had the right signature but returned hardcoded values or empty dicts instead of real implementations:
- Energy calculations returning fixed scores
- Pattern detection with minimal actual logic
- Effectiveness tracking without real measurement

### 6. Production Readiness: 4/10
- No graceful shutdown
- No connection pooling configuration
- No health check endpoints
- structlog configured but not wired
- No pre-commit hooks

---

## SPECIFICATION: WHAT TO BUILD

Read these documents in this order:
1. **CLAUDE.md** -- All rules, especially Neurotype Segmentation section
2. **ARCHITECTURE.md** -- Full system design (the spec)
3. **ROADMAP.md Phase 1 + Phase 2** -- Feature checklist
4. **docs/WORKFLOWS.md** -- System workflows

### Phase 1 Components (Vertical Slice)

#### 1.0 Security Foundation
- `src/lib/encryption.py` -- AES-256-GCM field-level encryption, HMAC-SHA256 PII hashing, key rotation, key destruction
- `src/lib/security.py` -- Input sanitization (XSS, SQL injection, path traversal), rate limiting, message validation
- `src/lib/gdpr.py` -- GDPRService, retention policies, export/delete/freeze per module
- `src/models/consent.py` -- ConsentRecord with version tracking, non-skippable consent gate

#### 1.1 Core Data Models
- `src/models/base.py` -- Single DeclarativeBase, shared utilities
- `src/models/user.py` -- User with per-user encryption keys, segment, GDPR methods
- `src/models/vision.py` -- Vision (encrypted), GDPR methods
- `src/models/goal.py` -- Goal linked to Vision, GDPR methods
- `src/models/task.py` -- Task linked to Goal, GDPR methods
- `src/models/daily_plan.py` -- DailyPlan snapshot
- `src/models/session.py` -- Session record
- `src/models/neurostate.py` -- NeurostateSnapshot (sensory, energy, inertia, masking, channel)

**Rules:** Every model has data classification. Every SENSITIVE/ART_9/FINANCIAL field encrypted. Every model has export_user_data, delete_user_data, freeze_user_data, unfreeze_user_data.

#### 1.2 Segment System
- `src/config/segment.py` -- 5 segment configs (AD/AU/AH/NT/CU) with 4 sub-objects each
- `src/core/segment_context.py` -- SegmentContext class (core, ux, neuro, features)
- `src/core/segment_service.py` -- Lookup and validation

**Rule:** NEVER `if segment == "AD"`. Always use SegmentContext fields.

#### 1.3 Module System
- `src/core/module_protocol.py` -- ModuleProtocol interface
- `src/core/module_registry.py` -- Auto-discovery, intent-to-module mapping
- `src/core/module_context.py` -- Context object (user, segment, state)
- `src/core/module_response.py` -- Response type
- `src/modules/planning.py` -- 8-state planning machine (segment-adapted task limits)
- `src/modules/review.py` -- Evening review (accomplishments, challenges, energy)
- `src/modules/capture.py` -- Fire-and-forget capture (task/idea/note/insight/question/goal)
- `src/modules/future_letter.py` -- Vision grounding through letter writing

#### 1.4 Daily Workflow + Bot
- `src/workflows/daily_graph.py` -- LangGraph StateGraph
- `src/workflows/daily_workflow.py` -- Orchestrator
- `src/bot/webhook.py` -- Telegram webhook + NLI intent routing (regex fast path ~70%, Haiku fallback)
- `src/bot/onboarding.py` -- Onboarding flow (state persisted to Redis)
- `src/services/coaching_engine.py` -- PINCH (ADHD), Inertia protocol (Autism), channel-aware (AuDHD)
- `src/services/redis_service.py` -- Redis wrapper

#### 1.5 Infrastructure
- `src/__init__.py` -- structlog configuration
- `src/lib/logging.py` -- Logging setup
- `src/i18n/strings.py` -- i18n (en, de, sr, el minimum)
- `src/core/buttons.py` -- Telegram button builders
- `src/core/side_effects.py` -- Side effect types

### Phase 2 Components (Intelligence Layer)

#### 2.1 Neurostate Services
- `src/services/neurostate/sensory.py` -- Sensory state (cumulative, NO habituation for AU/AH)
- `src/services/neurostate/inertia.py` -- Inertia detection (3 types: task-transition, initiation, shutdown)
- `src/services/neurostate/burnout.py` -- Burnout classification (3 types: ADHD burnout, Autistic burnout, AuDHD compound)
- `src/services/neurostate/masking.py` -- Masking load (exponential for AuDHD, not linear)
- `src/services/neurostate/channel.py` -- Channel dominance (ADHD-day vs Autism-day for AuDHD)
- `src/services/neurostate/energy.py` -- Energy prediction from behavioral proxies (NOT only self-report for AU/AH)

#### 2.2 Pattern Detection & Safety
- `src/services/pattern_detection.py` -- 5 destructive cycles (Meta-Spirale, Shiny Object, Perfectionism, Isolation, Free Work) + 18 daily burden signals
- `src/services/crisis_service.py` -- Crisis detection (20+ signals, 13+ warning signals, severity scoring, hotline integration)
- `src/services/energy_system.py` -- Energy gating per segment (IBNS/PINCH for ADHD, ICNU for AuDHD, Spoon-Drawer for AuDHD, Sensory+Cognitive for Autism)

#### 2.3 Effectiveness & Tracking
- `src/services/effectiveness.py` -- Intervention tracking, A/B testing, weekly effectiveness reporting

---

## QUALITY REQUIREMENTS

### Must Pass:
1. All 689 existing tests (`pytest tests/ -v`)
2. `ruff check src/` -- Zero lint errors
3. `mypy src/ --strict` -- Zero or near-zero errors (aim for 0)
4. Zero `if segment ==` patterns anywhere in code
5. All SENSITIVE/ART_9 fields use EncryptionService
6. All models have GDPR methods
7. All async code uses `asyncio.Lock` (never `threading.Lock`)
8. All state persisted to DB or Redis (no in-memory dicts for user state)
9. structlog properly configured and used throughout
10. Proper SQLAlchemy async patterns

### Code Style:
- Type annotations on all public functions
- Docstrings only where logic isn't self-evident
- No over-engineering -- minimum complexity for current requirements
- Follow existing folder structure exactly

---

## EXISTING TEST SUITE (689 tests)

These tests were written by Opus and are the regression suite for the rewrite:

| Test File | Count | Tests |
|-----------|-------|-------|
| `tests/src/lib/test_encryption.py` | 39 | Roundtrip, key rotation, destruction, hashing |
| `tests/src/lib/test_security.py` | 141 | XSS, SQL injection, path traversal, rate limiting |
| `tests/src/lib/test_gdpr.py` | 55 | Retention, export, delete, freeze/unfreeze |
| `tests/src/models/test_consent.py` | 54 | Create, verify, validate, withdraw, reconsent |
| `tests/src/core/test_segment_context.py` | 94 | All 5 segments, configs, display names |
| `tests/src/services/test_crisis_service.py` | 201 | All crisis signals, warning signals, hotlines |
| `tests/src/services/neurostate/test_burnout.py` | 57 | 3 types, trajectory, severity, protocols |
| `tests/src/services/neurostate/test_inertia.py` | 48 | 3 types, keyword scoring |

**Important:** These tests define the expected API contracts. Your rewrite must match these interfaces. Read each test file to understand the expected method signatures, return types, and behaviors.

---

## ANTI-PATTERNS TO AVOID

From CLAUDE.md -- these are project rules, not suggestions:

1. **Never** `if segment == "AD"` -- use SegmentContext fields
2. **Never** in-memory state for user data -- use DB/Redis
3. **Never** `threading.Lock` in async code -- use `asyncio.Lock`
4. **Never** skip consent gate
5. **Never** aggregate data across segments
6. **Never** store Art. 9 data unencrypted
7. **Never** "just start" for Autistic Inertia (wrong intervention)
8. **Never** Behavioral Activation during Autistic Burnout
9. **Never** treat AuDHD as "ADHD + Autism combined" (it's its own thing)
10. **Never** assume sensory habituation for AU/AH (sensory load accumulates)
11. **Never** Pomodoro for AU/AD-I deep focus types
12. **Never** same notifications/burnout protocol for all segments

---

## WORKFLOW

1. Read CLAUDE.md completely
2. Read ARCHITECTURE.md completely
3. Read all test files to understand expected APIs
4. Rewrite `src/` from scratch, file by file
5. Run tests after each major component
6. When all 689 tests pass + ruff + mypy clean: done
7. Update TODO.md, ROADMAP.md, IMPLEMENTATION-LOG.md
8. Commit and push

**Branch:** Create a new branch from `main` for the rewrite (e.g., `claude/rewrite-phase1-2-<session-id>`)

---

## ADDITIONAL CONTEXT

### Segment Quick Reference
| Code | Internal | User-Facing | Key Trait |
|------|----------|-------------|-----------|
| AD | AD | ADHD | Interest-based nervous system, PINCH/IBNS energy |
| AU | AU | Autism | Predictability, deep focus, sensory accumulation |
| AH | AH | AuDHD | Channel dominance (ADHD-day vs Autism-day), compound masking |
| NT | NT | Neurotypical | Standard executive function model |
| CU | CU | Custom | User-defined profile |

### Energy Systems per Segment
- **ADHD:** IBNS (Interest-Based Nervous System) + PINCH (Play, Interest, Novelty, Competition, Humor)
- **AuDHD:** ICNU (Interest-Consistency-Novelty-Urgency) + Spoon-Drawer (spoons + energy drawers)
- **Autism:** Sensory-Cognitive composite (sensory load + cognitive load + transition cost)
- **NT:** Standard willpower/depletion model

### Burnout Types (3 distinct!)
1. **ADHD Burnout:** Interest collapse, executive function bankruptcy
2. **Autistic Burnout:** Sensory/social overload, skill regression, long recovery
3. **AuDHD Compound:** Both simultaneously, channel collapse

### Inertia Types (3 distinct!)
1. **Task-Transition:** Can't switch between tasks (stuck in current)
2. **Initiation:** Can't start anything (frozen at beginning)
3. **Shutdown:** System shutdown, no output possible

---

*This handover was generated from the deep audit session on 2026-02-14.*
*All source documents (CLAUDE.md, ARCHITECTURE.md, ROADMAP.md) are the authoritative references.*
