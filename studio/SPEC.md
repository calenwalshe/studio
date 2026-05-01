---
layer: spec
type: high-level-system-design
status: design — not yet built
created: 2026-04-29
last_reviewed: 2026-04-29
author: Calen (with Claude assistance)
---

# Studio — High-Level System Design

## Vision

A personal **director's studio** for orchestrating multi-agent research
and build work. The operator is a single person ("the director")
conducting many specialized AI agents across many concurrent projects.
The studio is the apparatus that makes one person's attention productive
across that surface area without losing work, drifting into chaos, or
pretending agents are autonomous when they aren't.

The animating constraint: **the studio is an instrument, not a
factory.** It only produces when the director is playing it. Nothing
runs autonomously in the background. When the director detaches, the
agents die and the system goes silent. What persists across detachment
is *state* (queues, ledgers, snapshots, memory) — not *activity*.

This inverts the usual agentic-system framing. Throughput is measured
in deliverables per **director-hour**, not deliverables per wall-clock
day. The job of the system is to compress more conducted work into
each attended hour, and to make sit-down-to-productive time as short
as possible.

## The two-level structure

The system separates the **recipe** from the **instance**.

- **Meta-framework** — a reusable, versioned set of components and
  conventions for how a studio is shaped. One recipe.
- **Studio instance** — a concrete instantiation of that recipe with
  its own scope, memory, ledger, and director seat. Many instances
  (e.g., one for work, one for family, one for open-source) can
  coexist, each isolated from the others, each pulling shared assets
  from a common pool.

This separation is what lets the architecture grow without each new
domain re-deriving the same primitives.

## Core components and how they interact

### The director's bridge
The control surface. A single attended session per studio. Everything
the director does flows through here. The bridge dispatches work and
reads aggregated state — it does not itself read the output of
subordinate agents or summarize their work. That discipline keeps the
orchestrator's context clean and prevents the bridge from becoming the
bottleneck.

### Labs
The bounded units of long-lived work. A lab owns a mission, a persona,
KPIs, a brain namespace, and stakeholders. Real project code stays
where it lives — the studio holds only a thin wrapper that points at
the real folder and tracks lab-level state. A lab is **memory-bearing**:
it accumulates context across sessions.

### Claws (specialized agents)
Short-lived, specialized agent instances. Each is defined declaratively
(model, permissions, skills, tools, prompt preamble, isolation
strategy). A claw is **not memory-bearing** — it loads what it needs
at spawn time and dies on detach. The catalog is small and curated
(research, code, reviewer, design, etc.); claw proliferation is treated
as a smell.

### Plays
Named, reusable multi-claw choreographies — the muscle memory of the
studio. A play encodes a sequence like "research → design →
implementation → review → write-up" with explicit handoff seams where
the director approves. The point is to convert one-off improvisation
into rehearsed routines.

### The spine
Per-studio shared assets: claw definitions, plays, persona/voice
guides, evals, capabilities, templates. The spine is **pull-only at
runtime** — labs and claws load from it; they do not continuously
write back. Publication into the spine is a distinct, intentional act,
not a side effect of work.

### Capabilities
Versioned bundles of tools, skills, and evals extracted from a lab once
they're proven. Labs **pin specific versions** — auto-upgrade is
forbidden so a publish never silently breaks a dependent lab.
Capabilities are how the studio compounds: a useful pattern in one lab
becomes a versioned asset other labs can adopt deliberately.

### The commons
A cross-studio shared pool. Capabilities promoted out of one studio's
spine are published to the commons; other studios pull from there.
This is how the recipe spreads across instances without coupling them.

### The passive listener (Bellclaw)
The **only** persistent process. It polls inbound channels (chat, mail,
calendar, cron, events) and queues items. It never spawns agents,
never decides, never acts. The director triages the queue when they
sit down. This is the architectural answer to "how do I not miss
things while staying honest about no background work."

### The ledger
Append-only accounting of every dispatched task: which lab, which
claw, which play, tokens, cost, status, artifacts, pointer to the
full session log. Every row carries a status and heartbeat so stale
work can be swept on next attach. The ledger is the substrate for
cost accountability, retrospectives, and "what did I actually do this
week."

### The cockpit
The ASCII call sheet rendered when the director attaches. It is **not**
a "what the studio is doing now" dashboard — there is no "now" when
detached. It surfaces what needs the director's attention: queued
items, hot tasks, rot risk on each lab (time-since-touch), inbox depth,
capability drift between spine and commons. Cron pre-renders snapshots
so attach is instantaneous.

### The lifecycle
A staged promotion path that every artifact lives on: hunch → sandbox
→ incubate → lab → platformize → retire. Promotion between stages is
gated by explicit checks (brief written, charter exists, evals pass,
used by ≥2 labs, etc.). This is the discipline mechanism — without
it, every hunch silently becomes a half-built project. Retirement is
a real ritual, not a deletion.

## How the parts cohere

A typical attended session looks like this:

1. **Ignite** — director attaches; cockpit renders from snapshots;
   last-words from prior session surface at top.
2. **Triage** — director scans the Bellclaw queue and the cockpit's
   rot/hot signals.
3. **Cast** — director either spawns a single claw against a task or
   runs a play (multi-claw choreography).
4. **Conduct** — claws work in parallel; director moves between them
   at handoff seams.
5. **Account** — every dispatched task lands in the ledger with cost
   and pointers.
6. **Close** — closing ritual kills claws, captures per-lab last-words,
   freezes a snapshot for tomorrow.

Between sessions: the listener queues, cron renders, nothing produces.
The studio is dark.

Across sessions: the ledger accumulates, labs' brains accumulate, the
spine slowly hardens as patterns prove out and get extracted into
versioned capabilities, capabilities flow through the commons to other
studios.

## Design tensions worth naming

- **Discipline vs. friction.** Lifecycle gates are the whole point,
  but every gate is friction. The system is only as good as the
  director's willingness to honor them.
- **Memory location.** Labs remember; claws don't. This is a
  deliberate constraint to keep agents cheap and replaceable, but it
  pushes complexity into the lab layer.
- **Spine as god-object risk.** Centralizing voice, evals, and
  capabilities is powerful and dangerous. Publication-as-intentional-
  act and version pinning are the guardrails.
- **Multi-studio coordination.** Studios are isolated by design; the
  commons is the only seam. Whether that's enough as the surface area
  grows is an open question.
- **Relationship to existing orchestration tools** (task trackers,
  agent frameworks, IDE harnesses). The studio is intended to *compose*
  these, not replace them — but the seams aren't fully worked out.

## What this is not

- Not autonomous. Not always-on. Not a swarm.
- Not a replacement for the underlying agent harness, code review
  system, or task tracker.
- Not multi-user or cloud-native. Single operator, local-first.
- Not a UI product in v1 — CLI, terminal multiplexer, ASCII cockpit.
  A graphical surface is downstream.

## Research questions this design opens

- What's the right **memory architecture** at the lab layer to support
  resumption without unbounded context growth?
- How do **capabilities** version and evolve in practice — is semver
  enough, or do evals need to be the contract?
- What's the right **granularity for plays** — when does choreography
  pay for itself vs. ad-hoc casting?
- How does a **passive listener** stay useful without becoming a
  notification firehose?
- What does **rot detection** look like beyond time-since-touch — can
  the system surface when a lab's stated mission has drifted from its
  actual activity?
- How do **multiple studios** share learnings without coupling, beyond
  rsync'd capability bundles?
- What's the **right unit of cost accounting** — per-task is the
  obvious answer, but plays and lifecycle stages are the units the
  director actually reasons in.
- How does this compose with **existing agent orchestration frameworks**
  rather than reinventing them?
