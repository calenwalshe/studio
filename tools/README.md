# Studio Tools

Developer utilities for Studio Lab OS.

---

## `persona_driver.py`

LLM persona driver for headless Studio Cockpit testing.

Runs `CockpitApp` via Textual's `run_test()`, serializes the screen to plain text,
feeds it to a Claude subagent via `claude -p`, and loops until the persona calls
`done()` or `max_steps` is reached.

### Standalone usage

```bash
# Default goal against hello-lab (verbose — shows each step):
studio/.venv/bin/python tools/persona_driver.py --verbose

# Custom goal:
studio/.venv/bin/python tools/persona_driver.py \
    --goal "Check if any labs are stale or blocked. List their IDs." \
    --verbose

# Custom lab root:
studio/.venv/bin/python tools/persona_driver.py \
    --lab-root /path/to/my/lab \
    --goal "Summarize all labs and their statuses." \
    --verbose

# Quiet mode (just print final verdict):
studio/.venv/bin/python tools/persona_driver.py
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--goal "<text>"` | Find all labs that need review or are blocked. Report lab IDs and recommendations. | Natural-language goal for the persona |
| `--max-steps <n>` | 15 | Maximum interaction steps before giving up |
| `--lab-root <path>` | `examples/hello-lab` | Path to the federation root (resolved to absolute) |
| `--verbose` | off | Print each step's screen state and persona decision |

### What goals make sense to try

- "Find all labs that need review. Report each lab id and its promotion recommendation."
- "Check if any labs are stale or blocked. List their IDs and explain why."
- "Summarize the Director Queue. What is the top promotion candidate?"
- "What is the current status of hello-lab? What happened in its last claw run?"
- "Press r to refresh, then verify the table updates correctly."

### Exit codes

- `0` — verdict contains a success signal word (achieved, found, complete, done, identified, located)
- `1` — persona gave up, hit max steps, or returned a non-success verdict
- `2` — bad arguments (e.g. lab root not found)

### Pytest integration

Used by `tests/test_persona.py` (marked `@pytest.mark.slow`).

```python
from persona_driver import run_persona
from lab_tui.cockpit import CockpitApp

result = asyncio.run(run_persona(
    goal="Find all labs that need review.",
    app_class=CockpitApp,
    max_steps=8,
))
print(result["verdict"])
print(result["findings"])
```

### How it works

1. `run_persona()` opens the app with `CockpitApp().run_test(size=(120, 40))`.
2. Each step: `serialize_screen(app)` walks the widget tree and produces a plain-text
   snapshot (columns, rows, Director Queue content, active bindings).
3. `ask_persona()` calls `claude -p` with the screen text and recent history.
   The prompt constrains output to a single JSON object: either
   `{"action": "press_key", "key": "..."}` or
   `{"action": "done", "verdict": "...", "findings": [...]}`.
4. The loop presses the key or returns the findings.

### Requirements

- `claude` CLI on PATH (part of Claude Code)
- Textual 0.85+ (already in `studio/.venv`)
- No `ANTHROPIC_API_KEY` needed — uses subscription billing via `env -u ANTHROPIC_API_KEY`

---

## `persona_capture.py`

Widescreen capturing variant of `persona_driver.py`. Same LLM-driven interaction loop, but:

- Runs the TUI at **200 cols x 50 rows** (widescreen).
- After each step, calls `export_screenshot()` and saves `step-N.svg` + `step-N.png` (1600px wide via `cairosvg`).
- Writes a `manifest.json` recording the full run: goal, verdict, findings, and per-step screenshot paths + decisions.
- After the run, automatically invokes `persona_viewer/make_index.py` to update the viewer index.

### Standalone usage

```bash
studio/.venv/bin/python tools/persona_capture.py \
    --persona-slug power-user \
    --goal "Inspect the promotion candidates for hello-lab." \
    --max-steps 10 \
    --verbose
```

### Options

| Flag | Required | Default | Description |
|------|----------|---------|-------------|
| `--persona-slug <name>` | yes | — | Short identifier used in run_id and manifest |
| `--goal "<text>"` | yes | — | Natural-language goal for the persona |
| `--max-steps <n>` | no | 15 | Maximum interaction steps |
| `--lab-root <path>` | no | `examples/hello-lab` | Federation root directory |
| `--verbose` | no | off | Print each step's screen state and persona decision |

### Run output

Each run lands in `tools/persona_runs/<run_id>/` (format: `YYYYMMDD-HHMMSS-<slug>`):

```
tools/persona_runs/20260501-172052-power-user/
    step-0.svg
    step-0.png
    step-1.svg
    step-1.png
    ...
    manifest.json
```

Runs are gitignored as ephemeral data. One specific published run is committed for
reference — see `.gitignore` for the exception pattern.

### Requirements

- All requirements from `persona_driver.py`
- `cairosvg` — already installed in `studio/.venv`

---

## `persona_viewer/`

Static HTML viewer for browsing persona run transcripts with screenshots. No build step, no npm.

### Files

| File | Purpose |
|------|---------|
| `index.html` | Single-page app; loads runs from `runs.json` via `fetch()` |
| `runs.json` | Index of all runs; generated by `make_index.py` |
| `make_index.py` | Scans `tools/persona_runs/*/manifest.json` and writes `runs.json` |

### Viewing runs

Open `tools/persona_viewer/index.html` directly in a browser (if your browser allows local
`fetch()` from `file://`), or serve it:

```bash
# From the repo root:
cd tools/persona_viewer && python -m http.server 8787
# Then open: http://localhost:8787
```

The left sidebar lists all runs grouped by date, most recent first. Click a run to see:
- Header: persona slug, goal, verdict, step count, duration.
- Each step: persona decision (JSON) + TUI screenshot (PNG). Click a screenshot to enlarge.
- Findings section at the bottom.

### Regenerating the index

```bash
studio/.venv/bin/python tools/persona_viewer/make_index.py
```

Run this after any `persona_capture.py` run (it also runs automatically at the end of each capture).

---

## `persona_runs/`

Storage root for run artifacts. Path: `tools/persona_runs/`.

Gitignored by default (ephemeral). To commit a specific run for review, add an exception
to `.gitignore`:

```
tools/persona_runs/*
!tools/persona_runs/<run_id>/
```
