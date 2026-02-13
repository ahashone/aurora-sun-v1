# ARCHITECTURE -- Aurora Sun V1

> **Aurora Sun** is an AI coaching system for neurodivergent people.
> It helps users navigate from life vision to daily tasks with drift control,
> habit development, belief work, self-discovery, financial management,
> and a second brain -- all adapted to how their brain actually works.
>
> This document is the single source of truth for the system architecture.
>
> Created: 2026-02-13

---

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [System Overview](#system-overview)
3. [Neurotype Segmentation](#neurotype-segmentation)
4. [Layer 1: Natural Language Interface](#layer-1-natural-language-interface)
5. [Layer 2: Module System](#layer-2-module-system)
6. [Layer 3: Daily Workflow Engine](#layer-3-daily-workflow-engine)
7. [Layer 4: Intelligence Layer](#layer-4-intelligence-layer)
8. [Layer 5: Knowledge Layer](#layer-5-knowledge-layer)
9. [Layer 6: Operations Layer](#layer-6-operations-layer)
10. [Security & Privacy Architecture](#security--privacy-architecture)
11. [Autonomy Model](#autonomy-model)
12. [Self-Learning Architecture](#self-learning-architecture)
13. [System Workflows](#system-workflows) (SW-1 through SW-20)
14. [Data Models](#data-models)
15. [Tech Stack](#tech-stack)
16. [Anti-Patterns](#anti-patterns)

---

## Design Philosophy

### Five Principles

1. **Three Pillars as architecture.** Vision-to-Task, Second Brain, and Money Management are not features -- they are the structural columns everything hangs on.

2. **Natural Language is the OS.** The Intent Router is the entry point for every user interaction. There are no commands, only conversations. Slash commands are syntactic sugar added for power users.

3. **Modules are plugins.** Every module implements the same interface. Adding a new module means implementing the interface and registering intents. The system discovers it.

4. **Segment is middleware, not code.** Neurotype segmentation wraps every interaction as a cross-cutting concern. Individual modules never check `if segment == "AD"` -- they receive a SegmentContext that contains the right config, framing, and constraints.

5. **Databases arrive when needed.** Start with PostgreSQL + Redis. Add Neo4j when there are graph relationships worth querying. Add Qdrant when there are embeddings worth searching. Add Letta when memory across conversations matters.

### Core Values

- **Privacy first, security by default.** Only aggregated data in pattern analysis. GDPR built into every module. All health data encrypted from day one. See [Security & Privacy Architecture](#security--privacy-architecture).
- **Propose, don't execute.** Show the plan, wait for OK. Always.
- **User > Theory.** User data wins against research findings.
- **All evidence is equal.** Anecdotal = Academic.
- **Shame-free language.** Enforced at CI level. In the DNA.
- **Natural language first.** Users talk, system understands.

---

## System Overview

```
+=========================================================================+
|                     NATURAL LANGUAGE INTERFACE                           |
|  Intent Router + Context Manager + Segment Middleware                   |
+===+============================+============================+==========+
    |                            |                            |
    v                            v                            v
+-------------------+  +-------------------+  +-------------------+
| PILLAR 1          |  | PILLAR 2          |  | PILLAR 3          |
| VISION-TO-TASK    |  | SECOND BRAIN      |  | MONEY MANAGEMENT  |
|                   |  |                   |  |                   |
| Daily Workflow    |  | Quick Capture     |  | Financial Capture |
| Planning Module   |  | Auto-Routing      |  | Budget Tracking   |
| Review Module     |  | Semantic Search   |  | Pattern Coaching  |
| Habit Module      |  | Proactive Surface |  | Shame-Free UX     |
| Belief Module     |  | Knowledge Graph   |  |                   |
| Motif Module      |  |                   |  |                   |
+--------+----------+  +--------+----------+  +--------+----------+
         |                       |                       |
+========+=======================+=======================+============+
|                        MODULE SYSTEM                                |
|  Module Interface (Protocol) + Module Registry + Lifecycle Manager  |
+========+========================================================+===+
         |                                                        |
+--------+-------------------+               +--------------------+---+
| INTELLIGENCE LAYER         |               | KNOWLEDGE LAYER        |
|                            |               |                        |
| Aurora (Synthesis Agent)   |  <-------->   | PostgreSQL (Facts)     |
| Coaching Engine            |               | Neo4j (Relationships)  |
| Neurostate Service         |               | Qdrant (Semantics)     |
| Pattern Detection          |               | Redis (Events/Cache)   |
| RIA Service (Learning)     |               | Letta (Memory)         |
| Effectiveness Service      |               |                        |
| Tension + Fulfillment      |               |                        |
+--------+-------------------+               +--------------------+---+
         |                                                        |
+========+========================================================+===+
|                        OPERATIONS LAYER                             |
|  TRON (Security) + Avicenna (Quality) + Observability + GDPR       |
+=====================================================================+
```

### Structural Summary

| Component | Type | Count |
|-----------|------|-------|
| Pillars | Structural columns | 3 |
| Modules | Plugin-based, extensible | 8+ |
| Agents | Autonomous entities | 3 (Aurora, TRON, Avicenna) |
| Services | Called, no own initiative | 6 |
| Databases | Introduced incrementally | 5 (PG + Redis first, rest later) |

---

## Neurotype Segmentation

### The Product IS Segmentation

Aurora Sun delivers fundamentally different experiences per neurotype. This is not a feature -- it is the core product design.

### Segments

| Internal Code | User-Facing Name | Core Experience |
|---------------|-----------------|-----------------|
| `AD` | **ADHD** | Novelty-first, dopamine-optimized, IBNS/PINCH, short sprints, system rotation |
| `AU` | **Autism** | Routine-first, predictability, sensory calm, monotropism, skeleton/muscles |
| `AH` | **AuDHD** | Flexible structure, ICNU-charging, channel dominance, spoon-drawer, integrity trigger |
| `NT` | **Neurotypical** | Standard productivity, goal tracking. Baseline -- neurodivergent segments are overrides |
| `CU` | **Custom** | Individually configurable |

**Critical rule:** Internal codes (`AD`, `AU`, `AH`, `NT`, `CU`) are used in code, databases, and developer documentation. Users NEVER see these codes. Users always see the full names: ADHD, Autism, AuDHD, Neurotypical, Custom.

### SegmentContext (Cross-Cutting Middleware)

SegmentContext is split into 4 sub-objects to avoid a God Object:

```python
@dataclass
class SegmentContext:
    core: SegmentCore
    ux: SegmentUX
    neuro: NeurostateConfig
    features: SegmentFeatures


@dataclass
class SegmentCore:
    code: str                          # AD | AU | AH | NT | CU (internal only)
    display_name: str                  # "ADHD" | "Autism" | "AuDHD" | ... (user-facing)
    max_priorities: int                # 2 (AD) | 3 (AU/AH/NT)
    sprint_minutes: int                # 25 (AD) | 45 (AU) | 35 (AH) | 40 (NT)
    habit_threshold_days: int          # 21 (AD/AH/NT) | 14 (AU)


@dataclass
class SegmentUX:
    energy_check_type: str             # simple | sensory_cognitive | spoon_drawer
    gamification: str                  # cumulative | none | adaptive
    notification_strategy: str         # interval | exact_time | semi_predictable | standard
    framing: SegmentFraming            # Language/tone adapted per segment
    money_steps: int                   # 3 (AD) | 7 (AU) | 5-8 (AH) | 4 (NT)


@dataclass
class NeurostateConfig:
    burnout_model: str                 # boom_bust (AD) | overload_shutdown (AU) | three_type (AH)
    inertia_type: str                  # activation_deficit (AD) | autistic_inertia (AU) | double_block (AH)
    masking_model: str                 # neurotypical (AD) | social (AU) | double_exponential (AH)
    energy_assessment: str             # self_report (AD) | behavioral_proxy (AU) | composite (AH)
    sensory_accumulation: bool         # True for AU/AH -- sensory load does NOT habituate
    interoception_reliability: str     # moderate (AD) | low (AU) | very_low (AH) | high (NT)
    waiting_mode_vulnerability: str    # high (AD) | high (AU) | extreme (AH)


@dataclass
class SegmentFeatures:
    icnu_enabled: bool                 # True for AD/AH only
    spoon_drawer_enabled: bool         # True for AH only
    channel_dominance_enabled: bool    # True for AH only
    integrity_trigger_enabled: bool    # True for AH only
    sensory_check_required: bool       # True for AU/AH
    routine_anchoring: bool            # True for AU
```

Modules access only the sub-object they need. Planning uses `core` + `ux`. NeurostateService uses `neuro`. No module sees everything.

---

## Layer 1: Natural Language Interface

The NLI is the operating system. Every user interaction flows through it.

### Architecture

```
User Message (text or voice)
    |
    v
+-----------------------------------+
| Transcription (if voice)          |
| Groq Whisper -> text              |
+-----------------------------------+
    |
    v
+-----------------------------------+
| Segment Middleware                 |
| Load user profile + segment       |
| Inject SegmentContext              |
+-----------------------------------+
    |
    v
+-----------------------------------+
| State Check                       |
| Is user mid-flow in a module?     |
| YES -> Route to active module     |
| NO  -> Intent Detection           |
+-----------------------------------+
    |
    v (if no active module)
+-----------------------------------+
| Intent Router (LLM-powered)       |
| Regex fast path (~70% of inputs)  |
| Haiku LLM fallback (~30%)         |
|                                   |
| Output: Intent + Confidence       |
| High confidence -> auto-route     |
| Low confidence -> clarify (1 Q)   |
+-----------------------------------+
    |
    v
+-----------------------------------+
| Module Registry                   |
| Intent -> Module mapping          |
| Route to appropriate module       |
+-----------------------------------+
```

### One Bot, Two Modes

There is ONE Telegram bot, not two separate instances. The Intent Router detects whether a message is a quick capture ("12 euros for sushi", "Idea: newsletter for coaches") or a conversation.

Quick captures are classified and routed immediately without pulling the user into a flow. Fire-and-forget: classify → route → one-line confirmation ("Captured: Task 'Newsletter for coaches' → Planning inbox").

### Intent Taxonomy

| Intent Category | Examples | Routed To |
|----------------|----------|-----------|
| `planning.*` | "Let's plan my day", "What should I work on?" | Planning Module |
| `review.*` | "How did my week go?", "Let me reflect" | Review Module |
| `capture.*` | "I just had an idea", "Quick thought" | Capture Module |
| `habit.*` | "I want to build a habit", "Did I meditate?" | Habit Module |
| `belief.*` | "I don't think I can do this" | Belief Module |
| `motif.*` | "What drives me?", "What do I keep coming back to?" | Motif Module |
| `money.*` | "12 euros for sushi", "Check my budget" | Money Module |
| `vision.*` | "What are my goals?", "Show my vision" | Vision Display |
| `coaching.*` | "I'm stuck", "I can't start" | Coaching Engine |
| `aurora.*` | "How am I growing?", "My journey" | Aurora Agent |
| `meta.*` | "Help", "What can you do?" | Help / Onboarding |

### Slash Commands as Aliases

```python
COMMAND_ALIASES = {
    "/plan": "planning.start",
    "/review": "review.start",
    "/capture": "capture.start",
    "/habits": "habit.list",
    "/beliefs": "belief.list",
    "/money": "money.start",
    "/budget": "money.budget",
    "/growth": "aurora.growth",
    "/help": "meta.help",
}
```

Commands are syntactic sugar for intents, not a separate routing path.

---

## Layer 2: Module System

### Module Interface (Protocol)

```python
class Module(Protocol):
    """Every module implements this interface. No exceptions."""

    name: str                              # "planning", "habits", "beliefs", ...
    intents: list[str]                     # Intents this module handles
    pillar: str                            # "vision_to_task" | "second_brain" | "money"

    async def handle(
        self,
        message: str,
        ctx: ModuleContext,                # user, segment, state, session
    ) -> ModuleResponse:                   # text, buttons, next_state, side_effects
        """Handle a user message within this module."""
        ...

    async def on_enter(self, ctx: ModuleContext) -> ModuleResponse:
        """Called when user enters this module."""
        ...

    async def on_exit(self, ctx: ModuleContext) -> None:
        """Called when user leaves this module (cleanup)."""
        ...

    def get_daily_workflow_hooks(self) -> DailyWorkflowHooks:
        """Return hooks for the daily workflow (morning, midday, evening)."""
        ...

    async def export_user_data(self, user_id: int) -> dict:
        """GDPR export for this module's data."""
        ...

    async def delete_user_data(self, user_id: int) -> None:
        """GDPR delete for this module's data."""
        ...
```

### Module Registry

```python
class ModuleRegistry:
    """Discovers and routes to modules. Adding a module = register + done."""

    _modules: dict[str, Module] = {}
    _intent_map: dict[str, Module] = {}

    def register(self, module: Module) -> None:
        self._modules[module.name] = module
        for intent in module.intents:
            self._intent_map[intent] = module

    def route(self, intent: str) -> Module | None:
        return self._intent_map.get(intent)

    def get_daily_hooks(self) -> dict[str, list[DailyWorkflowHook]]:
        """Collect all daily workflow hooks from all modules."""
        ...
```

### Adding a New Module (Example)

```python
class MotifModule:
    name = "motifs"
    intents = ["motif.explore", "motif.list", "motif.discover"]
    pillar = "vision_to_task"

    async def handle(self, message, ctx):
        ...

    async def on_enter(self, ctx):
        return ModuleResponse(text="Let's explore what drives you...")

    def get_daily_workflow_hooks(self):
        return DailyWorkflowHooks(
            morning=None,
            planning_enrichment=self.surface_relevant_motifs,
            evening=None,
        )

# Registration (in app startup)
registry.register(MotifModule())
# Done. Router now handles "motif.*" intents.
```

### Available Modules

| Module | Pillar | State Machine |
|--------|--------|---------------|
| **Planning** | Vision-to-Task | SCOPE -> VISION -> OVERVIEW -> PRIORITIES -> BREAKDOWN -> [SEGMENT_CHECK] -> COMMITMENT -> DONE |
| **Review** | Vision-to-Task | ACCOMPLISHMENTS -> CHALLENGES -> ENERGY -> REFLECTION -> FORWARD -> DONE |
| **Habits** | Vision-to-Task | CREATE -> IDENTITY -> CUE -> CRAVING -> RESPONSE -> REWARD -> TRACKING |
| **Beliefs** | Vision-to-Task | SURFACE -> QUESTION -> EVIDENCE -> REFRAME -> TRACK |
| **Motifs** | Vision-to-Task | EXPLORE -> DISCOVER -> MAP -> CONFIRM |
| **Capture** | Second Brain | CAPTURE -> CLASSIFY -> ROUTE -> DONE (fire-and-forget for quick captures) |
| **Money** | Money | TYPE -> AMOUNT -> CATEGORY -> [AU: NOTE -> ENERGY -> REFLECT] -> DONE |
| **Future Letter** | Vision-to-Task | SETTING -> LIFE_NOW -> LOOKING_BACK -> CHALLENGES -> WISDOM -> DONE |

---

## Layer 3: Daily Workflow Engine

The Daily Workflow is a first-class LangGraph -- not something assembled from calling separate modules. It IS the central user experience.

### Daily Workflow Graph (LangGraph)

```
                    +------------------+
                    | MORNING          |
                    | morning_activate |
                    +--------+---------+
                             |
                    +--------v---------+
                    | NEUROSTATE       |
                    | tiered pre-flight|
                    | (see below)      |
                    +--------+---------+
                             |
                  [overload?]--> GENTLE_REDIRECT
                             |   (recovery protocol,
                             |    no planning today)
                             |
                    +--------v---------+
                    | VISION           |
                    | display vision   |
                    | show 90d goals   |
                    +--------+---------+
                             |
                    +--------v---------+
                    | PLAN             |
                    | -> Planning      |
                    |    Module        |
                    +--------+---------+
                             |
              +--------------+--------------+
              |                             |
    +---------v----------+       +----------v---------+
    | DURING DAY         |       | INLINE COACHING    |
    | auto_reminders     |<----->| triggered by:      |
    | (CheckinScheduler) |       | "I'm stuck"        |
    | segment-adaptive   |       | drift detected     |
    | timing             |       | pattern re-entry   |
    +--------+-----------+       +--------------------+
              |
    +---------v----------+
    | EVENING            |
    | auto_review        |
    | (triggered, not    |
    |  manual)           |
    +--------+-----------+
              |
    +---------v----------+
    | REFLECT            |
    | energy check       |
    | 1-line reflection  |
    | tomorrow intention |
    +--------+-----------+
              |
    +---------v----------+
    | END                |
    | save daily summary |
    | feed Aurora         |
    +--------------------+
```

### Tiered Neurostate Pre-Flight

Not every user gets a full 5-question assessment every morning. The pre-flight is tiered:

| Condition | Assessment Level |
|-----------|-----------------|
| **Always** | 1-question energy check (or behavioral proxy for Autism/AuDHD) |
| **Yellow energy** | + Sensory check + Channel check (AuDHD only) |
| **Red energy OR 3+ Red days** | Full neurostate: sensory + masking + burnout trajectory |
| **Autism/AuDHD + Afternoon** | Sensory accumulation check (no habituation) |

### Module Hooks in Daily Workflow

```python
@dataclass
class DailyWorkflowHooks:
    """How a module participates in the daily workflow."""
    morning: Callable | None               # Called during morning activation
    planning_enrichment: Callable | None   # Called before/during planning
    midday_check: Callable | None          # Called during midday reminder
    evening_review: Callable | None        # Called during auto-review

# Examples:
# Habits module: morning = "habit reminders", evening = "habit check-in"
# Beliefs module: planning_enrichment = "surface blocking beliefs"
# Motifs module: planning_enrichment = "suggest motif-aligned tasks"
# Capture module: planning_enrichment = "surface captured tasks/ideas"
# Money module: evening = "daily spending summary" (if enabled)
```

### Segment-Adaptive Timing

| Event | ADHD | Autism | AuDHD | Neurotypical |
|-------|------|--------|-------|-------------|
| Morning activation | Flexible (8-10) | Exact (9:00) | Semi-predictable | Standard (8:30) |
| Midday check-in | 90 min after last interaction | Exact (13:00) | Channel-dependent | Standard (13:00) |
| Evening review | Flexible (18-21) | Exact (17:00) | Channel-dependent | Standard (18:00) |
| Reminder frequency | Interval-based | Minimal | Semi-predictable | Moderate |

### Inline Coaching (Segment-Specific)

When "I'm stuck" / "I can't start" is detected during any module:

| Segment | Protocol | Key Insight |
|---------|----------|-------------|
| **ADHD** | PINCH (Passion, Interest, Novelty, Competition, Hurry) + activation deficit protocol | Needs dopamine hook to start |
| **Autism** | Inertia protocol: transition bridges, NOT "just start" | Inertia != laziness != activation deficit |
| **AuDHD** | Channel dominance check FIRST, then route to ADHD or Autism protocol | Wrong-channel intervention backfires |
| **Neurotypical** | Standard motivation coaching | Goal-focused |

**Burnout gate:** If burnout trajectory detected, coaching shifts from activation to recovery. Behavioral Activation during Autistic Burnout actively harms.

---

## Layer 4: Intelligence Layer

### 3 Agents

| Agent | Type | Purpose | Autonomy |
|-------|------|---------|----------|
| **Aurora** | Active, user-facing | Coach, mentor, synthesis, growth narratives, proactive impulses | Proactive impulses to users (from approved types). New types require admin approval. |
| **TRON** | Active, system-facing | Security scanning, threat detection, incident response | Observe + suggest. All actions require admin approval. |
| **Avicenna** | Passive, dev-facing | Quality observer, spec compliance, Soll/Ist comparison | Always observing. DM to admin on critical issues. Never intervenes. |

### Aurora Agent (Central Intelligence)

```
Aurora Agent
    |
    +-- Narrative Engine
    |   (StoryArc, Chapter, Daily Note, Milestone Card)
    |   This is what users SEE.
    |
    +-- Growth Tracker
    |   (TrajectoryScore, Milestones, Habit Stability)
    |   This is what the system MEASURES.
    |
    +-- Coherence Auditor
    |   (Vision-Goal-Habit alignment, Belief-Goal conflicts)
    |   This CONNECTS everything.
    |
    +-- Proactive Engine
        (ReadinessScore, max 3/week, boom-bust detection)
        This INITIATES when the user doesn't.
```

### TRON Agent (Security)

3 configurable modes:

| Mode | Behavior | Recommended For |
|------|----------|-----------------|
| **Observe** | Scan, detect, log. No action. DM to admin with recommendation. | Development phase |
| **Suggest + Auto-Low** | Auto-act on low-risk (rate limiting). DM for medium+. | Beta phase |
| **Auto-High** | Auto-act all levels. DM on HIGH+. Admin can override. | Production with many users |

**Absolute override:** Mental Health Crisis > Security. A user in crisis is never locked out by security actions.

### Avicenna Agent (Quality Observer)

- `@avicenna_tracked` decorator on all message handlers
- Architecture spec in YAML (valid transitions, expected writes, SLAs)
- Rolling issue buffer with severity classification
- Stuck state detection (30 min threshold)
- Stale interaction detection
- Telegram DM to admin for critical/warning issues (60s cooldown)
- **Philosophy:** Diagnose, never fix. Human decides.

### 6 Services

| Service | Purpose | Consumed By |
|---------|---------|-------------|
| **RIA Service** | Scheduled learning loop: Ingest -> Analyze -> Propose -> Reflect | Aurora, Coaching Engine |
| **PatternDetectionService** | Detects 5 destructive cycles + 14 neurostate signals | Daily Workflow, Aurora, Coaching |
| **NeurostateService** | Composite assessment: sensory + masking + inertia + burnout + energy prediction | Daily Workflow, Modules, Coaching |
| **EffectivenessService** | Measures whether interventions actually worked (behavioral signals) | RIA, Aurora, DSPy |
| **CoachingEngine** | LangGraph workflow for coaching interactions | All modules (inline coaching) |
| **FeedbackService** | Aggregates user feedback | Aurora, RIA |

### NeurostateService (6 Sub-Services)

| Sub-Service | What | Key Research Insight |
|-------------|------|---------------------|
| **Sensory State Assessment** | Pre-task sensory check for Autism/AuDHD | Sensory load accumulates, does NOT habituate. Morning fine != afternoon fine. |
| **Inertia Detection** | Detect autistic inertia (Autism) vs activation deficit (ADHD) vs double-block (AuDHD) | Wrong intervention worsens it. Autism needs bridges, ADHD needs dopamine, AuDHD needs channel ID first. |
| **Burnout Type Classifier** | Identify which burnout is emerging | ADHD: boom-bust. Autism: overload->shutdown (skill regression, not failure). AuDHD: 3 distinct types. |
| **Masking Load Tracker** | Track cumulative masking cost | AuDHD masking is exponential (double-masking). Masking drains executive function pool. |
| **Channel Dominance Detector** | AuDHD: which channel dominates today? | ADHD-day vs Autism-day. Wrong-channel interventions fail or backfire. |
| **Energy Prediction** | Behavioral signals instead of self-report | Autism/AuDHD interoception is unreliable. Use response latency, message length, vocabulary complexity, time-of-day patterns. |

### Coaching Engine (LangGraph)

```
Router -> Enrich Context -> Coaching -> Memory -> Summary -> END
              |                 |
              v                 v
        Knowledge Node    DSPy Signatures
        (Neo4j + Qdrant)  (5 segment-specific)
```

**4-tier response fallback:** Optimized Artifact -> DSPy -> PydanticAI -> Placeholder

### Tension Engine + Fulfillment (Services)

```python
# Tension Engine
QUADRANTS = {
    (HIGH, HIGH): "SWEET_SPOT",      # Reinforce
    (HIGH, LOW):  "AVOIDANCE",       # Cycle Breaker
    (LOW, HIGH):  "BURNOUT",         # Sonne intervention
    (LOW, LOW):   "CRISIS",          # Safety first
}

OVERRIDE_HIERARCHY = [
    "SAFETY",       # Crisis, burnout, health -> overrides everything
    "GROUNDING",    # Must act, not just think -> overrides Sonne
    "ALIGNMENT",    # Fulfillment -> overrides optimization
    "OPTIMIZATION", # Efficiency -> lowest priority
]

# Fulfillment Detector
# GENUINE: activity + energy rises + results emerge
# PSEUDO: activity + energy rises + NO results (flow as avoidance)
# DUTY: results + no energy (burnout path)
```

---

## Layer 5: Knowledge Layer

### Incremental Database Strategy

| Build Phase | Databases | Why |
|-------------|-----------|-----|
| Phase 1-2 | **PostgreSQL + Redis** | Users, sessions, tasks, events. Sufficient for daily modules. |
| Phase 3 | + **Neo4j** | Growth narratives and pattern relationships worth querying. |
| Phase 3 | + **Qdrant** | Research embeddings + captured items for semantic search. |
| Phase 3 | + **Letta** | Long-term memory for coaching continuity. |

### PostgreSQL Data Model

See [Data Models](#data-models) section below.

### Neo4j Knowledge Graph

```
# Core hierarchy (Vision -> Goal -> Task -> Habit)
(:User)-[:HAS_VISION]->(:Vision {type: life|10y|3y})
(:Vision)-[:LEADS_TO]->(:Goal {type: 90d|weekly|daily})
(:Goal)-[:HAS_TASK]->(:Task)
(:Goal)-[:HAS_HABIT]->(:Habit)

# Beliefs block goals
(:Belief)-[:BLOCKS]->(:Goal)
(:BeliefEvidence)-[:SUPPORTS|:REFUTES]->(:Belief)

# Motifs emerge from patterns
(:Motif)-[:DRIVES]->(:Goal)
(:Motif)-[:EXPRESSED_IN]->(:Pattern)
(:FulfillmentState)-[:REVEALS]->(:Motif)

# Captured items link to everything
(:CapturedItem)-[:BECAME]->(:Task|:Goal|:Insight)
(:CapturedItem)-[:RELATED_TO]->(:Goal|:Motif)

# Aurora narratives
(:StoryArc)-[:HAS_CHAPTER]->(:Chapter)
(:Chapter)-[:HIGHLIGHTS]->(:TurningPoint|:MicroWin|:Setback)
(:Motif)-[:THEMES_IN]->(:StoryArc)

# Neurostate trajectories
(:User)-[:HAS_SENSORY_PROFILE]->(:SensoryProfile)
(:User)-[:HAS_MASKING_PATTERN]->(:MaskingPattern)
(:User)-[:HAS_BURNOUT_TRAJECTORY]->(:BurnoutTrajectory)
(:BurnoutTrajectory)-[:TRIGGERED_BY]->(:Pattern)
(:MaskingPattern)-[:DRAINS]->(:EnergyPool)

# Research (RIA)
(:Finding)-[:APPLIES_TO]->(:Segment)
(:Finding)-[:SUPPORTS]->(:Hypothesis)
(:Hypothesis)-[:GENERATES]->(:Proposal)
```

### Qdrant Collections

```
captured_items   - User captures with embeddings (for semantic search)
research         - Research documents + findings (for RIA)
coaching_traces  - Coaching interactions (for DSPy optimization)
```

### Redis

```
Events:     user:{id}:events, daily_workflow:{id}:state
Cache:      user:{id}:segment_context, module:{id}:state
Pub/Sub:    goal:achieved, vision:updated, pattern:broken, habit:completed
```

---

## Layer 6: Operations Layer

### Observability

Avicenna provides observability as a dedicated agent, not just a decorator:

- Architecture spec in YAML: valid state transitions, expected DB writes, SLAs
- State machine validation against spec at every transition
- Stuck state + stale interaction detection
- Health report command
- Telegram DM for critical issues to admin
- Rolling issue buffer with severity classification

### Crisis Safety Net (Always Running)

```
OVERRIDE HIERARCHY:
1. SAFETY (crisis, burnout, health) -> overrides EVERYTHING
2. GROUNDING (must act, not just think) -> overrides Sonne
3. ALIGNMENT (fulfillment, purpose) -> overrides optimization
4. OPTIMIZATION (efficiency) -> lowest priority
```

---

## Security & Privacy Architecture

### Principle: Security by Default

Security is not a phase. It is a property of every line of code, every data model, every deployment. No data is stored without classification. No Art. 9 field is stored without encryption. No phase ships without security review.

### Data Classification Matrix

Every table and field is classified at design time. Classification determines encryption, retention, and access requirements.

| Classification | Definition | Encryption Required | Example |
|---------------|-----------|-------------------|---------|
| **PUBLIC** | No user data, no business logic | No | Feature flags, app config |
| **INTERNAL** | System data, non-user-identifiable | No | InterventionTrace (anonymized), BudgetCategory (meta) |
| **SENSITIVE** | User-identifiable, personal | Yes (AES-256-GCM) | User (name, telegram_id), CapturedItem, Task, Goal |
| **ART. 9 SPECIAL** | Health data, mental state, neurotype | Yes (AES-256-GCM + field-level) | Belief, SensoryProfile, MaskingLog, BurnoutAssessment, ChannelState, InertiaEvent, coaching transcripts (Letta) |
| **FINANCIAL** | Money, transactions, budgets | Yes (AES-256-GCM, 3-tier envelope) | Transaction, BudgetState |

### Table-Level Classification

| Table | Classification | Encrypted Fields | Justification |
|-------|---------------|-----------------|---------------|
| User | SENSITIVE | `name`, `telegram_id` (HMAC-SHA256 hashed) | PII identifier |
| Vision | SENSITIVE | `content` | Personal goals |
| Goal | SENSITIVE | `title`, `key_results` | Personal goals |
| Task | SENSITIVE | `title` | Personal tasks |
| DailyPlan | ART. 9 SPECIAL | `reflection_text`, `morning_energy`, `evening_energy` | Mental state indicators |
| Habit | ART. 9 SPECIAL | `identity_statement`, `cue`, `craving`, `response`, `reward` | Identity + behavioral health |
| Belief | ART. 9 SPECIAL | `text` | Mental health: core beliefs |
| Motif | SENSITIVE | `label`, `signals` | Psychological patterns |
| CapturedItem | SENSITIVE | `content` | May contain anything |
| SensoryProfile | ART. 9 SPECIAL | `baseline_thresholds`, `current_load`, `recovery_activities` | Neurotype health data |
| MaskingLog | ART. 9 SPECIAL | `masking_type`, `context`, `estimated_cost` | Mental health: masking burden |
| BurnoutAssessment | ART. 9 SPECIAL | `burnout_type`, `severity`, `indicators` | Mental health: burnout state |
| ChannelState | ART. 9 SPECIAL | `dominant_channel`, `signals` | Neurotype state |
| InertiaEvent | ART. 9 SPECIAL | `inertia_type`, `trigger`, `resolved_via` | Neurotype behavioral data |
| Transaction | FINANCIAL | `amount_encrypted`, `description_encrypted` | Financial data (3-tier envelope) |
| BudgetCategory | INTERNAL | -- | Non-sensitive metadata |
| BudgetState | FINANCIAL | `safe_to_spend`, `total_committed` | Financial data |
| InterventionTrace | INTERNAL | -- | Anonymized system data |

### Encryption Architecture

```
                    ENCRYPTION LAYERS

Layer 1: Transport (HTTPS via Caddy, Tailscale for SSH)
    |
Layer 2: Storage (PostgreSQL, disk-level encryption)
    |
Layer 3: Field-Level (application-level, per-classification)
    |
    +-- SENSITIVE fields: AES-256-GCM, per-user encryption key
    +-- ART. 9 fields: AES-256-GCM, per-user key + field-level salt
    +-- FINANCIAL fields: AES-256-GCM, 3-tier envelope (master → user → field)
    |
Layer 4: Cross-Database
    +-- Neo4j: node properties encrypted for SENSITIVE/ART.9 data
    +-- Qdrant: embeddings are derived data (not directly reversible, but user-scoped)
    +-- Redis: session data TTL-bound, no persistent SENSITIVE storage
    +-- Letta: memory entries encrypted (coaching transcripts = ART. 9)
```

**Encryption Library:** `src/lib/encryption.py` -- built in Phase 1.0, used by everything from first schema onward.

```python
class EncryptionService:
    """Handles all field-level encryption. Used by every model with SENSITIVE or higher classification."""

    def encrypt_field(self, plaintext: str, user_id: int, classification: DataClassification) -> EncryptedField: ...
    def decrypt_field(self, encrypted: EncryptedField, user_id: int) -> str: ...
    def rotate_key(self, user_id: int) -> None: ...
    def destroy_keys(self, user_id: int) -> None: ...  # For GDPR delete
```

### GDPR Compliance

#### Legal Basis

Processing of Art. 9 health data requires **explicit consent** (GDPR Art. 9(2)(a)). Not implied, not buried in ToS.

#### Consent Architecture

```
USER OPENS BOT (first time)
    |
    v
ONBOARDING FLOW (Phase 1.1)
    |
    v
STEP 1: Language selection
STEP 2: Name
STEP 3: Working style inference
STEP 4: CONSENT GATE  <-- NEW, MANDATORY
    |
    +-- Display: What data we collect (plain language, translated)
    +-- Display: Why (coaching requires understanding your patterns)
    +-- Display: What we do NOT do (sell, share, aggregate across users)
    +-- Display: Your rights (export, delete, withdraw consent at any time)
    +-- Require: Explicit "I agree" (not pre-checked, not skippable)
    +-- Store: consent_given_at, consent_version, consent_language
    |
    v
STEP 5: Confirmation → Bot active

CONSENT WITHDRAWAL:
    User says "delete my data" or "I withdraw consent" at any time
    → SW-15 (GDPR Export/Delete) triggers
    → All data deleted across all 5 databases
    → Encryption keys destroyed
    → Confirmation sent
```

#### Consent Record

```
ConsentRecord
+-- id, user_id
+-- consent_version: str (e.g. "1.0")
+-- consent_language: str
+-- consent_given_at: datetime
+-- consent_withdrawn_at: datetime | null
+-- ip_hash: str (HMAC, not raw IP)
+-- consent_text_hash: str (to prove which version was accepted)
```

#### Data Subject Rights (GDPR Art. 15-22)

| Right | Implementation | Workflow |
|-------|---------------|----------|
| **Access** (Art. 15) | `export_user_data()` across all modules | SW-15 |
| **Rectification** (Art. 16) | User can update any personal data via conversation | Module state machines |
| **Erasure** (Art. 17) | `delete_user_data()` cascade across 5 DBs + key destruction | SW-15 |
| **Restriction** (Art. 18) | Freeze processing without deletion (consent withdrawn but data retained for legal obligation) | NEW: `freeze_user_data()` in Module Protocol |
| **Portability** (Art. 20) | Export in machine-readable format (JSON) | SW-15 |
| **Objection** (Art. 21) | User can object to specific processing (e.g. proactive impulses) | Feature flags per user |

#### Module Protocol (Extended)

```python
class Module(Protocol):
    async def export_user_data(self, user_id: int) -> dict: ...
    async def delete_user_data(self, user_id: int) -> None: ...
    async def freeze_user_data(self, user_id: int) -> None: ...   # Art. 18: restriction
    async def unfreeze_user_data(self, user_id: int) -> None: ...
```

#### Retention Policy

| Data Category | Retention | After Retention |
|--------------|-----------|----------------|
| Active user data | While account active | -- |
| Deleted user data | 0 days (immediate cascade delete) | Keys destroyed |
| Consent records | 5 years after withdrawal (legal obligation) | Anonymized |
| Anonymized analytics | Indefinite | Already anonymized |
| Backup data | 30 days rolling | Auto-purged |
| Intervention traces (anonymized) | Indefinite | No PII |

### Sub-Processor Registry

Every third party that processes user data must be documented.

| Sub-Processor | Purpose | Data Sent | Classification | DPA Required |
|--------------|---------|-----------|---------------|-------------|
| **Anthropic** (Claude Sonnet/Haiku) | Coaching, intent routing, coaching prompts | User messages (transient, not stored by provider) | SENSITIVE + ART. 9 | Yes |
| **OpenAI** (fallback) | Fallback LLM | User messages (transient) | SENSITIVE + ART. 9 | Yes |
| **Groq** (Whisper) | Voice transcription | Audio (transient) | SENSITIVE | Yes |
| **Telegram** | User interface, message delivery | Messages, user ID | SENSITIVE | Platform ToS |
| **Hetzner** | Infrastructure hosting | All data (encrypted at rest) | All | Yes |
| **Langfuse** | LLM tracing | Prompt/response pairs | SENSITIVE (must be anonymized) | Yes |

**Rule:** Before adding ANY new sub-processor, document it here and get Ahash's approval.

### Breach Notification Procedure

```
BREACH DETECTED (by TRON, Avicenna, or external report)
    |
    v
1. CONTAIN (0-1h)
   - Isolate affected systems
   - Revoke compromised credentials
   - TRON: auto-block if in Auto-High mode
    |
    v
2. ASSESS (1-24h)
   - What data was accessed?
   - How many users affected?
   - What classification level?
   - Was data encrypted? (if yes: lower risk)
    |
    v
3. NOTIFY (within 72h of awareness -- GDPR Art. 33)
   - IF Art. 9 data involved OR high risk to individuals:
     - Supervisory authority: within 72h
     - Affected users: "without undue delay" (Art. 34)
   - IF encrypted and keys not compromised:
     - Authority notification still required
     - User notification may not be required (Art. 34(3)(a))
    |
    v
4. REMEDIATE
   - Fix root cause
   - Key rotation for affected users
   - Updated security measures
   - Post-incident report → docs/archive/
```

### DPIA (Data Protection Impact Assessment)

A DPIA is **mandatory** under GDPR Art. 35 because Aurora Sun:
- Processes Art. 9 health data (mental health, neurotype)
- Profiles individuals systematically (pattern detection, behavioral analysis)
- Uses automated decision-making (coaching interventions based on behavioral data)

**DPIA deliverable:** `docs/DPIA.md` -- created in Phase 1.0, updated at every phase transition.

**DPIA must cover:**
1. Description of processing operations and purposes
2. Assessment of necessity and proportionality
3. Assessment of risks to data subjects
4. Measures to address risks (encryption, consent, access controls)

### Input Validation & Rate Limiting

Built from Phase 1, not Phase 4:

- **Input sanitization:** All user input sanitized before processing (XSS, injection, path traversal)
- **Rate limiting:** Per-user rate limits on all endpoints (prevents abuse AND protects LLM costs)
- **Message size limits:** Max message length enforced at NLI layer
- **File upload limits:** Voice messages capped at 60s / 10MB

### Access Control

| Role | Access | Defined In |
|------|--------|-----------|
| **User** | Own data only, via Telegram bot | Telegram auth (user_id) |
| **Admin (Ahash)** | All data, TRON commands, deployment | Telegram admin auth + Tailscale SSH |
| **System (Aurora/RIA/Avicenna)** | User data within scope of function | Service-level scoping |
| **Sub-Processors** | Transient access during API calls | DPA agreements |

**Rule:** No database has a public-facing port. All access through application layer or Tailscale SSH.

---

## Autonomy Model

### The Principle

**The system learns autonomously. It never acts autonomously. It always proposes.**

### What the System Does WITHOUT Admin Approval

Exactly 3 things:

1. **Observe** -- Avicenna tracks every interaction, EffectivenessService measures outcomes, PatternDetection recognizes cycles. This is perception, not action.

2. **Think** -- RIA analyzes patterns, generates hypotheses, compares intervention effectiveness. The weekly Self-Doubt Check runs automatically. This produces insights, not changes.

3. **Propose** -- Everything from Observe + Think becomes a Proposal sent to admin via Telegram DM. With data, reasoning, expected impact.

### What Requires Admin Approval

Everything that changes the system's behavior:

| Change Type | Approval Required | How |
|-------------|-------------------|-----|
| Prompt changes | Yes | RIA proposes, admin approves, DSPy deploys |
| New intervention types | Yes | RIA proposes with evidence |
| New pattern detectors | Yes | System proposes with detection logic |
| Architecture changes | Yes | Admin decides completely |
| New modules | Yes | Admin decides completely |
| Segment logic changes | Yes | Admin decides completely |
| Feature flag changes | Yes | System proposes, admin flips |

### Exception: Aurora's Proactive Impulses

Aurora sends proactive coaching impulses to users (max 3/week). This MUST be autonomous -- users can't wait for admin to wake up.

**Constraint:** Aurora only selects from admin-approved intervention types. New types require approval first.

### Autonomy Matrix

| Component | Observe | Think | Propose | Act |
|-----------|---------|-------|---------|-----|
| **Avicenna** | Autonomous | -- | DM on critical | Never |
| **EffectivenessService** | Autonomous | Autonomous | Weekly report | Never |
| **RIA** | -- | Autonomous | Every proposal -> DM | Never without OK |
| **DSPy** | -- | -- | Prompt changes -> DM | Only after OK |
| **Aurora** | -- | Autonomous | New types -> DM | Approved types only |
| **TRON** | Autonomous | Autonomous | Every action -> DM | Never without OK (default) |
| **PatternDetection** | Autonomous | -- | New patterns -> DM | Never |

---

## Self-Learning Architecture

### 4 Feedback Loops

```
Loop 1: PERCEIVE (Avicenna + EffectivenessService)
   Every interaction observed. Every intervention measured.
   -> "Something is happening"

Loop 2: UNDERSTAND (RIA + PatternDetection)
   Patterns analyzed. Effectiveness compared.
   -> "This is the problem / opportunity"

Loop 3: PROPOSE (RIA -> Admin)
   Proposal generated with evidence + expected impact.
   -> "This could be the solution. May I?"

Loop 4: VERIFY (EffectivenessService, post-change)
   After admin approves and change is deployed:
   Did it actually work? Behavioral measurement.
   -> "It worked / It didn't. Here's the data."
   -> Feeds back into Loop 1.
```

### Weekly Self-Doubt Check

The system asks itself: "Are my users actually getting better?"

```
Question 1: Are users completing more tasks than 4 weeks ago?
Question 2: Are users staying closer to their vision?
Question 3: Are users breaking out of destructive cycles more often?
Question 4: Is habit completion rate rising?
Question 5: Is pattern recurrence rate falling?
```

If 3+ questions answer "No" -> Self-Doubt Report to admin:
"My interventions aren't working. Here's the data. Here are possible causes. Here are proposals."

### EffectivenessService

```python
class EffectivenessService:
    """Measures whether interventions actually worked.
    Closes the learning loop."""

    async def track_intervention(
        self,
        user_id: int,
        intervention_type: str,    # "coaching_prompt", "habit_reminder", etc.
        intervention_id: str,
        segment: str
    ) -> None:
        """Register: Intervention X was delivered."""

    async def measure_outcome(
        self,
        user_id: int,
        intervention_id: str,
        window_hours: int = 48
    ) -> InterventionOutcome:
        """Measure: What did the user do AFTER the intervention?

        Behavioral signals (not self-report):
        - Task completion rate (before vs after)
        - Response latency (faster = more engaged)
        - Session length
        - Pattern recurrence
        - Energy trajectory
        """

    async def compare_variants(
        self,
        intervention_a: str,
        intervention_b: str,
        segment: str,
        min_samples: int = 20
    ) -> VariantComparison:
        """Compare: Which intervention works better?
        Segment-specific -- never aggregate across segments."""
```

### How a Proposal Flows

```
SYSTEM OBSERVES
    |
    v
Avicenna: logs interactions
EffectivenessService: measures outcomes
    |
    v
RIA: analyzes patterns + effectiveness data
RIA: generates proposal
    |
    v
TELEGRAM DM TO ADMIN:
"ADHD users ignore the morning impulse in 73% of cases (N=34).
When I ask 'What's the ONE task that changes everything today?'
instead of 'What do you want to achieve?', response rate for
similar prompts rises to 61%. Shall I switch?"
    |
    v
ADMIN: "Yes" / "No" / "Modify"
    |
    v
DSPy: optimizes prompt, deploys new version
Feature flag: 10% of users first (if admin approves staged rollout)
    |
    v
EffectivenessService: measures new version
After 20+ samples: report to admin
    |
    v
LOOP CLOSED
```

---

## Data Models

### PostgreSQL

```
User
+-- id, telegram_id, name, language, timezone
+-- working_style_code: AD | AU | AH | NT | CU  (internal)
+-- encryption_salt, letta_agent_id

Vision
+-- id, user_id, type: life | 10y | 3y
+-- content, created_at, updated_at

Goal
+-- id, user_id, vision_id (FK)
+-- type: 90d | weekly | daily
+-- title, key_results, status

Task
+-- id, user_id, goal_id (FK)
+-- title, status, priority, committed_date

DailyPlan
+-- id, user_id, date
+-- vision_displayed, goals_reviewed
+-- priorities_selected, tasks_committed
+-- morning_energy, evening_energy
+-- auto_review_triggered, reflection_text

Habit
+-- id, user_id, title
+-- identity_statement ("I am someone who...")
+-- cue, craving, response, reward
+-- stack_after (habit stacking)
+-- frequency, total_completions
+-- goal_id (FK -> Goal)

Belief
+-- id, user_id, text
+-- category: self_worth | capability | permission | safety | belonging
+-- status: surfaced | questioned | evidence_collecting | reframing | shifted | released
+-- contradiction_index
+-- blocked_goal_id (FK -> Goal)

Motif
+-- id, user_id, label
+-- motif_type: drive | talent | passion | fear | avoidance | attraction
+-- confidence_score
+-- signals: JSON
+-- confirmed_by_user: bool

CapturedItem
+-- id, user_id, content, classification
+-- routed_to: task | goal | insight | idea | none
+-- routed_id: FK (to Task or Goal)
+-- embedding_id: FK (to Qdrant vector)

SensoryProfile
+-- id, user_id
+-- baseline_thresholds: JSON (per modality)
+-- current_load: float (0.0-1.0, cumulative)
+-- last_assessment_at, recovery_activities: JSON

MaskingLog
+-- id, user_id, timestamp
+-- masking_type: social | neurotypical | double
+-- context: work | social | public | digital
+-- duration_minutes, estimated_cost: float

BurnoutAssessment
+-- id, user_id, assessed_at
+-- burnout_type: boom_bust | overload_shutdown | adhd_type | autistic_type | combined_type
+-- severity: float (0.0-1.0)
+-- skill_regression_detected: bool
+-- indicators: JSON

ChannelState (AuDHD only)
+-- id, user_id, date
+-- dominant_channel: adhd | autism | balanced | rapid_switching
+-- confidence: float
+-- signals: JSON

InertiaEvent
+-- id, user_id, timestamp
+-- inertia_type: autistic | activation_deficit | double_block
+-- trigger: task_transition | initiation | overwhelm | demand_avoidance
+-- resolved_via: transition_bridge | dopamine_hook | channel_switch | rest | external_aid

-- Money Management (encrypted)
Transaction
+-- id, user_id, amount_encrypted, category_id, description_encrypted
+-- timestamp, currency

BudgetCategory
+-- id, user_id, name, monthly_limit, category_type

BudgetState
+-- id, user_id, month, safe_to_spend, total_committed

InterventionTrace
+-- id, user_id, intervention_type, intervention_id
+-- delivered_at, segment
+-- outcome_measured: bool
+-- outcome_data: JSON (task completion, latency, etc.)
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **LLM Orchestration** | LangGraph | Stateful workflows (Daily Workflow, Coaching, RIA, Security) |
| **Prompt Engineering** | DSPy | Self-optimizing prompts, segment-specific signatures |
| **Type Safety** | PydanticAI | Structured LLM responses |
| **LLM Providers** | Anthropic (Sonnet/Haiku), OpenAI (fallback) | Primary intelligence |
| **Voice** | Groq Whisper | Speech-to-text for captures |
| **Bot** | python-telegram-bot | User interface |
| **Relational DB** | PostgreSQL | Core data, encrypted financial data |
| **Graph DB** | Neo4j | Relationships, narratives, patterns |
| **Vector DB** | Qdrant | Semantic search, embeddings |
| **Cache/Events** | Redis | Session cache, event bus, pub/sub |
| **Memory** | Letta/MemGPT | Long-term conversational memory |
| **Tracing** | Langfuse | LLM interaction tracing |
| **Monitoring** | Prometheus + Grafana | System metrics |
| **Security** | fail2ban, Tailscale, Caddy (HTTPS) | Infrastructure security |
| **Deployment** | Docker Compose | Container orchestration |
| **CI/CD** | GitHub Actions | Test + security + coverage gates |
| **Encryption** | AES-256-GCM | All SENSITIVE/ART.9/FINANCIAL fields (see Security & Privacy Architecture) |

---

## System Workflows

Internal workflows that define how agents, services, and modules interact at runtime.
Each workflow is a step-by-step sequence with trigger, participants, and outcome.

Module-internal state machines (Planning, Habits, Beliefs, etc.) are defined in [Layer 2: Module System](#layer-2-module-system) and are NOT repeated here. System Workflows cover cross-cutting flows only.

---

### SW-1: Daily Cycle

**Trigger:** Scheduled (segment-adaptive morning time)
**Participants:** Daily Workflow Engine, NeurostateService, Planning Module, Review Module, Aurora, all modules (via hooks)

```
1. CheckinScheduler fires at segment-adaptive time
2. Morning activation message → user
3. NeurostateService: tiered pre-flight (→ SW-18)
4. IF overload detected → SW-12 (Burnout Redirect), STOP
5. Vision display (90d goals, life vision)
6. Planning Module: invoke (→ module state machine)
7. Collect morning hooks from all registered modules
   (habits: reminders, beliefs: blocking beliefs, motifs: alignment, capture: inbox items)
8. During day: CheckinScheduler fires midday reminder (segment-adaptive)
9. IF "I'm stuck" detected at any point → SW-3 (Inline Coaching)
10. Evening: auto-trigger Review Module (→ module state machine)
11. Reflect: energy check + 1-line reflection + tomorrow intention
12. Save DailyPlan record
13. Feed daily summary to Aurora (narrative update)
14. EffectivenessService: register all interventions delivered today
```

---

### SW-2: Proactive Impulse (Aurora)

**Trigger:** Aurora's Proactive Engine (ReadinessScore threshold met)
**Participants:** Aurora, EffectivenessService, PatternDetection

```
1. Aurora evaluates ReadinessScore (time since last contact, energy trajectory, pattern state)
2. Check: max 3 impulses/week not exceeded
3. Check: no active burnout trajectory (PatternDetection)
4. Check: intervention type is admin-approved
5. Select impulse type based on segment + current state:
   - ADHD: novelty hook, curiosity spark, micro-challenge
   - Autism: routine reinforcement, predictable check-in, progress reflection
   - AuDHD: channel-appropriate (detect dominant channel first → SW-19)
6. Deliver impulse via Telegram
7. EffectivenessService.track_intervention(type="proactive_impulse", ...)
8. After 48h window: EffectivenessService.measure_outcome()
9. IF new impulse type needed → generate Proposal → admin DM (→ SW-5)
```

---

### SW-3: Inline Coaching Trigger

**Trigger:** User says "I'm stuck" / "I can't start" / drift detected / pattern re-entry during any module
**Participants:** Active Module, CoachingEngine, NeurostateService, Tension Engine, PatternDetection

```
1. Active module detects stuck signal (NLI classification or drift heuristic)
2. Active module pauses state machine, hands off to CoachingEngine
3. CoachingEngine: check Tension Engine quadrant
   - SWEET_SPOT → reinforce, no coaching needed
   - AVOIDANCE → cycle breaker protocol
   - BURNOUT → SW-12 (Burnout Redirect)
   - CRISIS → SW-11 (Crisis Override)
4. CoachingEngine: check segment
   - ADHD → PINCH activation (Passion, Interest, Novelty, Competition, Hurry)
   - Autism → Inertia protocol (transition bridges, NOT "just start")
   - AuDHD → Channel Dominance check first (→ SW-19), then route to ADHD or Autism protocol
   - Neurotypical → Standard motivation coaching
5. CoachingEngine LangGraph: Router → Enrich (Neo4j+Qdrant) → Coach (DSPy signature) → Memory → Summary
6. 4-tier response fallback: Optimized Artifact → DSPy → PydanticAI → Placeholder
7. EffectivenessService.track_intervention(type="inline_coaching", ...)
8. Return control to active module (resume state machine)
```

---

### SW-4: Pattern Detection → Alert

**Trigger:** PatternDetectionService detects destructive cycle or neurostate signal
**Participants:** PatternDetection, Aurora, NeurostateService, Admin (via Telegram DM)

```
1. PatternDetection runs on every interaction (event-driven)
2. Checks against 5 destructive cycle types + 14 neurostate signals
3. IF pattern detected:
   a. Classify severity (info / warning / critical)
   b. Check segment-specificity (pattern valid for this user's segment?)
   c. Check: is this a NEW pattern or recurrence?
4. IF recurrence → compare with previous intervention effectiveness (EffectivenessService)
5. IF info → log only, feed to Aurora narrative
6. IF warning → Aurora receives for next interaction framing
7. IF critical → immediate Telegram DM to admin with:
   - Pattern type, segment, frequency, user impact
   - Previous interventions tried + their effectiveness
   - Proposed response
8. Tension Engine: update user's quadrant if pattern shifts it
9. IF new pattern type not yet in detector → propose new detector to admin (→ SW-5)
```

---

### SW-5: RIA Learning Cycle

**Trigger:** Scheduled (weekly) + on-demand (admin request)
**Participants:** RIA Service, EffectivenessService, PatternDetection, DSPy, Admin

```
1. INGEST: Collect from last cycle:
   - EffectivenessService: all intervention outcomes
   - PatternDetection: all detected patterns
   - FeedbackService: user feedback aggregated
   - Avicenna: quality issues logged
2. ANALYZE (per segment, NEVER aggregate across segments):
   - Compare intervention effectiveness per type per segment
   - Identify: what works, what doesn't, what's untested
   - Cross-reference with research findings (applicable_segments)
   - Generate hypotheses
3. PROPOSE: For each actionable insight:
   - Create Proposal with: evidence, expected impact, affected segments, risk
   - Telegram DM to admin (one message per proposal, not bulk)
4. ADMIN DECISION: "Yes" / "No" / "Modify"
5. IF approved → DEPLOY:
   - DSPy: optimize affected prompts (→ SW-8)
   - Feature flag: staged rollout if admin approves (10% → 50% → 100%)
6. REFLECT: After deployment:
   - EffectivenessService measures new version (→ SW-6)
   - After min_samples reached → report to admin
   - Feed results back into next INGEST cycle
```

---

### SW-6: Effectiveness Measurement Loop

**Trigger:** Every tracked intervention (continuous)
**Participants:** EffectivenessService, RIA, Aurora, Admin

```
1. Intervention delivered (any type: coaching, impulse, prompt, reminder)
2. EffectivenessService.track_intervention() → register with timestamp + segment
3. 48h measurement window opens
4. Behavioral signals collected (NOT self-report):
   - Task completion rate (before vs after)
   - Response latency (faster = more engaged)
   - Session length change
   - Pattern recurrence (did destructive cycle continue?)
   - Energy trajectory (behavioral proxy)
5. EffectivenessService.measure_outcome() → InterventionOutcome
6. IF variant comparison requested:
   - EffectivenessService.compare_variants(A, B, segment, min_samples=20)
   - Per-segment comparison only
7. Results feed into:
   - RIA (next learning cycle → SW-5)
   - Aurora (narrative: "This approach worked for you")
   - Weekly Self-Doubt Check (→ SW-7)
```

---

### SW-7: Weekly Self-Doubt Check

**Trigger:** Scheduled (weekly, automated)
**Participants:** EffectivenessService, RIA, Admin

```
1. System auto-runs 5 questions (per segment):
   Q1: Are users completing more tasks than 4 weeks ago?
   Q2: Are users staying closer to their vision?
   Q3: Are users breaking out of destructive cycles more often?
   Q4: Is habit completion rate rising?
   Q5: Is pattern recurrence rate falling?
2. Score: count "Yes" answers per segment
3. IF 3+ "No" for any segment → Self-Doubt Report:
   - Which segment is struggling
   - Data behind each "No"
   - Possible causes (from EffectivenessService data)
   - Proposals for correction
4. Telegram DM to admin: "My interventions for [Segment] aren't working. Here's the data."
5. IF all segments pass → short confirmation to admin: "Weekly check: all segments improving."
6. Results logged for longitudinal tracking
```

---

### SW-8: DSPy Prompt Optimization + Deployment

**Trigger:** RIA proposal approved by admin (from SW-5)
**Participants:** DSPy, EffectivenessService, Admin

```
1. RIA proposal approved → DSPy receives optimization request
2. DSPy loads segment-specific signature (5 signatures, one per segment)
3. DSPy optimizes prompt using coaching_traces (Qdrant collection)
4. New prompt version created with:
   - Version number
   - Affected segment
   - Expected improvement metric
5. IF admin approved staged rollout:
   a. Feature flag: 10% of segment users → new prompt
   b. EffectivenessService: track both versions
   c. After min_samples (20): compare_variants()
   d. Report to admin: "New version +15% task completion for ADHD users (N=23)"
   e. Admin approves full rollout → 100%
6. IF admin approved direct rollout:
   a. Deploy to 100% immediately
   b. EffectivenessService: track from deployment point
   c. After 1 week: effectiveness report to admin
7. Old prompt version archived (never deleted)
```

---

### SW-9: TRON Incident Response

**Trigger:** TRON security scan detects anomaly
**Participants:** TRON, Admin, (affected services)

```
1. TRON continuous scan detects anomaly:
   - Rate limit violation
   - Unusual API pattern
   - Injection attempt
   - Data access anomaly
   - Infrastructure alert
2. Classify severity: LOW / MEDIUM / HIGH / CRITICAL
3. Behavior depends on TRON mode:
   OBSERVE mode (default/dev):
     → Log all levels → DM admin with recommendation for all levels
   SUGGEST+AUTO-LOW mode (beta):
     → LOW: auto-act (rate limit, block) + log
     → MEDIUM+: DM admin with recommendation, wait for approval
   AUTO-HIGH mode (production):
     → LOW-HIGH: auto-act + log
     → CRITICAL: auto-act + DM admin immediately
4. ABSOLUTE OVERRIDE: Mental Health Crisis > Security
   → User in crisis is NEVER locked out by security actions
5. All actions logged with: timestamp, trigger, severity, action taken, admin notified
6. Post-incident: TRON generates incident report → admin
```

---

### SW-10: Avicenna Quality Alert

**Trigger:** Avicenna detects spec violation, stuck state, or stale interaction
**Participants:** Avicenna, Admin

```
1. @avicenna_tracked decorator fires on every message handler
2. Avicenna checks against architecture spec (YAML):
   - Valid state transitions (is this transition allowed?)
   - Expected DB writes (did the write happen?)
   - SLA compliance (response time within bounds?)
3. Additional checks:
   - Stuck state: user in same module state > 30 minutes
   - Stale interaction: no response to system message > configured threshold
   - Segment mismatch: intervention doesn't match user's segment
4. IF violation detected:
   a. Add to rolling issue buffer
   b. Classify: INFO / WARNING / CRITICAL
   c. INFO → log only
   d. WARNING → buffer, DM admin if 3+ warnings in 1 hour
   e. CRITICAL → immediate DM to admin (60s cooldown between DMs)
5. DM format: "[SEVERITY] [Component] [Issue] [Affected User Count] [Since]"
6. Avicenna NEVER fixes anything. Diagnose only. Human decides.
```

---

### SW-11: Crisis Override

**Trigger:** Crisis signal detected (any source: NLI, PatternDetection, NeurostateService, CoachingEngine)
**Participants:** All components (override hierarchy activates)

```
1. Crisis signal detected:
   - User expresses self-harm / suicidal ideation
   - Burnout severity > 0.9 (BurnoutAssessment)
   - Tension Engine: CRISIS quadrant (LOW sonne + LOW erde)
   - Explicit distress language
2. IMMEDIATE: Override hierarchy activates
   SAFETY > GROUNDING > ALIGNMENT > OPTIMIZATION
3. ALL active workflows pause:
   - Daily Workflow → suspend
   - Active module → suspend
   - Proactive impulses → disabled for this user
   - Pattern alerts → muted (except safety-related)
4. CoachingEngine switches to crisis protocol:
   - Empathetic acknowledgment (segment-adapted)
   - NO task-focused prompts
   - NO "just breathe" / "just start" platitudes
   - Provide appropriate resources (localized)
5. TRON: mental health override active
   → User is NEVER locked out during crisis
6. Telegram DM to admin: "[CRISIS] User [ID] in crisis state. Protocol active."
7. Recovery: admin manually lifts crisis state after verification
8. Post-crisis: Aurora adjusts narrative (no "bounce back" framing)
```

---

### SW-12: Burnout Redirect

**Trigger:** BurnoutTypeClassifier detects emerging burnout OR burnout gate in coaching
**Participants:** NeurostateService (BurnoutTypeClassifier), CoachingEngine, Aurora, Daily Workflow

```
1. BurnoutTypeClassifier detects trajectory:
   - ADHD: boom-bust cycle (high output → crash)
   - Autism: overload → shutdown (skill regression, NOT failure)
   - AuDHD: 3 distinct types (identify which one)
2. Classify severity: emerging (0.3-0.6) | active (0.6-0.8) | critical (0.8+)
3. IF critical → SW-11 (Crisis Override)
4. IF active or emerging:
   a. Daily Workflow: switch to GENTLE_REDIRECT
      - No planning today
      - Recovery protocol instead
      - Reduced notification frequency
   b. CoachingEngine: shift from activation to recovery
      - ADHD: pacing protocol, energy banking
      - Autism: reduced demands, sensory recovery, acknowledge skill regression as temporary
      - AuDHD: identify burnout type FIRST, then segment-appropriate recovery
   c. Aurora: adjust proactive impulses
      - Reduce frequency
      - Shift to maintenance/rest themes
      - NO "get back on track" framing
5. CRITICAL ANTI-PATTERN: Behavioral Activation during Autistic Burnout = HARM
6. Recovery: gradual return detected by NeurostateService → report to admin
```

---

### SW-13: User Onboarding

**Trigger:** New user starts first interaction
**Participants:** NLI, Segment Middleware, Daily Workflow Engine, Aurora

```
1. New Telegram user detected (no User record in PG)
2. Language auto-detect via Telegram client locale
3. Welcome message (shame-free, warm, segment display names)
4. Segment selection:
   - Present: ADHD, Autism, AuDHD, Neurotypical, Custom
   - User selects (can change later)
   - Internal: store working_style_code (AD/AU/AH/NT/CU)
5. Create User record + SegmentContext initialized
6. First Vision capture:
   - "What does your ideal life look like?"
   - Store as Vision (type=life)
7. First 90-day goal derivation (from vision)
8. Timezone confirmation
9. Notification preference preview (segment-adapted defaults shown)
10. Daily Workflow: schedule first morning activation
11. Aurora: initialize narrative (StoryArc: "Beginning")
12. Avicenna: start tracking from first interaction
```

---

### SW-14: Vision/Goal Update Cascade

**Trigger:** User updates vision or goal
**Participants:** NLI, Planning Module, Aurora (Coherence Auditor), Neo4j

```
1. User expresses vision/goal change via NLI
2. Update Vision or Goal record in PG
3. Neo4j: update graph relationships
   - Vision → Goal chain integrity check
   - Goal → Task alignment check
   - Goal → Habit alignment check
4. Aurora Coherence Auditor:
   - Check: do existing goals still align with updated vision?
   - Check: do beliefs block the new goal?
   - Check: are habits still relevant?
5. IF misalignment detected:
   - Present to user: "Your goal X might not align with your updated vision. Want to revisit?"
   - NOT auto-delete anything
6. IF belief blocks new goal:
   - Surface belief: "You've said [belief]. This might be relevant to your new goal."
   - Route to Belief Module if user engages
7. Motif check: does the change reveal or contradict known motifs?
8. Aurora: update narrative chapter if significant change
```

---

### SW-15: GDPR Export/Delete

**Trigger:** User requests data export or account deletion
**Participants:** All modules (via Module Interface), GDPR framework, Admin

```
1. User requests via NLI: "Export my data" or "Delete my account"
2. EXPORT flow:
   a. Framework calls export_user_data(user_id) on every registered module
   b. Each module returns its data as structured dict
   c. Framework aggregates into single export package
   d. Include: all PG records, Neo4j subgraph, Qdrant vectors, Redis keys, Letta memories
   e. Encrypt package → deliver to user via Telegram (or secure link)
3. DELETE flow:
   a. Confirmation required (double-confirm for delete)
   b. Framework calls delete_user_data(user_id) on every registered module
   c. Each module deletes its data
   d. PG: cascade delete user + all related records
   e. Neo4j: delete user subgraph
   f. Qdrant: delete user vectors
   g. Redis: flush user keys
   h. Letta: delete agent memory
   i. Telegram DM to admin: "User [ID] requested full deletion. Executed."
4. Money data: decrypt before export, then delete encryption keys
5. Audit log: record that export/delete happened (without user data)
```

---

### SW-16: Capture → Route → Enrich (Second Brain)

**Trigger:** User sends quick capture (fire-and-forget message)
**Participants:** NLI (Intent Router), Capture Module, Module Registry, Qdrant

```
1. User sends message: "Idea: newsletter for coaches" / "12 euros sushi" / "Remember: call dentist"
2. NLI Intent Router: fast-path classification (regex ~70%)
   - capture.* → Capture Module
   - money.* → Money Module (→ module state machine)
3. Capture Module (fire-and-forget mode):
   a. Classify content type: task | idea | insight | reference | financial
   b. IF financial → route to Money Module directly
   c. Generate embedding → store in Qdrant (captured_items collection)
   d. Store CapturedItem in PG with classification
   e. Auto-route if clear: task → Planning inbox, idea → Second Brain
   f. IF ambiguous: store as unrouted, surface in next planning session
4. One-line confirmation: "Captured: Task 'Call dentist' → Planning inbox"
5. NO follow-up questions in fire-and-forget mode
6. Enrichment (async, later):
   - Qdrant semantic search: find related items
   - Neo4j: link to relevant goals/motifs if match found
   - Surface during next Daily Workflow morning hooks (→ SW-1 step 7)
```

---

### SW-17: Module Lifecycle (Register + Hooks)

**Trigger:** Application startup / hot-registration request
**Participants:** ModuleRegistry, Module, Daily Workflow Engine

```
1. APPLICATION STARTUP:
   a. ModuleRegistry scans for Module implementations
   b. For each module:
      - Validate: implements Module Protocol (handle, on_enter, on_exit, hooks, GDPR)
      - Register: add to _modules dict + _intent_map
      - Log: "Module [name] registered with intents [list]"
   c. Collect daily workflow hooks from all modules → inject into Daily Workflow Engine
2. HOT-REGISTRATION (future, Phase 5):
   a. New module deployed
   b. ModuleRegistry.register(new_module)
   c. Intent map updated (no restart needed)
   d. Daily Workflow hooks refreshed
   e. Avicenna: add module to spec validation
3. MODULE DEREGISTRATION:
   a. Module removed from registry
   b. Active users in that module → graceful exit (on_exit called)
   c. Intent map cleaned
   d. Avicenna: remove from spec
```

---

### SW-18: Neurostate Assessment (Tiered Pre-Flight)

**Trigger:** Daily Workflow morning (SW-1 step 3) + on-demand (coaching, midday)
**Participants:** NeurostateService (6 sub-services), SegmentContext

```
1. Determine assessment tier based on conditions:
   TIER 1 (ALWAYS):
     - 1-question energy check
     - ADHD/Neurotypical: self-report ("How's your energy?")
     - Autism/AuDHD: behavioral proxy (response latency, message length, vocabulary)
   TIER 2 (YELLOW energy OR segment requires):
     - + Sensory State Assessment (AU/AH)
     - + Channel Dominance Detection (AH only → SW-19)
   TIER 3 (RED energy OR 3+ consecutive red days):
     - + Full assessment: sensory + masking load + burnout trajectory
     - + Inertia Detection (type-specific)
   TIER 4 (AU/AH + afternoon):
     - Sensory accumulation check (load does NOT habituate)
     - Recalculate available capacity
2. Compile NeurostateSnapshot:
   - energy_level, sensory_load, masking_cost, burnout_risk
   - channel_dominant (AH only), inertia_type (if detected)
3. Store assessment in PG + Redis cache
4. Feed to: Daily Workflow (routing decision), CoachingEngine (context), Aurora (trajectory)
5. IF burnout_risk > threshold → SW-12 (Burnout Redirect)
6. IF crisis indicators → SW-11 (Crisis Override)
```

---

### SW-19: Channel Dominance Switch (AuDHD)

**Trigger:** NeurostateService detects channel shift OR scheduled check for AuDHD users
**Participants:** NeurostateService (Channel Dominance Detector), CoachingEngine, Daily Workflow

```
1. AuDHD user only (SegmentFeatures.channel_dominance_enabled == True)
2. Channel Dominance Detector analyzes signals:
   - Response patterns (speed, length, structure)
   - Task switching frequency
   - Sensory sensitivity level
   - Time-of-day patterns
3. Classify: adhd_dominant | autism_dominant | balanced | rapid_switching
4. Store ChannelState in PG
5. IF channel changed since last check:
   a. Update SegmentContext.neuro dynamically
   b. Notify CoachingEngine: adjust intervention style
      - ADHD-dominant day → novelty hooks, short sprints, PINCH
      - Autism-dominant day → routine reinforcement, transition bridges, sensory care
      - Rapid switching → minimal interventions, stability-first
   c. Daily Workflow: adjust reminder timing + frequency
   d. Aurora: adjust impulse type selection
6. ANTI-PATTERN: ADHD intervention on Autism-dominant day = BACKFIRE
   → Channel check is MANDATORY before any AuDHD coaching intervention
```

---

### SW-20: Feedback Collection → RIA

**Trigger:** User gives explicit feedback OR implicit signals detected
**Participants:** FeedbackService, RIA, EffectivenessService

```
1. EXPLICIT feedback:
   - User says "That was helpful" / "This doesn't work for me" / thumbs up/down
   - FeedbackService: store with context (which intervention, which module, which segment)
2. IMPLICIT feedback (behavioral):
   - EffectivenessService: intervention outcome signals
   - PatternDetection: did user repeat destructive cycle after intervention?
   - Session behavior: did user engage more or less after change?
3. FeedbackService aggregates per segment:
   - Intervention type → satisfaction score
   - Module → engagement score
   - Time-of-day → responsiveness score
4. Aggregated feedback feeds into RIA (→ SW-5 step 1):
   - "ADHD users rate morning impulses 2.1/5 but evening impulses 4.2/5"
   - "Autism users disengage after 3rd notification"
5. CRITICAL: Never aggregate feedback across segments
6. RIA uses feedback + effectiveness data to generate proposals
```

---

### Workflow Coverage Matrix

Every component participates in at least one system workflow:

| Component | Primary Workflows | Supporting |
|-----------|------------------|------------|
| **Aurora** | SW-2, SW-14 | SW-1, SW-3, SW-4, SW-7, SW-12, SW-13 |
| **TRON** | SW-9 | SW-11 |
| **Avicenna** | SW-10 | SW-5, SW-13, SW-17 |
| **RIA Service** | SW-5 | SW-7, SW-20 |
| **PatternDetection** | SW-4 | SW-2, SW-3, SW-12, SW-20 |
| **NeurostateService** | SW-18, SW-19 | SW-1, SW-3, SW-12 |
| **EffectivenessService** | SW-6 | SW-2, SW-5, SW-7, SW-8, SW-20 |
| **CoachingEngine** | SW-3 | SW-12, SW-11, SW-19 |
| **Tension + Fulfillment Engine** | SW-3, SW-4 | SW-11, SW-12 |
| **FeedbackService** | SW-20 | SW-5 |
| **Narrative Engine** (Aurora sub) | SW-2, SW-14 | SW-1, SW-4, SW-13 |
| **DSPy** | SW-8 | SW-3, SW-5 |
| **ModuleRegistry** | SW-17 | SW-1, SW-16 |
| **Daily Workflow** | SW-1 | SW-12, SW-18 |
| **NLI / Intent Router** | (entry for all) | SW-13, SW-16 |
| **GDPR Framework** | SW-15 | -- |

---

## Anti-Patterns

### Segment Anti-Patterns (NEVER)

These are violations of the core product design:

- Apply a finding validated for one segment to another
- Use ICNU scoring for Autism users (ICNU is an AuDHD/ADHD concept)
- System rotation as default for Autism users (consistency IS their operating system)
- "Just start" prompts for Autistic Inertia (Inertia != Activation Deficit)
- Behavioral Activation during Autistic Burnout (actively harms)
- Treat AuDHD as "ADHD + Autism combined" (it's its own category)
- Pomodoro for Autism/ADHD-I deep focus (interrupts monotropic focus)
- Same notification strategy for all segments
- Only self-report for energy in Autism/AuDHD (interoception unreliable)

### Neurostate Anti-Patterns (from Daily Burden Research, 96 findings)

- **Assume sensory habituation for Autism/AuDHD.** NT brains habituate; autistic brains accumulate. Track cumulative load, not snapshots.
- **Treat masking as binary (on/off).** Masking is a spectrum. AuDHD double-masking is exponential. Masking drains executive function.
- **Apply same burnout protocol to all segments.** ADHD boom-bust needs pacing. Autism overload->shutdown needs skill regression awareness. AuDHD has 3 distinct types.
- **Intervene on AuDHD without checking channel dominance.** ADHD-day intervention on Autism-dominant day backfires. Always detect channel first.
- **Use time-based deadlines for Autism transitions.** Autistic inertia is not about time management. Provide transition bridges, not countdown timers.
- **Assume "not responding" = "not engaged".** Autism shutdown and ADHD executive function collapse both look like disengagement but require opposite interventions.

### Architecture Anti-Patterns

- Module checks `if segment == "AD"` instead of using SegmentContext
- Agent has no own initiative but is called an "agent" (should be a service)
- Database introduced before there's data worth storing in it
- User needs to know a slash command to use a feature
- Daily workflow assembled from independent module calls instead of first-class graph
- GDPR as afterthought instead of built into Module Interface
- Intervention deployed without effectiveness measurement

### Research Anti-Patterns

- **ADHD contamination:** 50-70% of Autism literature is ADHD-contaminated. Scrutinize Autism findings extra carefully.
- Aggregate findings across segments (each segment is analyzed independently)
- Apply finding without checking `applicable_segments`

---

## Internationalization

| Aspect | Approach |
|--------|----------|
| Primary language | English |
| Supported | English, German, Serbian, Greek, extensible |
| Detection | Auto-detect via Telegram client locale |
| Implementation | i18n keys in every module from day one |
| User-facing segment names | Translated per language |

---

## Research Foundation

The system is built on extensive research:

| Research Set | Scope | Findings |
|-------------|-------|----------|
| 5 Meta-Syntheses (general) | ADHD, Autism, AuDHD, Neurotypical, Custom | 56 findings |
| 3 Meta-Syntheses (Daily Burden) | ADHD, Autism, AuDHD daily challenges | 96 findings (49 HCF, 30 MCF, 17 LCF) |
| 1 Cross-Synthesis (general) | Cross-segment patterns | Collision map |
| 3 Meta-Syntheses (Money) | Financial behavior per segment | 60 findings |
| Feature Extraction | Implementable features from all research | 25 new features, 10 extensions |
| Design Principles | From all research | 12 principles, 15 anti-patterns |

**All research is segment-specific. Findings are never applied across segments without explicit validation.**

---

_Aurora Sun V1 Architecture. Created 2026-02-13._
_Successor to Ravar V7. Complete rebuild with hindsight-informed design._
