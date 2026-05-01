# ADR 0002 — Per-machine state keyed by lab basename

**Status:** accepted
**Date:** 2026-04-30

## Context

The harness writes per-machine runtime state: which tmux pane is what,
which supervisor maps to which UUID, snapshot caches, theme score caches.
Originally these all lived at `~/.local/state/cgl/*` — a single bucket.

But a single director may operate on multiple labs on the same machine
(CGL lab + a personal lab + a side-gig lab, for example). Single-bucket
state means switching `CGL_LAB_ROOT` between sessions corrupts each other.

## Decision

State is keyed by a per-lab basename:

```
$XDG_STATE_HOME/studio/<basename>/
├── panes.json
├── supervisors.json
├── focus-cache/
└── themes-cache/
```

The basename is derived as:
- `$CGL_PROFILE` if set (explicit override for collision resolution)
- otherwise `basename(CGL_LAB_ROOT)`

Tmux session names follow the same convention: `cgl-<basename>`. Multiple
sessions can coexist on the `-L cgl` socket.

## Consequences

- Multi-lab "just works": set `CGL_LAB_ROOT` differently in different shells
  and the harness does the right thing.
- Collision risk: if two labs have the same basename, their state collides.
  Mitigation: `CGL_PROFILE=foo` overrides the basename.
- Per-lab caches grow over time. Cleanup: remove the lab's state dir.
- `~/.local/state/cgl/*` from older versions is **not migrated automatically**.
  Old state is left in place; harness writes new state to the new location.

## Alternatives considered

- **Hash of CGL_LAB_ROOT path** — opaque, robust against collisions, but
  unreadable. Filed paths like `~/.local/state/studio/8f3a/` are user-hostile.
- **First-class profile system** — `~/.config/studio/profiles/*.toml` and
  `cgl-tmux --profile foo` — was deferred to v0.2+. Basename keying gives
  80% of the value with no profile concept yet.
