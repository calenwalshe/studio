# Concepts

Studio's vocabulary. Read this once and the rest of the lab OS framing makes sense.

---

## Lab

A **lab** is a unit of long-lived work. It's a directory in the user's
filesystem. The harness operates on whatever lab the env points at via
`$CGL_LAB_ROOT`.

A lab has one of three **kinds**:

| Kind | Purpose | Where it lives |
|---|---|---|
| `surface` | Public-facing output (a website page, a downloadable artifact) | `<lab>/surfaces/<slug>/` |
| `investigation` | A research effort with a contract, cycles, and budget | `<lab>/research/investigations/<slug>/` |
| `systems` | Internal infrastructure or tooling work | `<lab>/systems/<slug>/` |

A lab's identity is its **slug**: `surface/snake`, `investigation/foo`,
`systems/distribution-engine`. The slug doubles as a directory key and as the
ID used by primitives (`cgl-claw spawn surface/snake "..."`).

The director runs **multiple labs in parallel** via the federation view.
Switching between labs in the Bridge swaps the supervisor pane to the new
lab's persistent Claude session.

---

## Supervisor

Each lab has a **persistent Claude session** — its supervisor — keyed by a
deterministic UUID. Sessions survive detach because Claude Code persists them
to `~/.claude/projects/<cwd-slug>/<uuid>.jsonl`.

The supervisor is a *coordinator*, not a worker. When the director gives it
a task that takes more than a few seconds, the supervisor spawns a **claw**
(see below) and stays free for more direction.

Each supervisor sees the lab's spine (skills, runbooks, ADRs) and can read
the lab's surfaces, investigations, etc., but typically delegates execution
to claws.

`cgl-supervisor activate <slug>` starts or resumes the supervisor for that
lab inside the current shell. The Bridge does this automatically when you
press a number key or Enter on a federation row.

---

## Claw

An **ephemeral background worker.** A claw is a one-shot Claude process
(`claude -p`) that runs in its own git worktree branched off the lab's
current HEAD. After the claw exits, its work lives on its branch until the
supervisor merges or abandons it.

```
cgl-claw spawn <slug> "<task description>"
```

The claw's work is *not* on the main working tree. The lab can keep moving
forward while the claw runs in parallel without contention. Multiple claws
can run simultaneously, each in its own worktree.

When the claw finishes, the supervisor decides:

- **Merge** — `cgl-claw merge <slug> <ts>` rebases onto main, ff-merges,
  removes the worktree.
- **Abandon** — `cgl-claw abandon <slug> <ts>` drops the worktree + branch
  with no merge.

Claw timestamps are `YYYYMMDD-HHMMSS`; logs and result files land in
`<lab>/<lab-subpath>/.claws/<ts>.{log,result.md,meta.json}`.

---

## Arm

An **arm** is a long-lived parallel branch of a lab's work. Like a claw, it's
a git worktree. Unlike a claw, it isn't ephemeral — arms can live for weeks
while you incubate a different direction without affecting the lab's main
branch.

```
cgl-arm new <name> [--from <ref>]
cgl-arm merge <name>
cgl-arm kill <name>
cgl-arm list
```

Arms live at `<lab-parent>/trees/<name>/` (sibling of the lab dir). Each gets
its own tmux window in the cgl session, automatically.

Use cases:
- An experimental rewrite of a major lab subsystem
- A long-running spike that may or may not graduate
- Parallel tracks of work that share the lab's history

When an arm matures into its own initiative, **promote it to a lab** —
typically a new surface or systems lab.

---

## Spine

The lab's **accumulated technique library.** Reusable assets that survive
across labs and inform how supervisors work:

| Type | Path | What it is |
|---|---|---|
| Skills | `<lab>/.claude/skills/` | Named procedures (invoked via `/skill-name`) |
| Runbooks | `<lab>/runbooks/` | Step-by-step procedures for repeat ops |
| Decisions (ADRs) | `<lab>/decisions/` | Append-only log of choices and reasoning |

Spine is *shared across all labs in a single lab repo*. When a pattern proves
out in one surface, it earns a runbook entry. Future labs draw on the
runbook rather than re-improvising.

---

## Bridge

The **director's TUI.** A keyboard-driven control surface that shows the
state of every lab and lets the director switch between supervisors,
spawn claws, and monitor activity.

The Bridge has two views:

- **Federation inbox** — cross-lab status. Shows stale & blocked rows,
  an open-asks inbox, and an investment dashboard. Default on launch.
- **Lab focus** — drill into one lab. Shows the lab's open themes, claws,
  recent commits, and a live event feed.

Toggle between them with `f`.

The Bridge is **read-only**. It dispatches to primitives (`cgl-claw`,
`cgl-tell`, etc.) for any mutation but doesn't mutate state itself.

---

## Federation

The set of all labs the director is operating on, plus the harness scaffolding
that lets them coexist:

- A single tmux session per lab basename (`cgl-<basename>`).
- A shared `_supervisors` window holding parked supervisor panes.
- Per-lab state at `~/.local/state/studio/<basename>/`.
- One Bridge window the director uses to navigate.

The federation view (in the Bridge) gives a cross-lab read: what's stale,
what's open, where time/money is going.

---

## Themes

Studio's **executive log per lab.** A pipeline produces director-grade
chunks from raw activity:

1. **Extract** — pull raw events (supervisor messages, claws, commits)
   idempotently via an impressions-index.
2. **Chunk** — apply heuristic gates (commits, claw events, asks, status
   keywords) to produce candidate themes.
3. **Score** — Haiku scoring with a 0.7 threshold; promotes only material
   updates.
4. **Render** — vault as a chronological executive log.

The Bridge reads the per-lab vault at `<lab>/.intel/themes/<slug>.jsonl`
to drive the federation inbox and the lab-focus event feed.

---

## Director

The **single human** at the keyboard. Not a role; not multi-tenant. The
harness assumes one director per machine.

The director has:
- A **director pane** (top-left in the Bridge) — a Claude session for
  cross-lab strategic work.
- A **bridge pane** (top-right) — the TUI itself.
- A **utility pane** (bottom-left) — a normal shell for `cgl-*` commands.
- A **supervisor pane** (bottom-right) — whichever lab's supervisor is
  currently active.

The director's workflow:
1. Sit down. Open the federation view. Read what needs attention.
2. Pick a lab. Activate its supervisor.
3. Direct the supervisor (via the supervisor pane or `cgl-tell`).
4. Supervisor spawns claws as needed; reports back.
5. Director merges, decides, moves on.

---

## Target-direction concepts (planned)

These are **directional concepts** for Studio as a director-oriented lab OS.
They guide framing and future design, but are not claims about current
implementation.

- **Orientation** — the current director posture for a lab (what matters now,
  what decisions are pending, and what outcomes are being driven).
- **Evidence** — concrete observations that justify a recommendation or
  decision (commits, logs, outputs, messages, measurements).
- **Artifact Bundle** — a grouped handoff package for review/promotion,
  combining key outputs, rationale, and pointers to evidence.
- **Promotion Gate** — an explicit checkpoint where work is reviewed before
  being merged, escalated, published, or otherwise advanced.
- **Source Pack** — the source set used to produce a recommendation or output,
  so conclusions can be audited and replayed.

For the framing narrative, see [`docs/lab-os.md`](lab-os.md).

---

## What this is NOT

- **Not an agent framework.** Studio is plumbing for a single director and
  their LLM coworkers. There's no autonomous loop, no scheduler, no
  multi-agent negotiation.
- **Not a workflow engine.** No DAG, no retries, no orchestration logic.
  Long work belongs to supervisors and claws, not the harness.
- **Not multi-tenant.** Single director per machine. The state files and
  conventions assume one human in charge.
- **Not opinionated about Claude's behavior.** The harness just routes;
  what the supervisors do is up to you (and your skills/runbooks/prompts).
