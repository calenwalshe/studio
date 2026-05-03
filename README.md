# studio

A human-in-the-loop lab operating system for director-oriented intelligence work.

> **Status:** v0 — extraction in progress. See [PLAN.md](PLAN.md).

## What this is

A keyboard-driven control surface for running multiple long-lived "labs" of
work in parallel — each with its own supervisor (a persistent Claude session),
ephemeral background workers ("claws"), and a federated view that lets a
single director coordinate across all of them.

The harness is the *tool*. Your labs are the *data*. They live in separate
directories. Updates to the harness never touch your lab content.

## Mental model

```
~/projects/studio/                ← THE LAB OS (this repo)
└── you pull updates here

~/your-lab/                       ← YOUR DATA (you create this)
├── surfaces/
├── systems/
├── research/investigations/
└── …

CGL_LAB_ROOT=~/your-lab cgl-tmux  ← run Studio against your lab
```

Same shape as `claude` itself: the tool is installed, your projects live
wherever you keep them, the tool reads from them via env vars or config.

## Install (preview — not yet wired)

```bash
git clone https://github.com/<owner>/studio ~/projects/studio
cd ~/projects/studio
./install.sh   # creates venv, prompts for CGL_LAB_ROOT, symlinks bin/
```

Then in a fresh terminal:

```bash
cgl-tmux
```

## Quickstart with the example lab

```bash
CGL_LAB_ROOT=~/projects/studio/examples/hello-lab cgl-tmux
```

This runs the harness against a clean template lab so you can see the Bridge
without using your own data.

## Multi-lab on one machine

State and tmux sessions auto-isolate by lab basename, so the same install
serves multiple labs:

```bash
CGL_LAB_ROOT=~/cairn-gate-labs/lab cgl-tmux  # one lab
CGL_LAB_ROOT=~/personal-labs       cgl-tmux  # another, parallel
```

## Concepts

- **Lab** — a folder. Holds surfaces, investigations, systems, and a `.intel/`
  directory the harness writes to.
- **Surface** — a public-facing output (e.g. a website page).
- **Investigation** — a research effort with a contract, cycles, and budget.
- **Systems** — internal infrastructure work.
- **Supervisor** — a persistent Claude session per lab. Resumeable via UUID.
- **Claw** — an ephemeral background Claude worker, runs in its own git
  worktree, merge-or-abandon when done.
- **Arm** — a long-lived parallel branch of a lab's work, also a worktree.
- **Spine** — the lab's reusable technique library: skills, runbooks, ADRs.

See [`docs/concepts.md`](docs/concepts.md) for the full taxonomy and
[`docs/lab-os.md`](docs/lab-os.md) for the target direction.

## Target architecture (lab OS)

Studio is moving toward a director-oriented lab OS — see
[`docs/specs/studio-lab-os-spec.md`](docs/specs/studio-lab-os-spec.md) for
the full architecture.

The `examples/hello-lab/` example now demonstrates the target shape: it includes
a `.studio/` control-plane (lab identity, orientations, roles, capabilities,
runtimes, promotion rules, sources) and a `.claws/` artifact bundle showing the
output contract a claw run should produce.

The v0 harness behavior (`cgl-tmux`, `cgl-labs`, `cgl-supervisor`, `cgl-claw`)
is unchanged — the new files are additive and do not affect running labs.

For a guided tour of hello-lab that explains how each file maps to the spec, see
[`docs/specs/walkthrough-hello-lab.md`](docs/specs/walkthrough-hello-lab.md).

## What this is NOT

- A general-purpose AI agent framework — it assumes Claude Code as the runtime.
- A workflow engine — there's no DAG, no scheduler, no retries. Long-running
  work is the supervisor's responsibility, not the harness's.
- A multi-tenant system — designed for a single director per machine.

## License

MIT — see [LICENSE](LICENSE).
