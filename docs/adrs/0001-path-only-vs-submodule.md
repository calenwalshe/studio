# ADR 0001 — Studio consumed via PATH, not as a submodule

**Status:** accepted
**Date:** 2026-04-30

## Context

A user lab needs to invoke the Studio harness (`cgl-tmux`, `cgl-bridge`, the
Python TUI source). Two architectures were considered:

1. **PATH-only** — Studio lives in its own repo, installed once at
   `~/projects/studio/`. The user's shell rc puts `~/projects/studio/bin/` on
   PATH and exports `CGL_LAB_ROOT`. The user lab is just a directory; it
   does not import Studio in any way.

2. **Submodule** — Studio is added as a git submodule inside each user lab
   (`<lab>/.studio/`). Updates: `cd <lab>/.studio && git pull`, then commit
   the new submodule pointer in the lab.

## Decision

**PATH-only.**

## Consequences

- A single `git pull` in `~/projects/studio/` updates every lab on the
  machine.
- User lab repos contain zero Studio source; their git history is purely
  about the lab's content.
- Multi-lab on one machine works trivially (env vars switch which lab the
  harness operates on).
- Cost: no per-lab Studio version pinning. If you upgrade Studio and a
  primitive's behavior changes, every lab on the machine is affected at
  the same time.
- Mitigation: tag releases (`v0.1`, `v0.2`, …) and pin via `git checkout
  <tag>` in the harness if a user wants version stability.

## Why not submodule

- Submodules are friction-heavy. Updating the harness requires a commit in
  every lab repo, even when the lab content didn't change.
- Submodules couple lab content to harness version in a way that obscures
  which is which when reading lab git history.
- The mental model we want is "the harness is a tool, like vim or jq" —
  not "the harness is part of the project."

## Why not vendor

Vendoring Studio source into each lab was considered briefly and rejected:
mixes concerns, makes "what changed in the lab vs in the harness" impossible
to read at a glance, and tempts users to make lab-local edits that should
be upstream changes.
