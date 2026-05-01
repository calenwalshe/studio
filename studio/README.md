---
layer: spec
status: design — not yet built
created: 2026-04-29
last_reviewed: 2026-04-29
---

# Studio — High-Level System Design

This directory holds the studio architecture spec — a **redesign-as-pattern**
of what's been built so far in `lab/.claude/skills/director/`,
`lab/research/`, and the cgl-* primitives.

## Status

**Design only. Not yet built.**

The architecture document captures a higher-abstraction view of the
director-orchestration pattern that emerged organically from building:

- The federation worktree pattern (`trees/<arm>/`)
- The cgl-* primitives (cgl-tmux, cgl-delegate, cgl-publish, cgl-send, cgl-status-pane)
- The Research Department (driver + bridge + critic + auto-publish)
- The cgl-publish + Drive Director Inbox

The spec names these as instances of a **meta-framework** with two levels:
recipe vs. studio instance. Today, `lab/` IS the studio instance and
there's no separation. The spec proposes that separation.

## What's in here

- `SPEC.md` — the architecture document (the high-level system design)

## What is NOT here

- Implementation. Nothing in `studio/` has executable code (yet).
- A migration plan from current state to the spec.
- A decision on whether to migrate at all.

## How this relates to what's already built

| Spec concept | Current implementation | Gap |
|---|---|---|
| Director's bridge | tmux command center + Claude Code session | Bridge currently DOES read agent output; spec says it shouldn't |
| Labs | `surfaces/*` (4 dormant) + `research/` (1 active dept) | No memory-bearing lab abstraction; research dept is closest |
| Claws | Cortex skills + bridge's Haiku/Sonnet/Gemini calls | No declarative claw catalog |
| Plays | Driver's hardcoded research cycle | One play exists but isn't extracted |
| Spine | `lab/.claude/skills/director/`, `runbooks/`, `decisions/` | No version pinning or eval contract |
| Capabilities | `cgl-publish`, `cgl-delegate`, `cgl-tmux`, etc. | No semver, no commons |
| Commons | — | Doesn't exist |
| Bellclaw | — | Doesn't exist |
| Ledger | `intel/publish-log.jsonl`, per-investigation `events.jsonl`, `costs.jsonl` | Distributed; not unified |
| Cockpit | `cgl-status-pane` + `/director status` | On-demand, not pre-rendered snapshots |
| Lifecycle | — | Biggest gap. Things currently go idea → built without staged gates |

## Why this is in `studio/`, not `decisions/`

Studio is a **structural spec**, not a one-time decision. ADRs are append-only
records of choices already made. This is a living design that may evolve
before any implementation. If/when the director commits to migrating to
the studio architecture, an ADR records that adoption decision and points
back here.

## Next moves (not commitments — options)

**Option A: Treat as v1.0 meta-framework spec.** Refactor the existing
`lab/` to match. Extract claws declaratively. Introduce lifecycle. Build
Bellclaw. 3-5 session effort.

**Option B: Treat as a forcing-function lens.** Use the spec's
vocabulary on the next thing built (next investigation, surface
activation, new lab). Let it prove itself by use first, then formalize.

**Option C: Park it.** The director sat with the design, decided the
current pattern (research dept + cgl-*) is good enough for now, and
returns to validate-by-use of v0.7. The spec stays here as a future
reference.

## Honest read on the spec

The spec is sharp and well-formed. Most of the structure already
exists implicitly in the build — the spec names it. The biggest gaps
are:

1. **Bridge discipline** ("dispatches but doesn't read") is aspirational
   today. The current bridge (this Claude session) reads everything
   and summarizes.
2. **Lifecycle gates** (hunch → sandbox → incubate → lab → platformize
   → retire) don't exist. The research dept went idea → shipped in one
   session.
3. **Bellclaw** (the persistent passive listener) is the only piece
   that genuinely doesn't exist anywhere in the lab today.

The other components either exist or have analogs. The spec's value
isn't in proposing new components — it's in **naming the pattern** so
future work follows the recipe deliberately rather than re-deriving it.
