# ADR 0003 — Claws run in ephemeral git worktrees

**Status:** accepted
**Date:** 2026-04-29 (originally in CGL); migrated 2026-04-30

## Context

A claw is a one-shot `claude -p` Claude process the supervisor spawns to do
work. Multiple claws often run in parallel. They mutate the lab's working
tree (write code, edit files, commit).

Three architectures considered:

1. **Direct mutation** — claws write directly to the lab's working tree.
   Simple, but parallel claws contend on the same files.
2. **Stash-and-pop** — each claw stashes the working tree, mutates, pops.
   Brittle under parallelism.
3. **Ephemeral worktrees** — each claw gets its own git worktree branched
   off the lab's HEAD. Claws never see each other's working trees.

## Decision

**Ephemeral worktrees.** Each claw spawn:

1. Creates a fresh worktree at `<lab-parent>/trees/claw-<slug>-<ts>/`
2. Branches off `<lab>` HEAD into `claw/<slug>/<ts>`
3. Runs `claude -p` with cwd inside that worktree
4. Auto-commits any changes when the claude process exits
5. Worktree + branch survive until the supervisor merges or abandons

The lab's main working tree is never touched by claws.

## Consequences

- Multiple claws run in parallel without contention.
- Failed/abandoned claws leave a branch + worktree the user can inspect.
- Disk cost: each claw worktree is a full lab checkout (cheap on a single
  filesystem; git worktrees share most objects).
- Merging a claw is an explicit step (`cgl-claw merge <slug> <ts>`), not
  automatic. The supervisor decides when to fold work back in.
- "Run multiple claws in parallel" is a first-class operating mode. Many
  systems pretend to support this; few actually do.

## Why merge ceremony, not auto-merge

Earlier prototypes auto-merged claws on success. This caused two problems:

1. Sequential claws on the same branch: if claw A merges first and shifts
   `<lab>` HEAD, claw B's branch (still on the old HEAD) can't fast-forward.
2. The director loses the chance to inspect the change before it lands on
   main.

`cgl-claw merge` rebases the claw branch onto the current HEAD before the
ff-merge, handling case 1. Case 2 stays a feature: the director gets to
review.

## Disk hygiene

Worktrees accumulate. Cleanup is manual via `cgl-claw abandon` or
periodic `git worktree prune`. A future enhancement: auto-cleanup of
worktrees older than N days that haven't been touched.
