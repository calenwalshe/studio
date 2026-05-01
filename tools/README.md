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
