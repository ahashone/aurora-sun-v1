# ROADMAP -- Aurora Sun V1

> **5 Phases.** Each delivers standalone user value.
> No phase longer than 4-6 weeks.
> Ahash decides priorities. System proposes.
>
> Predecessor: Ravar V7 (research, findings, and learnings carry over).
>
> Created: 2026-02-13

---

## Vision

A coaching system that doesn't "fix" neurodivergent people, but helps them understand their unique working style and use it productively -- from life vision down to today's tasks.

### Three Pillars

| Pillar | What | Interface |
|--------|------|-----------|
| **Vision-to-Task** | Daily workflow: vision → plan → reminders → inline coaching → auto-review. Modules: Habits, Beliefs, Motifs | Natural language (main bot) |
| **Second Brain** | Quick capture of thoughts/tasks/ideas. LLM classification, auto-routing, semantic search, proactive surfacing | Natural language (same bot, fire-and-forget mode) |
| **Money Management** | Quick financial capture ("12 euros for sushi"), auto-budgeting, pattern coaching, shame-free language | Natural language (same bot, fire-and-forget mode) |

### Interaction Principle

**Natural language is the only interaction mode.** Users talk to the bot conversationally. Slash commands exist as optional shortcuts for power users but are never required. A new user can use the entire app without learning a single command.

---

## Phase 0: Discovery & Research
**Status:** Research Complete. Interviews Paused (Ahash decides).
**Duration:** --
**Dependency:** None

This phase is done for research. Interview round remains open.

### Completed (carries over from Ravar V7):
- [x] 5 meta-syntheses (ADHD, Autism, AuDHD, Neurotypical, Custom) -- 56 findings
- [x] 1 cross-synthesis (collision map across segments)
- [x] 3 Daily Burden meta-syntheses (ADHD, Autism, AuDHD) -- 96 findings
- [x] Feature extraction: 25 new features, 10 extensions, 12 design principles, 15 anti-patterns
- [x] 3 Money meta-syntheses -- 60 findings
- [x] Product Bible (8 clusters, 47 design principles, 93 features)
- [x] Interview guide ready

### Open:
- [ ] 10 user interviews (ADHD/Autism/AuDHD communities)
- [ ] Core question: "What is the one moment where an app would need to save you from yourself?"
- [ ] 3 validated destructive cycles from real users

**Weekly reminder:** "Want to start user interviews this week?" (Ahash decides, max 1x/week)

---

## Phase 1: Vertical Slice
**Status:** Not Started
**Duration:** 4-6 weeks
**Dependency:** Phase 0 research (complete)
**Databases:** PostgreSQL + Redis only
**Value:** One user can complete the full daily loop via natural language.

This phase delivers the core experience: a user opens the app, plans their day grounded in their vision, gets reminders, and reviews in the evening. Everything via natural language, everything segment-adapted.

### 1.0: Security Foundation

> **This section is implemented FIRST, before any data model or user interaction exists.**

#### Encryption & Data Classification
- [ ] `src/lib/encryption.py`: EncryptionService (encrypt_field, decrypt_field, rotate_key, destroy_keys)
- [ ] Data classification enum: PUBLIC, INTERNAL, SENSITIVE, ART_9_SPECIAL, FINANCIAL
- [ ] Per-user encryption key generation (on user creation)
- [ ] AES-256-GCM field-level encryption for all SENSITIVE and ART. 9 fields
- [ ] 3-tier envelope encryption for FINANCIAL fields (master → user → field)
- [ ] HMAC-SHA256 hashing for PII identifiers (telegram_id, name lookups)
- [ ] Unit tests: encrypt → decrypt roundtrip, key rotation, key destruction

#### Consent Architecture
- [ ] ConsentRecord model (consent_version, language, timestamp, text_hash)
- [ ] Consent gate in onboarding flow (explicit, not skippable, translated)
- [ ] Consent withdrawal handler ("delete my data" / "I withdraw consent" → SW-15)
- [ ] Consent version tracking (prove which version was accepted)

#### GDPR Foundation
- [ ] Module Protocol extended: `freeze_user_data()`, `unfreeze_user_data()` (Art. 18)
- [ ] Retention policy config (per data classification)
- [ ] Data export format: JSON, machine-readable (Art. 20 portability)
- [ ] `docs/DPIA.md`: Initial Data Protection Impact Assessment

#### Input Security
- [ ] Input sanitization middleware (XSS, SQL injection, path traversal)
- [ ] Per-user rate limiting (message frequency + LLM cost protection)
- [ ] Message size limits at NLI layer
- [ ] Voice message limits (60s / 10MB)

#### Documentation
- [ ] Sub-processor registry documented (Anthropic, OpenAI, Groq, Telegram, Hetzner, Langfuse)
- [x] Breach notification procedure documented
- [ ] Data classification matrix for all Phase 1 tables

### 1.1: Foundation

#### Segment Engine
- [ ] Neurotype segmentation as core data model: AD/AU/AH/NT/CU internal, ADHD/Autism/AuDHD/Neurotypical/Custom user-facing
- [ ] SegmentContext middleware (split: core/ux/neuro/features) -- injected into every interaction
- [ ] Segment config objects: every downstream decision driven by SegmentContext, never by `if segment == "AD"`
- [ ] i18n foundation (en, de, sr, el) baked in from day one

#### Natural Language Interface
- [ ] Intent Router: regex fast path (~70%) + Haiku LLM fallback (~30%)
- [ ] Confidence-based routing: high → auto-route, low → 1 clarifying question
- [ ] State-aware routing: mid-module vs idle behavior
- [ ] Slash command aliases as syntactic sugar for intents

#### Module System
- [ ] Module Interface (Protocol): `handle()`, `on_enter()`, `on_exit()`, `get_daily_workflow_hooks()`, `export_user_data()`, `delete_user_data()`, `freeze_user_data()`, `unfreeze_user_data()`
- [ ] Module Registry: intent → module mapping, auto-discovery
- [ ] ModuleContext: user + SegmentContext + state + session
- [ ] Module lifecycle: enter → handle → exit (with cleanup)
- [ ] GDPR built into interface from day one

#### Bot Scaffold
- [ ] PostgreSQL schema: Users, Sessions, Visions, Goals, Tasks, DailyPlans (SQLAlchemy + Alembic)
- [ ] Redis: event bus + session cache
- [ ] Telegram bot: webhook handler, messages flow through NLI first
- [ ] One bot, two modes: conversational + fire-and-forget capture
- [ ] Onboarding flow: Language → Name → Working style inference (LLM) → **Consent Gate (explicit, Art. 9)** → Confirmation

#### Agentic Stack (Minimal)
- [ ] LangGraph: StateGraph foundation, error nodes
- [ ] DSPy: segment-specific signatures framework (stubs)
- [ ] PydanticAI: structured response models
- [ ] Ahash personality: coach persona system prompt
- [ ] Feature flags: global feature flag system

### 1.2: Core Modules (Pillar 1a)

#### Planning Module
- [ ] State machine: SCOPE → **VISION** → OVERVIEW → PRIORITIES → BREAKDOWN → [SEGMENT_CHECK] → COMMITMENT → DONE
- [ ] **VISION step**: Display user's vision + 90d goals BEFORE task list
- [ ] Vision alignment check: "Does today's plan serve your vision?"
- [ ] Segment-specific: ADHD (max 2 priorities, 25 min sprints, cumulative gamification, NO streaks), Autism (max 3, 45 min, sensory check, routine anchoring), AuDHD (max 3, 35 min, channel check, ICNU, integrity trigger), Neurotypical (max 3, 40 min, standard)
- [ ] Task persistence, pending tasks from previous sessions
- [ ] Natural language entry

#### Review Module
- [ ] Task completion check (from DailyPlan)
- [ ] Accomplishments, challenges, energy, reflection, forward-look
- [ ] Segment-specific reflection prompts
- [ ] Auto-trigger in evening (not only manual)
- [ ] Scrub completed tasks from todo
- [ ] Natural language entry

#### Capture Module (Basic)
- [ ] Quick capture: classify as task/idea/note/insight/question/goal (Haiku)
- [ ] Fire-and-forget mode: classify → route → one-line confirmation
- [ ] Segment-adaptive (ADHD: minimal friction, Autism: structured, AuDHD: adaptive)
- [ ] Voice input via Groq Whisper
- [ ] Tasks captured → appear in next planning session

#### Future Letter Module
- [ ] Deep dive: setting → life_now → looking_back → challenges → wisdom
- [ ] Feeds into vision anchoring

### 1.3: Daily Workflow Engine

- [ ] Daily Workflow as first-class LangGraph (not assembled from module calls)
- [ ] Morning activation: vision + energy check + yesterday's wins (optional, configurable)
- [ ] **Tiered neurostate pre-flight**: always 1-question energy check; yellow → + sensory; red / 3+ red days → full check; Autism/AuDHD afternoon → sensory accumulation
- [ ] Overload → gentle redirect to recovery (no planning)
- [ ] During day: CheckinScheduler with segment-adaptive timing (ADHD: interval, Autism: exact, AuDHD: semi-predictable)
- [ ] Evening: auto-review trigger (if user doesn't initiate)
- [ ] Reflection: energy + 1-line reflection + tomorrow intention
- [ ] DailyWorkflowHooks: modules inject into daily flow without modifying flow

### 1.4: Basic Inline Coaching

- [x] "I'm stuck" / "I can't start" detected during any module → coaching activates
- [x] No module exit required (coaching within current state)
- [x] ADHD → PINCH activation protocol
- [x] Autism → Inertia protocol (transition bridges, NOT "just start")
- [x] AuDHD → Channel check first, then route to ADHD or Autism protocol
- [x] Burnout gate: if burnout trajectory → recovery, not activation

**Exit Criterion:** A user can complete the full daily cycle (morning vision → plan → reminders → inline coaching → auto-evening review → reflection) without entering a single command. All segment-differentiated. Captures route to planning inbox. Encryption active on all SENSITIVE/ART.9 fields. Consent obtained before any data storage. Input sanitization and rate limiting active. DPIA v1 complete.

---

## Phase 2: Intelligence Layer
**Status:** Not Started
**Duration:** 4-6 weeks
**Dependency:** Phase 1 (daily workflow generating data)
**Databases:** PostgreSQL + Redis (still)
**Value:** The system starts watching, detecting patterns, and tracking energy states.
**Security:** All Phase 2 data models use Phase 1.0 encryption and consent frameworks. New Art. 9 tables (SensoryProfile, MaskingLog, BurnoutAssessment, ChannelState, InertiaEvent) encrypted at field level from creation. Crisis logs stored in BurnoutAssessment + coaching transcripts (Letta), both classified ART. 9 SPECIAL.

Now that users generate daily data, the intelligence has something to work with.

### 2.1: Neurostate Intelligence

- [ ] NeurostateService with 6 sub-services:
  - Sensory State Assessment (Autism/AuDHD: cumulative, no habituation, per-modality)
  - Inertia Detection (3 types: autistic/activation_deficit/double_block)
  - Burnout Type Classifier (ADHD boom-bust / Autism overload→shutdown / AuDHD 3-type)
  - Masking Load Tracker (AuDHD exponential double-masking, per-context)
  - Channel Dominance Detector (AuDHD: ADHD-day vs Autism-day)
  - Energy Prediction (behavioral proxies: latency, message length, vocab, time-of-day)
- [ ] DB models: SensoryProfile, MaskingLog, BurnoutAssessment, ChannelState, InertiaEvent
- [ ] Integration with Daily Workflow pre-flight (tiered, not always full)
- [ ] Integration with ModuleContext (modules receive neurostate)

### 2.2: Pattern Detection Service

- [ ] 5 destructive cycles: Meta-Spirale, Shiny Object, Perfectionism, Isolation, Free Work
- [ ] Service, not agent (consumed by Daily Workflow + Aurora)
- [ ] Segment-differentiated interventions per cycle
- [ ] Real-time detection during active planning
- [ ] 14 additional detection signals from Daily Burden research (masking escalation, sensory overload trajectory, inertia frequency, burnout early warning, etc.)

### 2.3: Energy System

- [ ] IBNS/PINCH for ADHD
- [ ] ICNU for AuDHD (Interest, Challenge, Novelty, Urgency + Integrity Trigger)
- [ ] Spoon-Drawer for AuDHD (6 pools: Social, Sensory, EF, Emotional, Physical, Masking)
- [ ] Simple energy states for ADHD/Neurotypical (RED/YELLOW/GREEN)
- [ ] Sensory + Cognitive for Autism
- [ ] Energy gating: RED blocks non-essential tasks

### 2.4: Revenue Tracker + Tension Engine

- [ ] Revenue tracking via natural language ("I earned 500 from Client X")
- [ ] Tension Engine: Sonne/Erde duality, 4 quadrants (Sweet Spot, Avoidance, Burnout, Crisis)
- [ ] Fulfillment Detector: Genuine / Pseudo / Duty
- [ ] Override hierarchy: Safety > Grounding > Alignment > Optimization

### 2.5: Crisis Safety Net

- [ ] Crisis detection (always running from here on)
- [ ] Hotline integration
- [ ] Mental Health > Security > Everything override
- [ ] Crisis data encryption: all crisis-related logs classified ART. 9 SPECIAL
- [ ] Crisis detection abuse prevention: false-trigger analysis, no rate-limiting on real crises

### 2.6: EffectivenessService

- [ ] Track every intervention delivered (type, id, segment, timestamp)
- [ ] Measure behavioral outcome within 48h window (task completion, latency, session length, pattern recurrence, energy trajectory)
- [ ] Variant comparison (A/B, min 20 samples, segment-specific)
- [ ] Weekly effectiveness report to admin

**Exit Criterion:** All 5 cycles + 14 signals detect correctly. Neurostate pre-flight gates daily workflow. Energy prediction uses behavioral proxies for Autism/AuDHD. Burnout classifier distinguishes 3 types. EffectivenessService tracking all interventions. Crisis net always running. All new Art. 9 tables (SensoryProfile, MaskingLog, BurnoutAssessment, ChannelState, InertiaEvent) encrypted at field level. DPIA updated for Phase 2 data.

---

## Phase 3: Knowledge + Aurora + Depth
**Status:** Not Started
**Duration:** 5-7 weeks
**Dependency:** Phase 2 (meaningful data to store and synthesize)
**Databases:** + Neo4j + Qdrant + Letta
**Value:** The system remembers, connects, synthesizes, and delivers depth modules.

### 3.1: Knowledge Layer

- [ ] Neo4j: Vision → Goal → Task → Habit hierarchy, Belief → BLOCKS → Goal, Pattern relationships, Neurostate trajectories, Aurora narrative ontology
- [ ] Qdrant: captured item embeddings, research embeddings, coaching trace embeddings
- [ ] Letta: 3-tier memory (short-term session / long-term profile / archival history)
- [ ] Neo4j sync from PostgreSQL events

### 3.2: Aurora Agent

- [ ] Foundation: models, LangGraph workflow (Gather → Assess → Synthesize → Recommend → Error)
- [ ] Narrative Engine: StoryArc, Chapter, Daily Note, Milestone Card
- [ ] Growth Tracker: TrajectoryScore (5 dimensions), 3-window comparison (now / 4w / 12w)
- [ ] Milestone Detection (deterministic): pattern broken, belief refuted, goal achieved, habit established (ADHD/AuDHD: 21d, Autism: 14d)
- [ ] Coherence Auditor: Vision-Goal-Habit coherence, contradiction detection, gap/conflict scores
- [ ] Proactive Engine: ReadinessScore-based, max 3/week, boom-bust detection for ADHD
- [ ] DSPy growth signatures (5 segment-specific)
- [ ] Dual-trigger scheduler: cron + Redis events
- [ ] **Autonomy:** proactive impulses from approved types only. New types → proposal to admin.

### 3.3: Coaching Engine (Full)

- [ ] LangGraph: Router → Enrich Context → Knowledge → Coaching → Memory → Summary → END
- [ ] DSPy segment-specific coaching signatures
- [ ] 4-tier fallback: Optimized Artifact → DSPy → PydanticAI → Placeholder
- [ ] Contextual prompt generation (Sonnet)
- [ ] Langfuse tracing

### 3.4: Habit Module (Atomic Habits Framework)

- [ ] State machine: CREATE → IDENTITY → CUE → CRAVING → RESPONSE → REWARD → TRACKING
- [ ] Identity-based framing: "I am someone who meditates" (not "I want to meditate")
- [ ] 2-minute rule: start tiny, scale up (critical for ADHD)
- [ ] Habit stacking: "After I [existing], I will [new]"
- [ ] Daily check-ins via CheckinScheduler (segment-aware timing)
- [ ] Cumulative progress (NOT streak-based for ADHD)
- [ ] Habit-goal linking (CoherenceRatio)
- [ ] Aurora milestone bridge: passive → active tracking
- [ ] Daily workflow hooks: morning reminders, evening check-in
- [ ] Segment-specific: ADHD (novelty rotation, gamification, dopamine pairing), Autism (fixed slots, minimal variation, monotropic focus), AuDHD (channel-aware, spoon-drawer, integrity trigger)

### 3.5: Limiting Beliefs Module

- [ ] Natural language surfacing: "I don't think I'm good enough to charge more"
- [ ] Guided flow: "What belief is holding you back?"
- [ ] Auto-detection from patterns (user avoids same goal repeatedly)
- [ ] Socratic questioning (segment-adapted: ADHD quick aha, Autism logical analysis, AuDHD flexible)
- [ ] Evidence collection: "What supports this?" / "What contradicts it?"
- [ ] ContradictionIndex tracking
- [ ] Planning integration: surface blocking beliefs when goals stall
- [ ] Aurora integration: belief shifts = milestones
- [ ] Neo4j: (:Belief)-[:BLOCKS]->(:Goal)

### 3.6: Landscape of Motifs

- [ ] Motif detection from existing data (Aurora themes + Pattern cycles + Fulfillment states)
- [ ] Types: drive, talent, passion, fear, avoidance, attraction
- [ ] Confidence scoring (how many independent signals)
- [ ] Exploration: "What do I keep coming back to?"
- [ ] "Passion archaeology": what excited you before obligations took over
- [ ] Planning integration: suggest motif-aligned tasks
- [ ] Aurora integration: motifs in growth narrative

### 3.7: Second Brain Upgrade

- [ ] Auto-routing: tasks → planning inbox, goals → goal system, insights → Aurora, ideas → Qdrant
- [ ] Semantic search: "What did I think about X last month?" → Qdrant
- [ ] Natural language retrieval, time-aware search
- [ ] Proactive surfacing before planning: "You had 3 ideas about Project X this week"
- [ ] Knowledge graph integration: captures → Neo4j nodes linked to goals, motifs, patterns

### 3.8: FeedbackService

- [ ] Explicit feedback capture: "That was helpful" / "This doesn't work" / thumbs up/down via Telegram
- [ ] Context storage: which intervention, which module, which segment, timestamp
- [ ] Implicit feedback integration: EffectivenessService outcome signals, PatternDetection recurrence
- [ ] Per-segment aggregation (NEVER across segments): intervention→satisfaction, module→engagement, time-of-day→responsiveness
- [ ] Feed aggregated data into RIA learning cycle (→ SW-20)

### 3.9: RIA Service

- [ ] LangGraph daily cycle: Ingest → Analyze → Propose → Reflect (scheduled, not autonomous)
- [ ] Research ingestion: 152+ findings into Neo4j + Qdrant
- [ ] Pattern analysis: 14 detection signals + neurostate signals
- [ ] Proposal engine: finding → hypothesis → proposal (segment-specific)
- [ ] ADHD contamination warning for Autism findings
- [ ] A/B test lifecycle, feedback → learning pipeline
- [ ] DSPy optimization: BootstrapFewShot (<200 traces), MIPROv2 (>=200)
- [ ] **Every proposal → DM to admin. No deployment without OK.**

**Exit Criterion:** Aurora generates meaningful weekly chapters and proactive impulses. Users can create/track habits, question beliefs, explore motifs -- all via natural language. Captured items auto-route and surface proactively. Semantic search works. RIA proposes segment-specific improvements to admin.

---

## Phase 4: Operations + Hardening
**Status:** Not Started
**Duration:** 3-4 weeks
**Dependency:** Phase 3 (stable system to protect and observe)
**Value:** Production-grade security, quality, and observability.

### 4.1: Avicenna Agent (Quality Observer)

- [ ] Architecture spec in YAML (valid transitions, expected writes, SLAs)
- [ ] `@avicenna_tracked` decorator on all message handlers
- [ ] State machine validation against spec
- [ ] DB write verification (expected writes per transition)
- [ ] Stuck state detection (30 min threshold)
- [ ] Stale interaction detection
- [ ] Rolling issue buffer with severity
- [ ] Health report command
- [ ] Telegram DM to admin (critical/warning, 60s cooldown)
- [ ] **Philosophy:** diagnose, never fix. Human decides.

### 4.2: TRON Agent (Security Automation)

> Note: Security foundations (encryption, consent, input validation, PII hashing) are built in Phase 1.0. TRON automates ongoing security monitoring.

- [ ] Threat monitor, anomaly detector, deterministic scoring
- [ ] 3 modes: Observe (dev) → Suggest+Auto-Low (beta) → Auto-High (production)
- [ ] **Default: Observe. Every action → DM to admin.**
- [ ] Crisis override: Mental Health > Security
- [ ] Vulnerability scanner, compliance auditor
- [ ] LangGraph SecurityScanGraph + IncidentGraph
- [ ] GDPR retention enforcement (automated checks against retention policy from Phase 1.0)
- [ ] Consent audit automation (verify all users have valid consent records)
- [ ] Encryption key rotation scheduler

### 4.3: Money Management Module

- [ ] 7 tables with field-level AES-256-GCM encryption (3-tier envelope)
- [ ] Natural language: "12 euros for sushi" → classify + capture
- [ ] Segment-adaptive: ADHD 3-step, Autism 7-step, AuDHD adaptive, Neurotypical 4-step
- [ ] Anti-Budget: safe_to_spend = income - committed
- [ ] Energy gating: RED blocks non-essential
- [ ] Shame-free language (CI lint gate)
- [ ] Money pattern detector: spending burst (ADHD), routine deviation (Autism), bimodal (AuDHD)
- [ ] DSPy money coaching signatures
- [ ] Privacy: aggregation-only for RIA, no raw amounts in evidence
- [ ] GDPR export/delete for all financial tables

### 4.4: Self-Learning Loops

- [ ] Weekly Self-Doubt Check: "Are my users getting better?" (5 questions, auto-report) (→ SW-7)
- [ ] Proposal flow: RIA → admin DM → approval → DSPy deploy → EffectivenessService verify (→ SW-5, SW-8)
- [ ] Feature flag staged rollout capability (10% → 50% → 100%, admin-controlled)
- [ ] Intervention variant comparison reports

### 4.5: GDPR Full-Stack Aggregation

> Note: Per-module export/delete + encryption + consent built in Phase 1.0. This phase aggregates across all 5 databases (Neo4j + Qdrant + Letta added in Phase 3).

- [ ] GDPR export aggregation across ALL databases: PG + Neo4j subgraph + Qdrant vectors + Redis keys + Letta memories (→ SW-15)
- [ ] GDPR delete cascade across ALL databases (same list)
- [ ] GDPR freeze/unfreeze cascade across ALL databases (Art. 18)
- [ ] Money data: decrypt before export, delete encryption keys after delete
- [ ] Letta memory: decrypt coaching transcripts for export, full purge on delete
- [ ] Qdrant: delete user-scoped embeddings (verify no cross-user leakage)
- [ ] Audit log: record export/delete events without user data
- [ ] Double-confirm UX for account deletion
- [ ] DPIA final update for full 5-database architecture

### 4.6: Production Hardening

- [ ] Docker Compose production config
- [ ] Deployment script with rollback
- [ ] CI/CD: GitHub Actions (test + security + coverage gates)
- [ ] Prometheus + Grafana monitoring
- [ ] Backup strategy (PG, Neo4j, Redis, Qdrant)
- [ ] RBAC on all API endpoints
- [ ] Caddy reverse proxy (HTTPS)
- [ ] Rate limiting, security headers, correlation IDs
- [ ] LLM cost limiter middleware
- [ ] Health checks, log rotation

**Exit Criterion:** Avicenna reports >90% health. TRON scan clean. Money module works with encryption verified. Self-learning loop produces first proposals. System deployed, monitored, backed up. GDPR full-stack export/delete/freeze verified across all 5 databases. DPIA finalized. All Art. 9 data encrypted at rest and in transit.

---

## Phase 5: Scale + Polish
**Status:** Not Started
**Duration:** 4-6 weeks
**Dependency:** Phase 4 (production-stable)
**Value:** International audience, deep onboarding, mobile-ready.

### 5.1: Internationalization + Onboarding

- [ ] Auto-language detection via Telegram locale
- [ ] Full i18n for all modules (en, de, sr, el + extensible)
- [ ] Deep onboarding: Quick Start vs Deep Dive paths
- [ ] Conversational onboarding (no command lists)
- [ ] User-facing segment names translated per language

### 5.2: DSPy Quality Optimization

- [ ] 200+ coaching traces per segment → MIPROv2
- [ ] A/B test optimized vs baseline
- [ ] Tune ReadinessScore weights, calibrate milestone thresholds
- [ ] EffectivenessService-driven optimization targets

### 5.3: CCPA Compliance (if US expansion)

- [ ] CCPA privacy policy section
- [ ] "Do Not Sell" mechanism
- [ ] CCPA-compliant export, 45-day response
- [ ] Request verification system

### 5.4: Mobile App Preparation

- [ ] API layer for mobile client (REST/GraphQL)
- [ ] React Native skeleton
- [ ] Core features ported (all three pillars)
- [ ] Voice input for captures
- [ ] Calendar integration
- [ ] Wearable data as energy signal
- [ ] Motif map visualization (graphical)

**Exit Criterion:** Onboarding in 4+ languages. DSPy optimization measurably improves coaching. API ready for mobile client.

---

## Dependency Graph

```
Phase 0: Research (DONE)
    |
Phase 1: VERTICAL SLICE
    |   1.0: SECURITY FOUNDATION (encryption, consent, DPIA, input validation)
    |   1.1: Segments + NLI + Module System
    |   1.2-1.4: Core Modules + Daily Workflow + Basic Coaching
    |   (PG + Redis only, encrypted from day one)
    |
Phase 2: INTELLIGENCE
    |   Neurostate + Patterns + Energy + Tension
    |   + Crisis (with crisis data encryption)
    |   + EffectivenessService
    |   (still PG + Redis, all Art. 9 tables encrypted)
    |
Phase 3: KNOWLEDGE + AURORA + DEPTH
    |   Neo4j + Qdrant + Letta (encrypted)
    |   Aurora Agent + Full Coaching
    |   Habits + Beliefs + Motifs + Second Brain Upgrade
    |   RIA Service
    |
Phase 4: OPERATIONS + HARDENING
    |   Avicenna + TRON (security automation)
    |   Money Module + GDPR Full-Stack (5-DB aggregation)
    |   Self-Learning Loops + Production Deploy
    |
Phase 5: SCALE + POLISH
        i18n + DSPy Quality + CCPA + Mobile Prep
```

---

## What Carries Over from Ravar V7

### Research (100% reusable):
- 5 general meta-syntheses (56 findings)
- 3 Daily Burden meta-syntheses (96 findings)
- 3 Money meta-syntheses (60 findings)
- 1 cross-synthesis + 1 feature extraction
- Product Bible (8 clusters)
- Interview guide

### Learnings (inform design):
- Segment anti-patterns (15+ documented)
- Neurostate anti-patterns (6 from Daily Burden)
- Architecture anti-patterns (7 documented)
- 4 completed external audits (7.1-8.6/10 scores)
- 1726 test patterns (inform test strategy)

### Code (selective migration):
- DSPy segment signatures (adaptable)
- LangGraph workflow patterns (adaptable)
- Encryption architecture (financial data)
- Ahash personality prompts
- YAML architecture spec (Avicenna)

### NOT carried over:
- Command-driven routing (replaced by NLI)
- 8-agent architecture (replaced by 3 agents + services)
- Module-as-standalone-file pattern (replaced by Module Protocol)
- 5-database-from-day-one (replaced by incremental strategy)
- Scattered `if segment ==` checks (replaced by SegmentContext middleware)

---

## Principles

1. **Every phase delivers value on its own.** No "this becomes useful later."
2. **Natural language first.** If a user needs a command, the NLI failed.
3. **Segment is the product.** Not a feature. The product.
4. **Backend exists != feature exists.** If users can't access it through conversation, it's not done.
5. **System proposes, admin decides.** Autonomous perception, human action.
6. **Ship > Perfect.** But never ship broken segment logic.

---

## System Workflow → Phase Mapping

Every system workflow (defined in ARCHITECTURE.md) maps to the phase where it is first implemented.

| Workflow | Name | Phase | Section |
|----------|------|-------|---------|
| **SW-1** | Daily Cycle | Phase 1 | 1.3 Daily Workflow Engine |
| **SW-2** | Proactive Impulse (Aurora) | Phase 3 | 3.2 Aurora Agent |
| **SW-3** | Inline Coaching Trigger | Phase 1 (basic) → Phase 3 (full) | 1.4 → 3.3 |
| **SW-4** | Pattern Detection → Alert | Phase 2 | 2.2 Pattern Detection |
| **SW-5** | RIA Learning Cycle | Phase 3 | 3.9 RIA Service |
| **SW-6** | Effectiveness Measurement Loop | Phase 2 | 2.6 EffectivenessService |
| **SW-7** | Weekly Self-Doubt Check | Phase 4 | 4.4 Self-Learning Loops |
| **SW-8** | DSPy Prompt Optimization + Deployment | Phase 4 | 4.4 Self-Learning Loops |
| **SW-9** | TRON Incident Response | Phase 4 | 4.2 TRON Agent |
| **SW-10** | Avicenna Quality Alert | Phase 4 | 4.1 Avicenna Agent |
| **SW-11** | Crisis Override | Phase 2 | 2.5 Crisis Safety Net |
| **SW-12** | Burnout Redirect | Phase 2 | 2.1 Neurostate Intelligence |
| **SW-13** | User Onboarding | Phase 1 | 1.1 Bot Scaffold |
| **SW-14** | Vision/Goal Update Cascade | Phase 3 | 3.2 Aurora (Coherence Auditor) |
| **SW-15** | GDPR Export/Delete | Phase 1.0 (encryption + consent + per-module) → Phase 4 (full-stack 5-DB) | 1.0 → 4.5 |
| **SW-16** | Capture → Route → Enrich | Phase 1 (basic) → Phase 3 (enrichment) | 1.2 → 3.7 |
| **SW-17** | Module Lifecycle | Phase 1 | 1.1 Module System |
| **SW-18** | Neurostate Assessment (Tiered) | Phase 1 (basic) → Phase 2 (full) | 1.3 → 2.1 |
| **SW-19** | Channel Dominance Switch | Phase 2 | 2.1 Channel Dominance Detector |
| **SW-20** | Feedback Collection → RIA | Phase 3 | 3.8 FeedbackService |

**Pattern:** Some workflows span multiple phases (marked with →). The first phase delivers the basic version, the later phase adds intelligence/depth.

---

## Open Questions (Ahash Decides)

| Question | Context | When |
|----------|---------|------|
| User interviews timing | Phase 0 interviews paused. Ready when Ahash is. | Whenever |
| Strangler Fig vs Clean Rebuild | Migrate Ravar V7 code selectively, or 100% fresh? | Before Phase 1 starts |
| TRON mode for Phase 1 | Observe only during dev? Or Suggest from start? | Phase 4 |
| Mobile app priority | Phase 5 or separate track? | After Phase 4 |

---

_Aurora Sun V1 Roadmap. Created 2026-02-13._
_Successor to Ravar V7 Roadmap. 5 phases instead of 16. Research carries over._
