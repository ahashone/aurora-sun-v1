# AGENTIC WORKFLOWS -- Aurora Sun V1

> **Follow step-by-step.** Every workflow is a checklist. Skip steps only if Ahash says so.
>
> Referenced from: CLAUDE.md

---

## WF-1: Feature Implementation

**Trigger:** Ahash requests a new feature or module.

```
1. READ    -> TODO.md, ARCHITECTURE.md, relevant existing code
2. PLAN    -> Write implementation plan, show to Ahash, wait for OK
3. BRANCH  -> Create feature branch: feature/<name>
4. SECURITY CHECK -> Any new data models? Assign data classification (→ ARCHITECTURE.md Security & Privacy Architecture).
                     Art. 9 fields? → must use EncryptionService. No exceptions.
5. CODE    -> Implement in small commits (each commit = one logical unit)
              Per commit: run tests -> auto-push -> auto-doc (IMPLEMENTATION-LOG + TODO)
6. VERIFY  -> Run full test suite, manual smoke test if UI-facing
7. QA      -> Run Light QA (→ docs/QA-AUDIT-CHECKLIST.md: Phase 1 + 2.1-2.2 + 4.1)
8. MERGE   -> PR to main (or direct merge if Ahash approved)
9. DOC     -> Update ARCHITECTURE.md (if structural), README.md (if user-facing)
10. ASK    -> "Feature complete and pushed. Should I deploy to production?"
11. DEPLOY -> Only after Ahash confirms. SSH -> pull -> restart -> health check
```

---

## WF-2: Bug Fix

**Trigger:** Bug reported or discovered during development.

```
1. REPRODUCE -> Confirm the bug exists, document exact steps
2. DIAGNOSE  -> Find root cause, identify affected files
3. PLAN      -> If non-trivial (>20 lines or multi-file): show plan, wait for OK
                If trivial (<20 lines, single file): fix directly
4. FIX       -> Implement fix
5. TEST      -> Write regression test if none exists, run all related tests
6. COMMIT    -> Commit with message: "fix: <description>" -> auto-push -> auto-doc
7. ASK       -> "Bug fix pushed. Should I deploy?"
```

---

## WF-3: Refactoring

**Trigger:** Code smell, duplication, or structural improvement needed.

```
1. SNAPSHOT  -> Run full test suite, record baseline (all tests must pass)
2. PLAN      -> Document what changes and WHY, show to Ahash
3. REFACTOR  -> Small commits, each one keeps tests green
                If a commit breaks tests: REVERT immediately, rethink approach
4. VERIFY    -> Full test suite must match or exceed baseline
5. COMMIT    -> auto-push -> auto-doc
6. ASK       -> "Refactoring complete. Should I deploy?"
```

---

## WF-4: Database / Schema Migration

**Trigger:** Any change to PostgreSQL, Neo4j, or Qdrant schemas.

```
1. PLAN       -> Document current schema, proposed changes, migration path
                 Show to Ahash, wait for OK (ALWAYS -- no exceptions)
2. CLASSIFY   -> Assign data classification to ALL new fields/tables.
                 Art. 9? → field-level encryption mandatory. Update ARCHITECTURE.md classification matrix.
3. BACKUP     -> Create backup script / document rollback procedure
4. MIGRATION  -> Write migration script (forward + rollback)
                 Encrypted fields: migration must handle encrypt-on-write for existing data
5. TEST       -> Run migration on local/test environment first
6. COMMIT     -> auto-push -> auto-doc (ARCHITECTURE.md mandatory)
7. ASK        -> "Migration ready. Should I deploy? Rollback procedure: [describe]"
8. DEPLOY     -> Only after Ahash confirms. Run migration -> verify data integrity
```

---

## WF-5: New Module Integration

**Trigger:** Adding a new pluggable module (Habits, Limiting Beliefs, etc.)

```
1. READ      -> Module Interface contract, existing modules for patterns
2. PLAN      -> Define: hooks, events, coaching triggers, neurotype-specific behavior
                Show to Ahash, wait for OK
3. SCAFFOLD  -> Create module structure following existing patterns
4. IMPLEMENT -> Core logic -> event subscriptions -> coaching triggers -> tests
                Small commits throughout, each with auto-push + auto-doc
5. INTEGRATE -> Register module, verify event flow with existing modules
6. TEST      -> Module tests + integration tests + verify no regression
7. QA        -> Run Light QA (→ docs/QA-AUDIT-CHECKLIST.md: Phase 1 + 2.1-2.2 + 4.1)
8. DOC       -> ARCHITECTURE.md (mandatory), README.md, API.md if endpoints added
9. ASK       -> "Module [name] complete. Should I deploy?"
```

---

## WF-6: Agent Work (Aurora / TRON / Avicenna / RIA)

**Trigger:** Changes to any agent's or service's behavior or logic.

```
1. READ      -> Current agent/service code, domain docs
2. PLAN      -> Document behavioral change, expected impact
                Neurotype impact assessment (does this affect segment-specific behavior?)
                Show to Ahash, wait for OK
3. IMPLEMENT -> Logic changes
4. TEST      -> Agent-specific tests + verify no cross-agent interference
                For Aurora: test per-neurotype response variations
                For RIA: test finding generation with applicable_segments
5. COMMIT    -> auto-push -> auto-doc
6. ASK       -> "Agent [name] updated. Should I deploy?"
```

---

## WF-7: Multi-Task Parallel Execution

**Trigger:** 3+ independent tasks identified that don't share files or dependencies.

```
1. IDENTIFY  -> List all tasks, confirm independence (no shared files/state)
2. ASSIGN    -> Spawn sub-agents per task (model per task type table)
3. MONITOR   -> Collect results from all sub-agents
4. VERIFY    -> Run full test suite (parallel work can cause subtle conflicts)
5. COMMIT    -> One commit per task, each with auto-push + auto-doc
6. REPORT    -> Summary of all completed tasks to Ahash
```

---

## WF-8: Session Start

**Trigger:** Every new working session (MANDATORY, no exceptions).

```
1. READ      -> TODO.md
2. READ      -> IMPLEMENTATION-LOG.md (last 5 entries for context)
3. STATUS    -> git status, check for uncommitted changes
4. ASSESS    -> If TODO.md empty -> read ROADMAP.md, propose next tasks
                If TODO.md has items -> prioritize and propose order
5. REPORT    -> "Here's what's pending: [list]. I suggest starting with [X]. OK?"
6. WAIT      -> For Ahash's direction before starting any work
```

---

## WF-9: Session End

**Trigger:** Ahash signals end of session OR extended inactivity.

```
1. COMMIT    -> Any uncommitted work (with proper message)
2. PUSH      -> Ensure everything is pushed
3. DOC       -> Final TODO.md update, IMPLEMENTATION-LOG.md entries
4. SUMMARY   -> "This session: [what was done]. Open items: [what remains]."
5. REMIND    -> Weekly reminder check (if applicable)
```

---

## Workflow Override Rules

- Ahash can skip any step by saying so explicitly
- If in Bypass Permissions mode: skip ASK steps, execute directly
- If a workflow step fails: STOP, report, wait for instructions
- Workflows can be nested (e.g., WF-1 discovers a bug -> triggers WF-2 mid-flow)

---

## Auto-Push Rules

After every commit:
1. Run relevant tests (if any exist for changed code)
2. If tests pass (or no tests affected): `git push` automatically
3. If tests fail: STOP, report failure, do NOT push

Push target: current working branch (never force-push to main).

---

## Deployment Rules

Aurora Sun V1 is a LIVE production system. Deployment is NEVER automatic.

After completing a programming task:
1. Push code (auto-push as above)
2. ASK Ahash: "Code is pushed. Should I deploy to production?"
3. Only deploy after explicit confirmation
4. Deployment procedure: SSH to server -> pull latest -> restart containers -> verify health
5. After deploy: confirm service is running, report any errors immediately

---

## Auto-Documentation Rules

Documentation updates happen AUTOMATICALLY after every change. No exceptions.

| Change Size | What Gets Updated |
|-------------|-------------------|
| Any change | `TODO.md` (mark done / add new), `IMPLEMENTATION-LOG.md` (one-liner) |
| Feature / behavior change | Above + `README.md` (if user-facing), `ARCHITECTURE.md` (if structural) |
| Schema / data flow change | Above + `ARCHITECTURE.md` (mandatory) |
| New dependency | Above + `pyproject.toml` |

### IMPLEMENTATION-LOG.md Format

```markdown
## YYYY-MM-DD

- **[component]** Brief description of change | files: `file1.py`, `file2.py`
```

Every entry, no matter how small. This is the project's memory.

### Documentation Commit Rule

Documentation updates are committed TOGETHER with the code change in the same commit. Not in a separate "docs update" commit afterward.

---

## QA & Audit Rules (MANDATORY)

Two audit documents exist. They serve different purposes:

| Document | Purpose | Scope |
|----------|---------|-------|
| **`docs/QA-AUDIT-CHECKLIST.md`** | Post-code quality: linting, tests, security, performance | Code-level (after features, before deploy) |
| **`docs/ARCHITECTURE-AUDIT.md`** | System-level stress test: architecture, resilience, segment consistency, failure modes | System-level (at phase transitions, on request) |

### QA Triggers (code-level)

| Trigger | What Runs | Autonomy |
|---------|-----------|----------|
| **Feature complete** (WF-1, WF-5) | **Light QA**: Phase 1 (static) + Phase 2.1-2.2 (unit tests) + Phase 4.1 (input validation) | Autonomous. Run without asking. |
| **Before deployment** | **Pre-Deploy QA**: Phase 2.5 (regression) + Phase 4 (security) + Phase 8 (readiness) | Autonomous. Report result to Ahash. |
| **Phase transition** (ROADMAP phase complete) | **Full QA Audit**: All 8 phases. Output: `QA-REPORT.md` | Autonomous. Report executive summary to Ahash. |

### Architecture Audit Triggers (system-level)

| Trigger | What Runs | Autonomy |
|---------|-----------|----------|
| **Phase transition** (ROADMAP phase complete) | **Full Architecture Audit**: All 10 sections + 7 stress test scenarios. Output: `AUDIT-REPORT.md` | Autonomous. Report executive summary to Ahash. |
| **Major architecture change** | Sections 1 (Architecture), 2 (Segments), 8 (Performance) minimum | Autonomous. Report findings to Ahash. |
| **Ahash requests** | Targeted sections as specified | As directed. |

### General Rules

- Light QA runs **automatically** after every feature/module completion. No question needed.
- QA-REPORT.md and AUDIT-REPORT.md are cumulative -- updated per audit, not replaced.
- Segment-specific checks are **always** included regardless of trigger level.
- At phase transitions: **BOTH** audits run (QA first, then Architecture).

---

*Extracted from CLAUDE.md. 9 workflows + auto-push/doc/deploy/QA rules.*
