# snake-surface — example

A complete example surface lab. Demonstrates the structure Studio expects
for a surface that produces a deployable artifact.

## What's here

```
snake-surface/
├── surfaces/snake/README.md        the lab's mission + quality bar
└── web/snake/index.html            the deliverable (a playable browser game)
```

The README in `surfaces/snake/` is the lab's **contract**: what it's trying
to deliver, the quality bar, what's out of scope. Studio reads the
frontmatter for kind/status; supervisors read the body to know what to do.

## Try it

```bash
CGL_LAB_ROOT=$HARNESS/examples/snake-surface cgl-tmux
```

In the Bridge, the lab list will show one entry: `surface/snake`. Activate
it (press `2`, or arrow + Enter on the federation row) and the supervisor
will spawn against `surfaces/snake/`.

## Story

This was the first end-to-end surface lab built using Studio. Three claws
shipped it (border, rainbow title, attribution link). The build run is
referenced in Studio's docs as the canonical "director → supervisor → claw"
demo.
