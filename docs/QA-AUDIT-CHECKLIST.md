# QA Audit Checklist -- Aurora Sun V1

> **Purpose:** Systematic post-code quality assurance and security audit.
> Referenced from CLAUDE.md. Executed at defined trigger points.
> Output: `QA-REPORT.md` in project root (updated per phase).
>
> **Language Rule applies:** All output in English.

---

## TRIGGER LEVELS

| Trigger | Phases to Run | When |
|---------|---------------|------|
| **Light QA** | Phase 1 + Phase 2 (unit only) + Phase 4.1 | After every completed feature (WF-1) or module (WF-5) |
| **Pre-Deploy QA** | Phase 2.5 + Phase 4 + Phase 8 | Before every production deployment |
| **Full Audit** | All 8 phases, sequentially | At ROADMAP phase transitions (e.g. Phase 1→2) |

---

## PHASE 1: CODE REVIEW & STATIC ANALYSIS

### 1.1 Structural Integrity
- [ ] Read entire codebase. Create **dependency map** of all modules/files and their relationships.
- [ ] Identify **dead code paths** (unreachable functions, unused imports, orphaned files).
- [ ] Check for **circular dependencies**.
- [ ] Verify all **environment variables** are documented with defaults/validation.

### 1.2 Code Quality
- [ ] Run available **linters** (`ruff`, `mypy`, etc.) and fix all findings.
- [ ] Check **type safety** -- missing types, `Any` abuse, implicit casts.
- [ ] Identify **code smells**: god-functions (>50 lines), deep nesting (>3 levels), magic numbers, duplication.
- [ ] Check **naming conventions** -- self-explanatory, consistent.

### 1.3 Architecture Check
- [ ] Check **separation of concerns** -- business logic, I/O, and presentation mixed?
- [ ] Evaluate **error handling strategy** -- consistent pattern? Errors swallowed?
- [ ] Check **configuration management** -- hardcoded values, environment-specific configs.

**→ Document all findings in QA-REPORT.md under `## Phase 1: Static Analysis`**

---

## PHASE 2: TESTING -- DEEP ANALYSIS

> Core phase. Be thorough to the point of paranoia.

### 2.1 Test Inventory
- [ ] Create **test coverage matrix**: every function/method/route → which tests exist? Which are missing?
- [ ] Categorize existing tests: Unit | Integration | E2E | Property-Based
- [ ] Identify **untested critical paths** (auth, payments, data validation, state transitions).

### 2.2 Unit Tests -- Write & Execute
Per function, test at minimum:
```
├── Happy Path (expected input → expected result)
├── Edge Cases
│   ├── Empty inputs (None, "", [], {})
│   ├── Boundary values (0, -1, MAX_INT, very long strings)
│   ├── Type mismatches (str instead of int, etc.)
│   └── Unicode / special characters / injection strings
├── Error case (invalid input → correct error handling)
├── State dependencies (behavior under different preconditions)
└── Concurrency (if relevant: race conditions, parallel calls)
```
- [ ] Write tests for **all exported functions**.
- [ ] Write tests for **all private helpers** with complex logic.
- [ ] Use **mocks/stubs** for external dependencies (DB, APIs, filesystem).
- [ ] Run all tests. **100% of written tests must be green** before proceeding.

### 2.3 Integration Tests
- [ ] Test **all API endpoints** (request → response, including errors, rate limiting, auth).
- [ ] Test **database interactions** (CRUD cycles, constraints, migrations up AND down).
- [ ] Test **service-to-service communication**.
- [ ] Test **middleware chain** (auth → validation → handler → error handler).
- [ ] Simulate **external API failures** (timeouts, 500s, malformed responses).

### 2.4 Edge Case & Stress Tests
- [ ] **Boundary testing**: all numeric inputs at min/max limits.
- [ ] **Injection testing**: SQL injection, XSS payloads, command injection in all user inputs.
- [ ] **Encoding**: UTF-8 edge cases, emoji, RTL text, null bytes.
- [ ] **Timing**: race conditions on parallel writes.
- [ ] **Resource limits**: very large payloads? Very many concurrent requests?
- [ ] **State corruption**: what happens on abort mid-transaction?

### 2.5 Regression Tests
- [ ] Verify **all existing tests** still green.
- [ ] Check that new changes don't **break existing functionality**.
- [ ] Test **backward compatibility** of API changes.

### 2.6 Test Coverage Measurement
- [ ] Run coverage tool (`coverage`, `pytest-cov`, etc.).
- [ ] **Target**: ≥80% line coverage, ≥70% branch coverage.
- [ ] Document **uncovered areas** with justification ("purely declarative" vs "TODO: test missing").

**→ Document in QA-REPORT.md under `## Phase 2: Testing`**
**→ Include: test count, coverage %, list of critical untested paths, test execution log**

---

## PHASE 3: DEBUGGING -- SYSTEMATIC BUG HUNTING

> Not just fix bugs -- **understand why** they occur.

### 3.1 Bug Triage
- [ ] Collect all failed tests, linter errors, runtime warnings.
- [ ] Categorize by **severity**:
  - CRITICAL: data loss, security hole, crash
  - HIGH: wrong results, broken UX flow
  - MEDIUM: performance issue, edge case
  - LOW: cosmetic, logging, naming

### 3.2 Root Cause Analysis (per bug)
For every bug ≥ MEDIUM:
```
Bug ID: #XXX
Symptom: [What happens?]
Reproduction: [Exact steps]
Root Cause: [WHY does it happen? Not just WHERE.]
Category: [Logic Error | Race Condition | Missing Validation | Type Error | Config Issue | ...]
Fix: [What was changed?]
Verification: [Which test proves the fix?]
Regression Risk: [Could this fix break something else?]
```

### 3.3 Defensive Code Review Post-Fix
- [ ] Check every fix for **side effects**.
- [ ] Ensure fixes don't **introduce new edge cases**.
- [ ] Run **full test suite** after every fix.

### 3.4 Error Handling Hardening
- [ ] Check **every try/except block**: errors logged correctly? Re-raised correctly?
- [ ] Any **unhandled exceptions**?
- [ ] Check **graceful degradation**: what happens when external services are down?
- [ ] Validate **error messages**: helpful for debugging WITHOUT leaking sensitive data?

### 3.5 Logging & Observability
- [ ] **Structured logs** present (JSON format, correlation IDs)?
- [ ] All **critical paths** logged (auth attempts, state changes)?
- [ ] **Log levels** (debug/info/warn/error) correctly assigned?
- [ ] **No sensitive content** logged (passwords, tokens, PII)?

**→ Document in QA-REPORT.md under `## Phase 3: Debugging`**
**→ Include: bug list with root cause analysis, fix verification status**

---

## PHASE 4: SECURITY AUDIT

### 4.1 Input Validation
- [ ] **All** user inputs validated (type, length, format, allowed values).
- [ ] **Sanitization** against XSS, SQL injection, path traversal.
- [ ] **File uploads**: type validation (not just extension), size limits, malware vectors.

### 4.2 Authentication & Authorization
- [ ] Tokens: correct expiration, secure storage, rotation.
- [ ] Every endpoint has **explicit auth checks** (not "open by default").
- [ ] **RBAC/permissions**: horizontal and vertical privilege escalation tested.
- [ ] **Rate limiting** on auth endpoints.

### 4.3 Data Protection
- [ ] **Secrets** not in code (no hardcoded API keys, passwords).
- [ ] **Encryption**: data at rest and in transit.
- [ ] **PII handling**: personal data handled correctly?
- [ ] **CORS**: correctly configured, no wildcard `*` in production.

### 4.4 Dependency Security
- [ ] `pip audit` / dependency audit -- all known CVEs fixed or documented.
- [ ] **Lockfiles** present and current.
- [ ] No **outdated dependencies** with known vulnerabilities.

**→ Document in QA-REPORT.md under `## Phase 4: Security`**

---

## PHASE 5: PERFORMANCE & OPTIMIZATION

### 5.1 Performance Analysis
- [ ] Identify **N+1 queries** and other DB performance killers.
- [ ] Check for **memory leaks** (event listeners, closures, caches without eviction).
- [ ] Identify **unnecessary computations** in hot paths.

### 5.2 Scalability
- [ ] Are there **bottlenecks** under increasing load?
- [ ] Are **caching strategies** implemented where sensible?
- [ ] Are **database indexes** used correctly?

**→ Document in QA-REPORT.md under `## Phase 5: Performance`**

---

## PHASE 6: REFACTORING

### 6.1 Code Cleanup
- [ ] Remove **dead code**, commented-out blocks, stale TODOs.
- [ ] Extract **reusable utilities** from duplicated code.
- [ ] Simplify **complex functions** (max 1 responsibility per function).
- [ ] Standardize **error handling patterns** across codebase.

### 6.2 API Design Review
- [ ] Endpoints **consistently named** (REST conventions or chosen schema)?
- [ ] **Response formats** uniform (envelope pattern, error format)?
- [ ] **Versioning** implemented if needed?

**→ Document in QA-REPORT.md under `## Phase 6: Refactoring`**

---

## PHASE 7: DOCUMENTATION

### 7.1 Code Documentation
- [ ] **Every exported function/class** has a docstring with: description, parameters, return value, errors, example.
- [ ] **Complex algorithms** have inline comments explaining WHY (not WHAT).
- [ ] **No open TODOs** without issue reference.

### 7.2 README.md
- [ ] Project description (1-3 sentences).
- [ ] Setup instructions (prerequisites → install → run → test).
- [ ] Architecture overview.
- [ ] Environment variables table (name | description | default | required?).
- [ ] Deployment instructions.
- [ ] Known issues / limitations.

### 7.3 Architecture Documentation
- [ ] **ADRs** for all non-obvious decisions.
- [ ] **Data flow diagram** for critical paths.
- [ ] **Error handling documentation**: propagation, retry strategies.

**→ Document in QA-REPORT.md under `## Phase 7: Documentation`**

---

## PHASE 8: DEPLOYMENT READINESS

### 8.1 Pre-Deployment Checklist
- [ ] All tests green (unit + integration + E2E).
- [ ] Coverage ≥ target values.
- [ ] No critical security findings open.
- [ ] No critical performance issues open.
- [ ] Documentation current.
- [ ] Lockfiles committed.
- [ ] `.env.example` current.
- [ ] **Rollback plan** exists.
- [ ] **Monitoring/alerting** configured.
- [ ] **Health check endpoint** present.

### 8.2 Executive Summary
Create at the end of QA-REPORT.md:
```markdown
## Executive Summary

### Status: READY / READY WITH CAVEATS / NOT READY

### Metrics
- Tests: X written, Y passed, Z failed
- Coverage: X% lines, Y% branches
- Security findings: X critical, Y high, Z medium
- Performance issues: X identified, Y fixed
- Bugs: X found, Y fixed, Z open

### Open Risks
1. [Risk] -- [Impact] -- [Mitigation]

### Recommendations
1. [Priority] [Recommendation]
```

---

## META RULES

1. **Work sequentially.** Don't skip phases.
2. **Fix problems immediately** when found -- then document.
3. **When uncertain**, choose the more conservative/safer option.
4. **Run tests again after EVERY fix.**
5. **Ask Ahash** if context is missing (e.g. which endpoints are public vs internal).
6. **QA-REPORT.md is mandatory** -- it's the proof that the work was done.
7. **Be brutally honest** in assessment. A polished report is worthless.

---

## SEGMENT-SPECIFIC QA RULES (Aurora Sun specific)

In addition to standard QA, every audit MUST verify:

- [ ] **No segment code in modules**: no `if segment == "AD"` -- only SegmentContext fields
- [ ] **Segment isolation**: findings/interventions tagged with `applicable_segments`
- [ ] **Anti-pattern scan**: check against all anti-patterns in ARCHITECTURE.md
- [ ] **Shame-free language**: no blame, no guilt, no "you failed" in any user-facing string
- [ ] **GDPR compliance**: every module implements `export_user_data()` + `delete_user_data()`
- [ ] **Intervention tracking**: every intervention registered with EffectivenessService
- [ ] **Crisis safety**: crisis override (SW-11) reachable from every active state

---

*QA Audit Checklist for Aurora Sun V1. Created 2026-02-13.*
*Referenced from CLAUDE.md. Full audit at phase transitions, light QA per feature.*
