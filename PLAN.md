# Studio — Migration & Setup Plan

A director-multiplexed lab management harness on top of tmux + Claude Code.
This plan extracts the harness from the in-place CGL lab, makes it portable,
and ships v0.1 to GitHub.

---

## Vision

A *harness* that lives in its own repo and a *lab* (or many labs) that the
harness operates on. Same mental model as `claude` itself: the tool is
installed once, the data lives wherever the user keeps it.

```
~/projects/studio/                 ← THE HARNESS (this repo). Pull updates here.
├── bin/                              cgl-* primitives
├── studio/                           bridge, lab_tui, lib (Python source)
├── docs/                             concepts, ADRs, runbooks (generic)
├── examples/                         snake demo, hello-lab template
├── install.sh                        one-shot setup
├── README.md
└── PLAN.md                           (this file)

~/projects/cairn-gate-labs/lab/     ← USER DATA. Untouched by harness updates.
├── surfaces/
├── systems/
├── research/investigations/
├── intel/
├── decisions/
├── foundation/
└── …
```

Run `cgl-tmux` with `$CGL_LAB_ROOT` set → harness operates on that lab.
Multiple labs on one machine = multiple `CGL_LAB_ROOT` values, with state
auto-isolated per lab.

---

## Locked design decisions

| Decision | Choice | Why |
|---|---|---|
| Repo name | `studio` | Matches the spec's name; brand-neutral |
| License | MIT | Default, doesn't bind anything |
| Visibility | Public | Lets you fork-and-improve later |
| Disk path | `~/projects/studio/` | Sibling to other projects |
| Script prefix | `cgl-*` (kept) | Stylistic, no brand meaning. Avoids muscle-memory churn |
| Consumption pattern | PATH-only | studio is a tool, lab is data — like claude code |
| State isolation | Keyed by lab basename + `CGL_PROFILE` override | Multi-lab support without a profile concept yet |
| Tmux session name | `cgl-<basename>` (e.g. `cgl-cairn-gate-labs`) | Each lab gets its own session on the cgl socket |
| Studio in CGL? | NO. studio is a separate repo. | Updates to studio never touch CGL |

---

## What goes in / what stays out

### IN the studio repo
- `bin/cgl-*` primitives (currently in `~/bin/`, untracked anywhere)
- `studio/bridge/`, `studio/lab_tui/`, `studio/lib/` (Python TUI source —
  currently in `~/projects/cairn-gate-labs/lab/studio/`)
- `studio/SPEC.md`, `studio/BUILD_PLAN.md`, architecture diagrams
- `tmux/tmux.conf` — generic version of the cgl tmux config
- `docs/concepts.md` — lab / surface / investigation / arm / claw / spine
  taxonomy
- `docs/adrs/` — generic ADRs about the harness model
- `docs/runbooks/` — generic ops runbooks (publish-discipline, etc.)
- `examples/snake-surface/` — a complete demo lab
- `install.sh`, `README.md`, `LICENSE`

### NOT in studio (stays in CGL or is per-machine)
- All `surfaces/*/`, `systems/*/`, `research/investigations/*/` content
- `intel/` (CGL-specific state, briefings, focus reports)
- `decisions/0001-*.md` etc. (CGL-specific ADRs about Wyoming LLC, Meta
  employment, brand-first stealth)
- `foundation/`, `brand/`, `legal/`, `contacts/`, `team/`
- `.api-keys`, anything secret
- `~/.local/state/cgl/` (per-machine runtime state)
- `~/.claude/projects/` (supervisor session logs)
- `.intel/themes/<lab-slug>.jsonl` (vault data, per-lab)

---

## Migration checklist

Each item is bounded and committable. Pick them up at your pace.

### Phase 1 — repo skeleton (≈ 30 min)

- [ ] **1.1** `cd ~/projects/studio && git init`
- [ ] **1.2** Create empty top-level dirs: `bin/`, `studio/`, `docs/`,
      `examples/`, `tmux/`, `docs/adrs/`, `docs/runbooks/`
- [ ] **1.3** Add MIT `LICENSE`
- [ ] **1.4** Write minimal `README.md` — what / why / install / quickstart
      (placeholder fine for now; tighten later)
- [ ] **1.5** Add `.gitignore` — `*.pyc`, `__pycache__/`, `.venv/`,
      `.DS_Store`
- [ ] **1.6** Initial commit: "studio v0 — empty harness skeleton"

### Phase 2 — copy in the source (≈ 1h)

- [ ] **2.1** Copy `~/bin/cgl-tmux` → `studio/bin/cgl-tmux`
- [ ] **2.2** Copy `~/bin/cgl-bridge` → `studio/bin/cgl-bridge`
- [ ] **2.3** Copy `~/bin/cgl-supervisor` → `studio/bin/cgl-supervisor`
- [ ] **2.4** Copy `~/bin/cgl-claw` → `studio/bin/cgl-claw`
- [ ] **2.5** Copy `~/bin/cgl-arm` → `studio/bin/cgl-arm`
- [ ] **2.6** Copy `~/bin/cgl-labs` → `studio/bin/cgl-labs`
- [ ] **2.7** Copy `~/bin/cgl-tell` → `studio/bin/cgl-tell`
- [ ] **2.8** Copy `~/bin/cgl-focus` → `studio/bin/cgl-focus`
- [ ] **2.9** Copy `~/bin/cgl-themes` → `studio/bin/cgl-themes`
- [ ] **2.10** Copy `~/bin/cgl-lab` → `studio/bin/cgl-lab` (the launcher,
      different from `cgl-labs`)
- [ ] **2.11** Copy `~/bin/cgl-diagram-add` → `studio/bin/cgl-diagram-add`
- [ ] **2.12** Copy `~/projects/cairn-gate-labs/lab/studio/bridge/`,
      `lab_tui/`, `lib/` → `studio/studio/`
- [ ] **2.13** Copy `studio/SPEC.md`, `BUILD_PLAN.md`, `studio-flow.mmd`,
      `tui-architecture.mmd` → `studio/studio/`
- [ ] **2.14** Copy `lab/.tmux.conf` → `studio/tmux/tmux.conf` (will get
      genericized in Phase 3)
- [ ] **2.15** Commit: "studio v0 — copy raw source, pre-genericization"

### Phase 3 — strip personal data, parameterize paths (≈ 1h)

For each file in `studio/bin/` and `studio/studio/`:

- [ ] **3.1** Replace any hardcoded `/home/agent/projects/cairn-gate-labs/lab`
      → use env `$CGL_LAB_ROOT` (most scripts already do this; verify)
- [ ] **3.2** Replace any hardcoded `/home/agent/` → `$HOME`
- [ ] **3.3** Replace any hardcoded `/home/agent/.local/state/cgl/` →
      `${XDG_STATE_HOME:-$HOME/.local/state}/cgl/<lab-slug>/`
- [ ] **3.4** Where state files exist (`panes.json`, `supervisors.json`),
      key them by `<lab-basename>` derived from `$CGL_LAB_ROOT`. Override
      with `$CGL_PROFILE` if set.
- [ ] **3.5** Tmux session name in `cgl-tmux`: `cgl-${CGL_PROFILE:-$lab_basename}`
      instead of hardcoded `cgl`. Socket stays `-L cgl`.
- [ ] **3.6** Replace any "Cairn Gate Labs" text in titles/banners with
      `${CGL_LAB_TITLE:-$lab_basename}`
- [ ] **3.7** Strip CGL-specific runbook references (e.g. meta-ads-pipeline
      mentions in scripts; the runbook itself is CGL data)
- [ ] **3.8** Run `grep -rE 'cairn|CGL_PROFILE|home/agent' studio/` —
      should return nothing CGL-specific
- [ ] **3.9** Commit: "studio v0 — parameterize paths, strip CGL specifics"

### Phase 4 — generic docs (≈ 45 min)

- [ ] **4.1** Write `docs/concepts.md` — lab kinds (surface, investigation,
      systems), arms, claws, spine, supervisors, claws-vs-arms distinction
- [ ] **4.2** Write `docs/architecture.md` — the studio model: persistent
      state vs attended session vs ephemeral exec vs bellclaw vs cron
- [ ] **4.3** Copy `lab/studio/studio-flow.mmd` and `tui-architecture.mmd`
      to `docs/diagrams/` (or keep in `studio/studio/` — pick one)
- [ ] **4.4** Identify which CGL ADRs are *generic* (lab-as-process,
      worktree pattern, claw-runs-in-ephemeral-worktree) vs *CGL-specific*
      (founding structure, brand-first stealth). Copy the generic ones to
      `docs/adrs/` and rewrite to remove CGL references.
- [ ] **4.5** Write `docs/runbooks/publish-discipline.md` and any other
      generic runbooks. Skip CGL-specific ones (Meta ads pipeline, etc).
- [ ] **4.6** Commit: "studio v0 — generic docs"

### Phase 5 — install.sh (≈ 30 min)

- [ ] **5.1** Write `install.sh`:
      1. Create `studio/.venv/`, install `textual`
      2. Prompt for `CGL_LAB_ROOT` (or accept as arg) — must be an
         existing directory
      3. Write `~/.config/cgl/config.toml` with `lab_root = "..."`
      4. Symlink `studio/bin/*` into `$HOME/bin/` (or `~/.local/bin/`,
         whichever is on PATH)
      5. Print next-steps message: "Run `cgl-tmux` from a fresh terminal."
- [ ] **5.2** Make scripts read config in this priority order:
      1. CLI flag (e.g. `--lab-root`)
      2. Env var (`CGL_LAB_ROOT`)
      3. Config file (`~/.config/cgl/config.toml`)
- [ ] **5.3** Commit: "studio v0 — install.sh"

### Phase 6 — example lab (≈ 30 min)

- [ ] **6.1** Create `examples/hello-lab/` with the canonical lab dir
      structure: `surfaces/`, `systems/`, `research/investigations/`,
      `runbooks/`, `decisions/`, `intel/`, `.claude/skills/`,
      `.tmux.conf`, README explaining it's a clean template
- [ ] **6.2** Create `examples/snake-surface/` — a copy of the snake
      surface (just the `index.html` + README) to demo a surface lab
- [ ] **6.3** Update `README.md` quickstart to point at `examples/hello-lab/`
- [ ] **6.4** Commit: "studio v0 — example labs"

### Phase 7 — smoke test on a fresh "lab" (≈ 30 min)

- [ ] **7.1** From a clean shell:
      `CGL_LAB_ROOT=~/projects/studio/examples/hello-lab cgl-tmux`
- [ ] **7.2** Verify Bridge launches, federation view renders, no errors
      referencing CGL paths
- [ ] **7.3** Press `N` to create a new lab; verify it lands in
      `examples/hello-lab/surfaces/<slug>/`
- [ ] **7.4** Press `2` to activate it; verify supervisor spawns in the
      example lab's worktree
- [ ] **7.5** Document any glitches in this PLAN.md, fix or list as TODOs
- [ ] **7.6** Commit: "studio v0 — smoke test passes"

### Phase 8 — push to GitHub (≈ 15 min)

- [ ] **8.1** `gh repo create cgl-harness/studio --public` (or whatever
      org/user) — pick public visibility
- [ ] **8.2** `git remote add origin <url> && git push -u origin main`
- [ ] **8.3** Tag `v0.1`
- [ ] **8.4** Write a short release note: "v0.1 — initial harness skeleton.
      Bridge TUI, claws, arms, themes pipeline. Single-lab support; multi-
      lab via env vars and basename keying. Experimental."

### Phase 9 — migrate CGL to consume studio (≈ 30 min)

- [ ] **9.1** In the CGL lab repo: `git rm -r lab/studio/bridge/
      lab/studio/lab_tui/ lab/studio/lib/`. Keep SPEC.md, BUILD_PLAN.md,
      diagrams (those are CGL-specific reflections on what we built).
- [ ] **9.2** Add a `lab/studio/.gitignore` line ignoring `.venv/`
- [ ] **9.3** Commit: "studio: extract harness to ~/projects/studio/"
- [ ] **9.4** Update shell rc so `~/projects/studio/bin/` is on PATH and
      `CGL_LAB_ROOT=~/projects/cairn-gate-labs/lab` is exported
- [ ] **9.5** Verify `cgl-tmux` still works for CGL — same flow as before,
      just now coming from the harness install
- [ ] **9.6** Commit/document the new shell rc setup

---

## Multi-lab pattern (the goal-state)

Once the above is done, on any machine:

```bash
# In ~/.bashrc or ~/.zshrc
export PATH=$HOME/projects/studio/bin:$PATH

# Per-shell: which lab am I working on?
export CGL_LAB_ROOT=~/projects/cairn-gate-labs/lab    # CGL
# or:
export CGL_LAB_ROOT=~/personal-labs                   # personal stuff
# or:
CGL_LAB_ROOT=~/sidegig/lab cgl-tmux                   # one-off

# State auto-isolates by lab basename:
#   ~/.local/state/cgl/cairn-gate-labs/panes.json
#   ~/.local/state/cgl/personal-labs/panes.json
#   ~/.local/state/cgl/lab/panes.json   (sidegig — collision risk; use CGL_PROFILE)

# Tmux sessions auto-isolate too:
#   tmux -L cgl ls →
#     cgl-cairn-gate-labs
#     cgl-personal-labs
#     cgl-lab
```

For collision-free naming when basenames clash:
```bash
CGL_PROFILE=sidegig CGL_LAB_ROOT=~/sidegig/lab cgl-tmux
# → tmux session: cgl-sidegig
# → state dir:    ~/.local/state/cgl/sidegig/
```

---

## Open follow-ups (post v0.1)

- Profile concept formalized via `~/.config/cgl/profiles/<name>.toml`
- `cgl-tmux --profile sidegig` instead of env var juggling
- `studio update` command that pulls + verifies the harness without
  affecting the lab
- Submodule pattern as an alternative for users who want studio version
  pinned per-lab
- `studio doctor` command to diagnose install state
- A neutral `~/projects/studio/examples/` walkthrough — readable as a
  story, not just a code dump
- ADR about why we picked PATH-only over submodule

---

## Status log

Update this section as you grind through the checklist.

| Date | Phase | Notes |
|---|---|---|
| 2026-04-30 | plan written | Locked design decisions; checklist drafted |
