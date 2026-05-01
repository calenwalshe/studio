# hello-lab

A minimal example lab for Studio. Use it to verify your install:

```bash
CGL_LAB_ROOT=$HARNESS/examples/hello-lab cgl-tmux
```

(where `$HARNESS` is the Studio repo root, e.g. `~/projects/studio`)

## Structure

```
hello-lab/
├── surfaces/          public-facing labs (e.g. snake-surface example)
├── research/
│   └── investigations/   research labs
├── systems/           internal infra labs
├── runbooks/          spine: ops procedures
├── decisions/         spine: ADRs
├── intel/             director's intel layer (themes, snapshots)
└── .claude/
    └── skills/        spine: invocable skills
```

This dir is intentionally empty — Studio operates on it as a real lab. Use
`cgl-labs new <kind> <slug>` from the Bridge or shell to create your first
lab inside it.
