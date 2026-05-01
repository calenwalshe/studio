---
surface: snake
code: SNK
status: active
last_reviewed: 2026-04-29
---

# Snake (SNK)

A playable browser snake game, deployed at cairnlabs.org/snake.

This surface exists to **dogfood the cairn-gate-labs studio TUI** — the first end-to-end run where the director (top-left pane) hands a mission to a per-lab supervisor (bottom-right pane), and the supervisor builds + deploys without further direction.

## Mission

Build a snake game playable in any modern browser. Single self-contained `index.html` that includes its own CSS and JS. Deploy it under `web/cairnlabs.org/snake/` so the existing webmaster deploy path picks it up.

## Quality bar

- Loads at `https://cairnlabs.org/snake/` and renders within 1s
- Playable with arrow keys (and WASD as bonus)
- Snake grows on eating food
- Dies on self-collision and wall-collision (or wraps — design choice)
- Score visible somewhere
- No external CDN dependencies (offline-friendly)

## Out of scope (for v1)

- High-score persistence (localStorage is fine if cheap, skip if not)
- Mobile touch controls
- Multi-player or networking
- Fancy graphics — classic green-on-black is fine

## Deploy path

`web/cairnlabs.org/snake/index.html` (and any companion files) — Caddy auto-syncs to the served path via the `caddy-deploy.sh` PostToolUse hook. Verify by hitting the URL after writes.
