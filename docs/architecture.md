# Architecture

Studio's runtime model: what's persistent, what's attended-session, what's
ephemeral.

---

## The five buckets

Every component in Studio lives in one of five lifecycles:

```
┌─────────────────────────────────────────────────────────────────────┐
│  PERSISTENT STATE (survives detach, survives reboot)                │
│  ────────────────────────────────────────                           │
│  • Lab content (surfaces/, investigations/, systems/)               │
│  • Spine (skills/, runbooks/, decisions/)                           │
│  • Ledger + theme vault (.intel/)                                   │
│  • Supervisor session logs (~/.claude/projects/.../<uuid>.jsonl)    │
│  • Per-machine state (~/.local/state/studio/<basename>/)            │
└─────────────────────────────────────────────────────────────────────┘
            ↑
            │  read/written by:
            │
┌─────────────────────────────────────────────────────────────────────┐
│  ATTENDED SESSION (only exists when director is at the keyboard)    │
│  ────────────────────────────────────────                           │
│  • tmux session (cgl-<basename>)                                    │
│  • Bridge TUI (Python/Textual process)                              │
│  • Director pane (Claude conversation)                              │
│  • Visible supervisor pane (per-lab Claude session)                 │
└─────────────────────────────────────────────────────────────────────┘
            ↑
            │  spawn:
            │
┌─────────────────────────────────────────────────────────────────────┐
│  EPHEMERAL EXEC (one-shot, per task)                                │
│  ────────────────────────────────────────                           │
│  • Claws (claude -p in their own git worktrees)                     │
│  • Themes pipeline runs (cgl-themes --reflect)                      │
│  • Haiku scoring calls                                              │
└─────────────────────────────────────────────────────────────────────┘
            ↑
            │  triggered (eventually) by:
            │
┌─────────────────────────────────────────────────────────────────────┐
│  CRON (no agents, only renders state)                               │
│  ────────────────────────────────────────                           │
│  • (Future) snapshot rendering between attended sessions            │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  PASSIVE LISTENER (one always-on process)                           │
│  ────────────────────────────────────────                           │
│  • (Future) Bellclaw — polls inbound channels, queues items         │
└─────────────────────────────────────────────────────────────────────┘
```

The principle: **separate sensing from acting.** Sensing is cheap, deterministic,
always-on (cron, bellclaw). Acting is expensive and judgment-laden — gated on
the director being present.

Today, only the first three buckets are wired. Cron and bellclaw are designed
but deferred.

---

## Process tree (when director is attended)

```
tmux server (-L cgl)
  └── cgl-<basename> session
        ├── lab window (4 panes)
        │     ├── %0  director pane: claude (cross-lab strategy)
        │     ├── %2  bridge pane:   python (Textual TUI)
        │     ├── %1  utility pane:  bash
        │     └── %X  supervisor pane: claude (current lab)
        │
        ├── _supervisors window (parked panes; supervisors run in background)
        │     ├── placeholder: bash
        │     ├── claude (lab A)
        │     ├── claude (lab B)
        │     └── ...
        │
        └── arm-* windows (one per worktree under <lab-parent>/trees/)
              └── shell: bash (cwd = arm path)
```

The Bridge orchestrates which supervisor is in the visible slot. Switching
labs swaps panes between the lab window and `_supervisors` via `join-pane` /
`break-pane`. Backgrounded supervisors keep running.

---

## State paths

```
$CGL_LAB_ROOT/                       ← user data
├── surfaces/<slug>/                   surface labs
├── research/investigations/<slug>/    investigation labs
├── systems/<slug>/                    systems labs
├── runbooks/                          spine: runbooks
├── decisions/                         spine: ADRs
├── .claude/skills/                    spine: skills
├── intel/                             director's intel layer
│   ├── state.json
│   ├── publish-log.jsonl
│   └── themes/<slug>.jsonl            theme vault per lab
└── .claws/                            (per-lab) ephemeral claw bookkeeping
                                       (under each lab's dir, not at root)

$XDG_STATE_HOME/studio/<basename>/   ← per-machine, per-lab runtime state
├── panes.json                         which pane is what (current view)
├── supervisors.json                   slug → UUID mapping
├── focus-cache/                       focus snapshot Haiku cache
└── themes-cache/                      themes pipeline scoring cache

~/.claude/projects/<cwd-slug>/<uuid>.jsonl  ← supervisor session logs
                                                (managed by Claude Code itself)
```

---

## Data flow

```
director keyboard
      │
      ▼
┌─────────────────┐         ┌──────────────────────┐
│  Bridge TUI     │ reads → │  state_reader.py     │ reads → lab files,
│  (Python/Textual)│         │  + focus_core.py     │         intel/, themes/
└─────────────────┘         └──────────────────────┘
      │
      │ keyboard actions: r refresh, [/] cursor, Enter activate, f toggle, ...
      │
      ▼
┌─────────────────┐ subprocess
│  cgl-* primitives │ ────────── reads/writes:
└─────────────────┘                • $CGL_STATE_DIR/* (panes, supervisors)
      │                            • lab files (when creating, archiving)
      │                            • git worktrees under trees/
      │                            • supervisor session logs (via UUID)
      │
      ▼
tmux ops:
  • respawn-pane (lab activation, supervisor swap)
  • send-keys (cgl-tell)
  • new-window (arm worktrees)
  • join-pane / break-pane (parking supervisors)
```

The Bridge **never mutates state directly**. It reads via state_reader; it
mutates via primitives. The primitives are the only writers.

---

## Why subprocess instead of in-process?

For everything except the snapshot collection (which lives in `focus_core.py`
and is imported in-process for speed), the Bridge calls primitives via
subprocess.

Reasons:
- The primitives are also runnable from a shell — that's their first-class
  use case. Bridge using them keeps one code path.
- Subprocess isolation makes the Bridge resilient to bugs in the primitives.
- Each primitive can pick its own Python runtime (the harness's venv) without
  the Bridge worrying about it.

The exception: per-tick state read (which happens every 5s) goes through
`focus_core` in-process to avoid Python startup overhead × refresh frequency.

---

## Extension points

If you want to add something to the harness:

| Want to add… | Where it goes |
|---|---|
| A new primitive | `bin/cgl-<name>` — bash or Python, source `_studio_env.sh` / import `_env` |
| A new lab kind | `studio/lib/state_reader.py` — add a `list_<kind>()` and update `list_labs()` |
| A new federation surface | `studio/lib/focus_core.py` — add a function, plug into `collect_whole()` |
| A new Bridge view | `studio/bridge/app.py` — extend FocusPane modes, add binding |
| A new claw type | `bin/cgl-claw` extension or a new primitive that wraps it |

There is no plugin system. Studio is small enough that fork-and-modify
is the expected path.

---

## What this architecture is NOT

- **Not high-availability.** A single tmux session, on a single machine,
  with single-process bottlenecks. If tmux dies, the Bridge dies. The state
  files survive; you can re-launch.
- **Not eventually-consistent.** State files are read directly; no sync,
  no replication, no clock skew tolerance.
- **Not real-time.** The 5s refresh tick is fine for human attention; not
  fine for sub-second monitoring. Studio is not a dashboard for a system
  under heavy automated load.
