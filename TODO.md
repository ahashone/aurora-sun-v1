# TODO -- Aurora Sun V1

> Max ~30 items. Completed items visible 1 session, then remove.
> **Current Phase: 2.5 Hybrid Quality Upgrade** (→ ROADMAP 2.5, docs/HYBRID-QUALITY-UPGRADE-PLAN.md)

---

## Phase 2.5: Hybrid Quality Upgrade (active)

### Step 0: Setup
- [x] Create branch claude/hybrid-quality-upgrade
- [x] Verify 689 tests passing (→ ROADMAP 2.5.0)
- [x] Verify 0 ruff errors (→ ROADMAP 2.5.0)

### Step 1: Rewrite Critical Files (→ ROADMAP 2.5.1, plan Step 1)
- [x] state_store.py — asyncio.Lock, proper LRU, Redis persistence | state_store.py
- [x] tension_engine.py — fix types, Redis persistence | tension_engine.py
- [x] energy_system.py — SegmentContext.neuro/ux/features | energy_system.py
- [x] pattern_detection.py — SegmentContext for signals + interventions | pattern_detection.py
- [x] coaching_engine.py — neuro fields, Redis channel cache, deterministic | coaching_engine.py
- [x] effectiveness.py — canonical SegmentCode, z-test, fix double-count | effectiveness.py

### Step 2: Inspect & Fix Untested Files (→ ROADMAP 2.5.2, plan Step 2)
- [x] 4/7 modules (planning, review, capture, future_letter) | planning.py, future_letter.py (belief/habit/motif not yet implemented)
- [x] 3 bot/infra (webhook, onboarding, module_registry) | webhook.py
- [x] 3 supporting (segment_service, redis_service, revenue_tracker) | redis_service.py, revenue_tracker.py

### Step 3: Neurostate Inspection (→ ROADMAP 2.5.3, plan Step 3)
- [x] 5 neurostate files (sensory, energy, masking, channel, __init__) | energy.py (segment-aware assessment)

### Step 4: Workflows Inspection (→ ROADMAP 2.5.4, plan Step 4)
- [x] daily_graph.py + daily_workflow.py | daily_graph.py (typo fix + SegmentContext)

### Step 5-6: Verification (→ ROADMAP 2.5.5-2.5.6, plan Steps 5-6)
- [x] mypy strict compliance (0 errors from 171) | 22 files fixed
- [x] Full verification suite (tests, ruff, grep checks) | all gates green

---

## Completed

- [x] Phase 1: Vertical Slice | all 1.0-1.4 tasks
- [x] Phase 2: Intelligence Layer | neurostate, patterns, energy, crisis, effectiveness
- [x] Deep audit: 14 bugs fixed, 514 lint errors resolved, 689 tests added

---

## Session Log

| Date | Task | Notes |
|------|------|-------|
| 2026-02-13 | Phase 1 Complete | Security, Foundation, Modules, Workflow, Coaching |
| 2026-02-13 | Phase 2 Complete | Neurostate, Patterns, Energy, Crisis, Effectiveness |
| 2026-02-14 | Deep Audit Complete | 14 bugs, 514 lint errors, 689 tests |
| 2026-02-14 | Quality Upgrade Plan | docs/HYBRID-QUALITY-UPGRADE-PLAN.md created |
| 2026-02-14 | Security Audit Fix Session 1 | 16 findings fixed (6 groups), 11 files modified, mypy 0 errors |
| 2026-02-14 | Security Audit Fix Session 2 | 8 remaining findings fixed (crisis data leak, Redis TLS, migration models, consent text, rate limiter fail-closed, revenue encryption, dep pinning, user IDs in logs) |
