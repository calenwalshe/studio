# hello-lab

A teaching example for the Studio lab OS. It demonstrates the target architecture
in its simplest form — a minimal lab you can inspect to understand how the pieces
fit before you build your own.

## What it shows

hello-lab illustrates two layers of the lab OS:

1. **v0 directory shape** — the folders a lab uses: `surfaces/`, `research/investigations/`,
   `systems/`, `runbooks/`, `decisions/`, and `.claude/skills/`. These are the durable
   locations that a director promotes work into.

2. **`.studio/` control plane** — the file-backed configuration that governs how
   a lab operates: which roles are available, what capabilities each role has, which
   sources are in scope, and what the promotion gate requires.

3. **`.claws/<id>/` artifact bundle** — a hand-written fixture showing exactly what
   a completed claw run leaves behind: `meta.json`, `trace.jsonl`, `evidence.jsonl`,
   and `result.md`. The v0 harness does not yet emit these files automatically; they
   are contracts written ahead of implementation so the shape is clear.

## Reading map

Start with the control plane, then look at the artifact example:

| File | What it governs |
|------|----------------|
| `.studio/lab.toml` | Lab identity, kind, and path configuration |
| `.studio/orientations.toml` | Example director orientation — what the lab is pointed at and why |
| `.studio/roles.toml` | The six claw roles and their output contracts |
| `.studio/capabilities.toml` | What each capability profile permits (filesystem, network, shell, tools) |
| `.studio/runtimes.toml` | Available runtimes (`claude`, `claude -p`, future `codex`) |
| `.studio/promotion.toml` | Allowed promotion outcomes and required checks |
| `.studio/sources.toml` | Sources in scope for the example orientation |
| `.claws/20260501-150000-scout-hello-lab/` | A complete example artifact bundle |

The artifact bundle inside `.claws/` tells a single coherent story:
`meta.json` records what ran and what it recommends; `trace.jsonl` records each
action the claw took; `evidence.jsonl` holds the claims it extracted with
provenance; `result.md` is the human-readable summary the director reviews.

## The example orientation

`orientations.toml` defines one orientation with id `orient-hello-lab-studio-exploration`.
It points the lab at the Studio repo itself, with roles `scout`, `researcher`, and
`curator`, and stops for director review after the first spec. This is illustrative —
no claw has been spawned from it; the orientation file is the declaration of intent.

## What is a fixture

The `.claws/` directory contains a hand-written fixture: a complete example of what
a real claw run would produce. Treat it as a contract and a reading aid, not as
evidence from a real investigation. When the CLI to spawn role-based claws is
implemented (see "What's not implemented yet"), real runs will produce bundles in
this same shape.

## Launching the harness against hello-lab

The v0 harness behavior is unchanged. To open the Bridge against this example:

```bash
CGL_LAB_ROOT=$HARNESS/examples/hello-lab cgl-tmux
```

where `$HARNESS` is the Studio repo root (e.g. `~/projects/studio`).

## Further reading

- Full architecture: [`docs/specs/studio-lab-os-spec.md`](../../docs/specs/studio-lab-os-spec.md)
- Guided walkthrough of this lab: [`docs/specs/walkthrough-hello-lab.md`](../../docs/specs/walkthrough-hello-lab.md)
- Target direction framing: [`docs/lab-os.md`](../../docs/lab-os.md)
