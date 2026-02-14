# Hybrid Quality Upgrade Plan

> **Context:** Aurora Sun V1 (Phase 1+2) was implemented by MiniMax in <1 day. A deep audit by Opus
> found and fixed 14 critical bugs, resolved 514 lint errors, and added 689 tests. Post-audit
> assessment identified 5-6 files with systemic quality issues (threading.Lock in async, in-memory
> state, segment violations, placeholder logic) and ~10 untested files (modules, bot, registry)
> that need inspection.
>
> **Goal:** Production-quality Phase 1+2 code — rewrite the broken files, inspect and fix the
> untested files, keep the clean tested files.
>
> **Branch:** `claude/hybrid-quality-upgrade`
>
> **Reference:** ROADMAP.md Phase 2.5 checkboxes track progress.

---

## Step 0: Branch Setup

1. Checkout the audit branch: `git checkout -b claude/hybrid-quality-upgrade origin/claude/fix-audit-issues-sXhRs`
2. Verify: `pytest tests/ -v` (expect 689 passing)
3. Verify: `ruff check src/` (expect 0 errors)

---

## Step 1: Rewrite Critical Files (5-6 files)

These files have known systemic issues. Rewrite from scratch using ARCHITECTURE.md as spec and existing tests as contracts.

### 1.1 src/services/state_store.py (~180 lines)

- **Issues:** threading.Lock in async code, wrong LRU eviction (evicts oldest, not least-recently-used), in-memory only
- **Rewrite:** asyncio.Lock, proper LRU with OrderedDict, Redis persistence with in-memory fallback

### 1.2 src/services/tension_engine.py (~319 lines)

- **Issues:** `Literal[0,1] = Literal[0,1]` type bug, in-memory state dict
- **Rewrite:** Proper type annotations, Redis/DB persistence for user tension state, correct quadrant logic (SWEET_SPOT/AVOIDANCE/BURNOUT/CRISIS)

### 1.3 src/services/energy_system.py (~1,016 lines)

- **Issues:** 4 segment code checks (`if segment == "AD"` etc.), some placeholder energy calculations
- **Rewrite:** Route energy logic through SegmentContext.neuro fields (burnout_model, energy_assessment, etc.), implement real IBNS/PINCH (ADHD), sensory-cognitive (Autism), ICNU/spoon-drawer (AuDHD), standard (NT) calculations

### 1.4 src/services/pattern_detection.py (~954 lines)

- **Issues:** Segment string matching in signal filtering
- **Rewrite:** Use SegmentContext.features and .neuro fields for signal relevance filtering instead of code comparison. Implement the 5 destructive cycles + 18 daily burden signals properly.

### 1.5 src/services/coaching_engine.py (~1,786 lines)

- **Issues:** Segment code checks for coaching protocol selection, placeholder coaching responses
- **Rewrite:** Protocol selection via SegmentContext.neuro.inertia_type, .neuro.burnout_model, .features.channel_dominance_enabled. Real LangGraph workflow: Router → Enrich → Coach → Memory → Summary with 4-tier fallback.

### 1.6 src/services/effectiveness.py (~921 lines)

- **Issues:** Placeholder measurement methods returning hardcoded values
- **Rewrite:** Real intervention tracking (DB-backed), real outcome measurement with behavioral signals (task completion rate, response latency, session length, pattern recurrence, energy trajectory). Per-segment variant comparison.

---

## Step 2: Deep Inspect & Fix Untested Files (~10 files)

Read each file thoroughly. Fix issues found. If a file is fundamentally broken → rewrite. If it's mostly fine → targeted fixes.

### 2.1 Modules (7 files)

- **src/modules/planning.py** (1,179 lines) — Check: state machine correctness, segment context usage (should use core.max_priorities, core.sprint_minutes), GDPR methods
- **src/modules/review.py** (643 lines) — Check: state machine, segment-adapted reflection prompts
- **src/modules/capture.py** (936 lines) — Check: fire-and-forget classification, GDPR methods
- **src/modules/future_letter.py** (697 lines) — Check: state machine, GDPR methods
- **src/modules/belief.py** (1,320 lines) — Check: cognitive reframing logic, GDPR
- **src/modules/habit.py** (1,380 lines) — Check: atomic habits flow, GDPR
- **src/modules/motif.py** (1,502 lines) — Check: pattern recognition, GDPR

**Focus:** No segment code comparisons in modules. All GDPR methods implemented. State machines follow ARCHITECTURE.md specs. Proper async patterns.

### 2.2 Bot & Infrastructure (3 files)

- **src/bot/webhook.py** (432 lines) — Check: NLI routing, error handling, rate limiting
- **src/bot/onboarding.py** (516 lines) — Check: Redis persistence (already fixed in audit), state machine correctness
- **src/core/module_registry.py** (244 lines) — Check: intent mapping, hook collection

### 2.3 Supporting files

- **src/core/segment_service.py** (123 lines) — Check: SegmentContext factory usage
- **src/services/redis_service.py** (139 lines) — Check: connection handling, error recovery
- **src/services/revenue_tracker.py** (638 lines) — Check: financial encryption, GDPR

---

## Step 3: Neurostate Services Inspection (~6 files)

These have tests (burnout: 57, inertia: 48) but the untested ones (sensory, energy, masking, channel) need review:

- **src/services/neurostate/sensory.py** (315 lines) — Check: cumulative load (NO habituation for AU/AH)
- **src/services/neurostate/energy.py** (515 lines) — Check: behavioral proxy for AU/AH (not self-report)
- **src/services/neurostate/masking.py** (450 lines) — Check: exponential for AuDHD (not linear)
- **src/services/neurostate/channel.py** (418 lines) — Check: channel dominance detection for AuDHD
- **src/services/neurostate/__init__.py** (73 lines) — Check: proper exports

---

## Step 4: Workflows Inspection (2 files)

- **src/workflows/daily_graph.py** (671 lines) — Check: LangGraph StateGraph correctness, segment-adaptive timing
- **src/workflows/daily_workflow.py** (753 lines) — Check: node implementations, tiered neurostate pre-flight

---

## Step 5: mypy Strict Compliance

Run `mypy src/ --strict` and fix all errors. Target: 0 errors (from 171).

---

## Step 6: Verification

1. `pytest tests/ -v` — All 689 tests pass
2. `ruff check src/` — 0 lint errors
3. `mypy src/ --strict` — 0 or near-0 errors
4. `grep -r "if.*segment.*==" src/` — 0 hits in modules, minimal in services (only for dispatch)
5. `grep -r "threading.Lock" src/` — 0 hits
6. `grep -r "in-memory\|_states\s*=" src/` — No user state in memory dicts

---

## Step 7: Documentation Updates

All in the SAME commit as code changes:
- TODO.md — Mark completed items
- IMPLEMENTATION-LOG.md — Log the upgrade
- ROADMAP.md — Check off Phase 2.5 checkboxes

---

## Execution Strategy

- **Parallel sub-agents** for independent rewrites (Step 1 files are independent of each other)
- **Parallel sub-agents** for module inspections (Step 2 modules are independent)
- **Sequential** for verification (Step 6 depends on all fixes)
- **Test after each major step** to catch regressions early

---

## Files NOT Touched (Phase 3, carry forward)

- src/agents/aurora/* (5,380 lines)
- src/agents/tron/* (2,680 lines)
- src/agents/avicenna/* (1,370 lines)
- src/services/knowledge/* (3,600 lines)
- src/services/ria_service.py (1,528 lines)
- src/services/second_brain.py (1,173 lines)
- src/services/feedback_service.py (935 lines)

## Files NOT Touched (Clean, tested)

- src/lib/encryption.py (39 tests)
- src/lib/security.py (141 tests)
- src/lib/gdpr.py (55 tests)
- src/models/consent.py (54 tests)
- src/core/segment_context.py (94 tests)
- src/services/crisis_service.py (201 tests)
- src/services/neurostate/burnout.py (57 tests)
- src/services/neurostate/inertia.py (48 tests)

---

_Created 2026-02-14. Branch: claude/hybrid-quality-upgrade._
