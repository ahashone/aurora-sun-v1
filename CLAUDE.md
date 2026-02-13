# AURORA SUN V1 -- Master Prompt for Claude Code

> **Context:** Aurora Sun V1 is an AI coaching system for neurodivergent people.
> Successor to Ravar V7. Complete rebuild with hindsight-informed architecture.
> Read this document completely. It defines all working rules.

**Language Rule:** The project owner (Ahash) gives instructions in German. ALL implementation, documentation, TODO items, roadmap entries, architecture docs, code comments, commit messages, and any other written output MUST be in English. This rule has no exceptions.

---

## PROJECT OVERVIEW

Aurora Sun V1: AI coaching for neurodivergent people. 3 Pillars (Vision-to-Task, Second Brain, Money), 3 Agents (Aurora, TRON, Avicenna), 6 Services, 8+ Modules. All via natural language.

**Full system description → ARCHITECTURE.md** (single source of truth).

---

## WORKING METHODOLOGY

### Model Selection & Sub-Agents (APPLY AUTOMATICALLY)

**Default Model: MiniMax (MiniMax-M2.5)** -- Use for all tasks EXCEPT planning.
**Opus: Planning + Verification** -- Plan Mode + Review MiniMax's output.

| Task | Model | Sub-Agent? |
|------|-------|------------|
| **Planning** (EnterPlanMode) | **Opus** | If needed |
| **Verification** (review MiniMax's work) | **Opus** | No |
| All other tasks | **MiniMax** | **ALWAYS use 3-5 sub-agents in parallel** |

- MiniMax is the default for: coding, documentation, bug fixes, git operations, file edits, reading code, writing code, implementing features, running tests, deployments, refactoring, architecture changes, security reviews
- Opus is reserved for: (1) Plan Mode tasks, (2) verifying MiniMax's code/tests before commit
- **Parallel Sub-Agents: ALWAYS spawn 3-5 sub-agents for any non-trivial task.** Break the work into independent chunks and assign to sub-agents. This is MANDATORY.
- If MiniMax fails verification -> Fix with MiniMax, re-verify with Opus

### Folder Structure (top-level only)

```
aurora-sun-v1/
├── src/           # agents/, services/, modules/, core/, models/, lib/, config.py
├── migrations/    # Alembic
├── tests/         # Mirrors src/
├── workflows/     # Process descriptions
├── scripts/       # Reusable scripts
├── knowledge/     # Research, findings, proposals (persistent)
├── external/      # Handover for external agents
├── docs/          # Active specs + docs/archive/ (never delete)
├── temp/          # Temporary (gitignored)
└── [root files]   # CLAUDE.md, ARCHITECTURE.md, ROADMAP.md, TODO.md, README.md,
                   # IMPLEMENTATION-LOG.md, main.py, pyproject.toml, Dockerfile, docker-compose.yml
```

### Documentation Lifecycle & Report Handling (MANDATORY)

**Root level:** ONLY active, constantly referenced files:
- Governance: `CLAUDE.md`, `README.md`, `ROADMAP.md`, `TODO.md`
- Architecture: `ARCHITECTURE.md`, `IMPLEMENTATION-LOG.md`
- Code/Config: `main.py`, `Makefile`, `setup.sh`, `deploy.sh`, `Dockerfile*`, `docker-compose*.yml`, `pyproject.toml`, `.env*`

**One-off reports immediately to `docs/archive/`:** Implementation reports, session summaries, status snapshots, audit/migration/verification reports, completed setup docs.

**docs/ level:** Active reference docs (guides, specs, policies like `GOVERNANCE.md`, `API.md`, `SECURITY.md`).

**Archival rule:** Report older than 2 weeks + purpose fulfilled + not regularly referenced -> `docs/archive/` (git mv).

**Before creating a new report:** `ls docs/*.md` / `git grep` -- avoid duplicates, use references instead of copies.

**temp/:** Brainstorming, debugging (gitignored). **knowledge/:** Aggregated findings (persistent).

### Autonomy Modes

| Mode | Behavior | When |
|------|----------|------|
| **Plan Mode** | Think/plan only | **New tasks** |
| **Ask Before Edits** | Asks before changes | Default |
| **Edit Automatically** | Without asking | Trusted tasks |
| **Bypass Permissions** | Full autonomy | **ONLY when actively observed** |

**ALWAYS start in Plan Mode for new tasks.**

### Overnight / Unattended Run Rules

When Ahash is not actively watching (e.g. overnight runs), minimize interruptions:

| Situation | Action |
|-----------|--------|
| Standard TODO item from current phase | **Proceed autonomously.** Implement, test, commit, push, update docs. No question needed. |
| Ambiguous requirement (multiple valid approaches) | **Pick the simplest approach, document the decision in IMPLEMENTATION-LOG.md**, continue. |
| Non-critical test failure (single test, obvious fix) | **Fix and continue.** |
| Critical failure (build broken, multiple tests fail, data loss risk) | **STOP. Leave detailed message for Ahash.** Do not attempt speculative fixes. |
| Structural architecture decision (new component, schema change, new module) | **STOP. Leave detailed message for Ahash.** |
| Security-relevant change | **STOP. Leave detailed message for Ahash.** |
| Deployment to production | **NEVER unattended. Always wait for Ahash.** |
| Phase transition (all checkboxes in a phase done) | **STOP. Report completion, wait for Ahash to confirm next phase.** |

**"Leave detailed message"** = Write to TODO.md: `- [ ] BLOCKED: [description of decision needed] (waiting for Ahash)` + continue with other non-blocked items.

**Rule of thumb:** If the decision is reversible and low-risk → proceed. If irreversible or high-risk → stop and document.

---

## AUTO-PUSH, AUTO-DOCUMENTATION, DEPLOYMENT & QA

**Full rules → `docs/WORKFLOWS.md`** (Auto-Push, Deployment, Auto-Doc, QA/Audit triggers).

**Quick reference:**
- **Auto-push:** Tests pass → `git push`. Tests fail → STOP.
- **Deployment:** NEVER automatic. Always ask Ahash first.
- **Auto-doc:** Every change → TODO.md + IMPLEMENTATION-LOG.md (same commit as code). Schema changes → ARCHITECTURE.md mandatory.
- **Light QA:** Runs automatically after every feature (WF-1, WF-5). No question needed.
- **Phase transition:** Full QA Audit + Architecture Audit, both run automatically.

---

## TRACKING & DOCUMENTATION

### TODO.md (MANDATORY -- read at every work start, update after every task)

- **Max ~30 lines.** Completed items visible for 1 session, then remove.
- Format: `- [ ] Task (→ ROADMAP X.Y, SW-N)` / `- [x] Task | changed files`

#### TODO Lifecycle (the cascade)

```
ROADMAP.md (phase checkboxes)
    |
    | [1] DERIVE: Pick unchecked items from current phase
    |     Reference: "→ ROADMAP 1.3" and "→ SW-1" if applicable
    v
TODO.md (active work items, max ~30)
    |
    | [2] WORK: Implement the task
    |
    | [3] COMPLETE: When task is done, cascade updates:
    v
+--→ TODO.md:           Mark [x] + note changed files
+--→ ROADMAP.md:        Check off the corresponding checkbox
+--→ IMPLEMENTATION-LOG.md: One-liner entry (ALWAYS)
+--→ ARCHITECTURE.md:   Update IF structural/schema/data flow change
+--→ README.md:         Update IF user-facing change
```

#### Rules

| Step | Rule |
|------|------|
| **Session start** | Read TODO.md. If empty → read ROADMAP.md → derive next items. |
| **Deriving TODOs** | Pick from CURRENT phase only. Include ROADMAP section ref + SW ref if a system workflow applies. |
| **After completing a task** | Cascade ALL updates in the SAME commit as the code change. Never a separate "docs update" commit. |
| **ROADMAP checkbox** | Check off IMMEDIATELY when the task is done. Don't batch. Don't forget. This is how progress is tracked. |
| **ARCHITECTURE.md** | Update when: new component, schema change, data flow change, new module registered, workflow behavior change. |
| **Stale TODOs** | If a TODO sits unchecked for 3+ sessions → reassess: still relevant? blocked? needs breakdown? |
| **Phase transition** | When all checkboxes in a ROADMAP phase are checked → report to Ahash: "Phase X complete. Ready for Phase Y?" |

### Additional Files (only when needed)

| File | When |
|------|------|
| **ARCHITECTURE.md** | On component/schema/data flow/workflow changes |
| **README.md** | On new features, commands, endpoints |
| **IMPLEMENTATION-LOG.md** | On every change (auto-documentation) |
| **ROADMAP.md** | Read when TODO.md empty OR direction question. Update checkboxes on task completion. |

---

## NEUROTYPE SEGMENTATION

**This is the most important design rule. Full details → ARCHITECTURE.md Section 3.**

**Key rules for coding:**
- Segments: AD/AU/AH/NT/CU (internal) → ADHD/Autism/AuDHD/Neurotypical/Custom (user-facing). **Never show codes to users.**
- **Never `if segment == "AD"` in code.** Always use SegmentContext fields (4 sub-objects: core, ux, neuro, features).
- Every finding has `applicable_segments`. Every proposal has `target_segment`. Never aggregate across segments.
- Burnout type IDENTIFY before intervening. Sensory state QUERY before planning (AU/AH). Channel dominance CHECK first (AH).

### Anti-Patterns (NEVER)

**Segment:** Universal findings from single-segment validation | ICNU for Autism | System rotation for Autism | "Just start" for Autistic Inertia | Behavioral Activation during Autistic Burnout | AuDHD as "ADHD + Autism combined" | Pomodoro for AU/AD-I deep focus | Same notifications for all | Only self-report for AU/AH energy

**Neurostate:** Sensory habituation for AU/AH (accumulates!) | Masking as binary (AuDHD = exponential) | Same burnout protocol for all (3 types!) | AuDHD without channel dominance check | Time-based deadlines for Autism transitions | "Not responding" = "not engaged" (shutdown ≠ EF collapse)

**Architecture:** `if segment ==` checks | Calling a service an "agent" | DB before data exists | Slash commands required | Daily workflow from module calls | GDPR as afterthought | Art. 9 data without encryption | Data model without classification | Skippable consent gate | Intervention without effectiveness measurement

**Research:** 50-70% Autism literature is ADHD-contaminated — scrutinize | No cross-segment aggregation | No finding without `applicable_segments`

---

## AUTONOMY & SELF-LEARNING

**Full details → ARCHITECTURE.md Sections 11-12.**

**Core rule:** The system learns autonomously. It **never acts** autonomously. It always **proposes.**

- Observe + Think = autonomous. Act = admin approval required.
- ALL changes (prompts, interventions, patterns, flags, architecture, modules, segment logic) → proposal to admin.
- **Exception:** Aurora's proactive impulses (max 3/week) from admin-approved types only.
- 4 feedback loops: PERCEIVE → UNDERSTAND → PROPOSE → VERIFY.

---

## PRINCIPLES

1. **Propose, don't execute.** Show plan, wait for OK. ALWAYS.
2. **Respect existing code.** Extend, don't replace.
3. **NEUROTYPE SEGMENTATION IS NOT OPTIONAL.** No one-size-fits-all. Ever.
4. **Natural Language first.** If a user needs a command, the NLI failed.
5. **All evidence is equal.** Anecdotal = Academic.
6. **Privacy first, security by default.** Only aggregated data. GDPR in every Module Interface. All Art. 9 health data encrypted from day one. No data model without classification. No phase ships without security review. See ARCHITECTURE.md → Security & Privacy Architecture.
7. **Incremental.** Small steps, each measurable.
8. **User > Theory.** User data wins over research.
9. **Transparency.** Explain WHY you suggest something.
10. **Backend exists != Feature exists.** If users can't access it through conversation, it's not done.
11. **System proposes, Admin decides.** Autonomous perception, human action.
12. **Ship > Perfect.** But never ship broken segment logic.
13. **Shame-free language.** CI-enforced. In the DNA.

---

## AGENTIC WORKFLOWS

**Full step-by-step workflows → `docs/WORKFLOWS.md`**. Read before first use.

| Workflow | Trigger | Key Steps |
|----------|---------|-----------|
| **WF-1** Feature | Ahash requests feature | READ → PLAN → BRANCH → **SECURITY CHECK** → CODE → QA → DEPLOY |
| **WF-2** Bug Fix | Bug found | REPRODUCE → DIAGNOSE → FIX → TEST → COMMIT |
| **WF-3** Refactor | Code smell | SNAPSHOT → PLAN → REFACTOR (tests green!) → VERIFY |
| **WF-4** Schema Migration | DB change | PLAN → **CLASSIFY** → BACKUP → MIGRATE → TEST → DEPLOY |
| **WF-5** New Module | New plugin | READ → PLAN → SCAFFOLD → IMPLEMENT → QA → DOC |
| **WF-6** Agent Work | Agent/service change | READ → PLAN (neurotype impact!) → IMPLEMENT → TEST |
| **WF-7** Parallel | 3+ independent tasks | IDENTIFY → ASSIGN sub-agents → VERIFY → REPORT |
| **WF-8** Session Start | Every session (MANDATORY) | READ TODO → READ LOG → git status → ASSESS → REPORT |
| **WF-9** Session End | End of session | COMMIT → PUSH → DOC → SUMMARY → REMIND |

**Override rules:** Ahash can skip steps. Bypass mode → skip ASK. Failure → STOP. Workflows nest (WF-1 → WF-2 mid-flow).

---

## TROUBLESHOOTING

- Service won't start -> Show error, attempt fix, ask if unclear
- Existing code breaks -> STOP IMMEDIATELY, show what happened
- Unsure which segment a finding applies to -> ASK AHASH
- Unsure if a change breaks features -> TEST FIRST, then ask
- Missing package -> Install, document in pyproject.toml

---

## SERVER & DEPLOYMENT

- **SSH:** `ssh root@100.80.51.61` (Tailscale)
- **Path:** `/opt/aurora-sun` (migrated from `/opt/ravar`)
- **Reverse Proxy:** Caddy (Port 80/443, HTTPS active)
- **App User:** `moltbot` (non-root)
- **Server:** Hetzner 4 GB RAM, Nuremberg (`yutur-v1-ubuntu-4gb-nbg1-1`)
- **Databases:** PostgreSQL + Redis (Phase 1-2), + Neo4j + Qdrant + Letta (Phase 3+)
- **Containers:** aurora-sun-app, postgres, redis (Phase 1-2), + neo4j, qdrant, letta, prometheus, grafana, alertmanager, cadvisor, node-exporter, redis-exporter, postgres-exporter (Phase 3+)
- **Security:** fail2ban, Tailscale, HTTPS via Caddy

---

## TECH STACK

**Full stack → ARCHITECTURE.md Section 15.** Key: LangGraph, DSPy, PydanticAI, Anthropic/OpenAI, PostgreSQL/Neo4j/Qdrant/Redis/Letta, AES-256-GCM encryption (all SENSITIVE/ART.9/FINANCIAL fields).

---

## NOTES FOR AI AGENTS

### Quality Over Cost

- Marginally more cost + value -> implement
- Significantly more cost + value -> ask first
- NEVER sacrifice quality for minimal cost savings

### International Audience

- Primary language: English. Additional: German, Serbian, Greek, others
- i18n / multilingual support is **mandatory** from the first commit

### Security (MANDATORY -- applies to every task)

- API keys ALWAYS in `.env`, NEVER in chat history
- Security-critical changes: Owner (Ahash) reviews
- **Every new data model** gets a data classification (PUBLIC/INTERNAL/SENSITIVE/ART_9_SPECIAL/FINANCIAL)
- **Every SENSITIVE/ART.9/FINANCIAL field** uses `EncryptionService` -- no plaintext storage
- **Every new sub-processor** (API, SaaS, LLM provider) documented in ARCHITECTURE.md Sub-Processor Registry
- **Consent is non-negotiable**: no user data stored before consent gate passed
- **DPIA updated** at every phase transition
- Reference: ARCHITECTURE.md → Security & Privacy Architecture

### Research Foundation

216+ findings across 11 meta-syntheses + Product Bible in `knowledge/research/`. **All findings are segment-specific.**

---

## WEEKLY REMINDERS

| Topic | Prompt | Since |
|-------|--------|-------|
| **Phase 0: User Interviews** | "Would you like to start user interviews this week? The guide is ready." | 2026-02-06 |

> Ask once per week, not more often. Ahash decides.

---

*Aurora Sun V1 Master Prompt. Created 2026-02-13.*
*Merged version: system architecture (agents, services, autonomy, self-learning) + development workflows (WF-1 to WF-9, auto-push, auto-doc).*
*Reference documents: ARCHITECTURE.md, ROADMAP.md*
