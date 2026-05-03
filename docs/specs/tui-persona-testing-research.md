# TUI Persona Testing — Research Report

> Scope: automated/persona-driven testing options for Studio Cockpit (Textual, Python 3.12)
> Audience: Studio lead developer
> Date: 2026-05-01

---

## TL;DR

The fastest win is combining what already works — Textual's `run_test()` / Pilot — with `pytest-textual-snapshot` for visual regression. That covers regression catching and takes about half a day to wire in. For behavioral/UX testing (does the persona accomplish a goal?), the best approach is a thin Python wrapper around `run_test()` that serializes screen state to text, then passes it to a Claude subagent via `claude -p`. The subagent decides what key to press next. `textual-mcp-server` (released 2026-02-17) is a drop-in MCP layer that does exactly this interface extraction and is worth evaluating immediately — it was purpose-built for LLM-driven Textual testing. VHS (Charm) is the right choice for shareable demo artifacts and reviewer walkthroughs, not for assertions.

---

## Option Matrix

| Approach | Setup cost | Cost per test | Catches | Reproducible | Works with pytest | CI-able |
|---|---|---|---|---|---|---|
| 1. Textual Pilot scripts | Low (already working) | Very low | Behavioral regressions, key flows, widget state | Yes, deterministic | Yes | Yes |
| 2. pytest-textual-snapshot | Low (one pip install) | Low | Visual regressions (pixel-diff SVG) | Yes | Yes | Yes, artifacts attachable |
| 3. Claude-as-persona (custom loop) | Medium (2-3 hrs) | Medium (API tokens per run) | UX flow validity, design coherence, "would a director get stuck here?" | Partially (LLM non-determinism) | With wrapper | Yes, headless |
| 4. textual-mcp-server + Claude subagent | Low-medium (MCP config) | Medium (API tokens per run) | Same as above, plus structured widget queries | Partially | Via subprocess | Yes |
| 5. VHS tape files | Medium (install Go tool, write tape) | Low | Demo correctness, visual walkthroughs | Yes (scripted) | No (standalone) | Yes (CI output = GIF/MP4/ASCII) |
| 6. tmux + libtmux loop | High (process management, ANSI strip) | Low | Integration-level (sees real terminal output) | Yes | Via subprocess | Yes, brittle |

---

## Detailed Write-Up Per Option

### Option 1: Textual Pilot scripts (pytest-driven scenarios)

**What it is:** Textual's built-in headless test runner. `App.run_test()` is an async context manager returning a `Pilot` object. You press keys, click widgets, await state, then assert.

**How it works mechanically:**

```python
import pytest
import os
from textual.pilot import Pilot

@pytest.mark.asyncio
async def test_cockpit_shows_hello_lab(tmp_path):
    os.environ["CGL_LAB_ROOT"] = str(Path("examples/hello-lab").resolve())
    from studio.lab_tui.cockpit import CockpitApp
    async with CockpitApp().run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        table = pilot.app.query_one("#lab-table")
        # Row cursor is on first row by default
        assert pilot.app._summaries[0].lab_id == "hello-lab"
        await pilot.press("enter")
        await pilot.pause()
        # assert notification appeared — check via app.log or query Notification widget
```

Reading screen state without snapshot: `pilot.app.query_one("#lab-table")` gives you the live DataTable widget. Call `.get_row_at(0)` or inspect `._summaries` directly. For text in a Static widget, use `.renderable` (returns a Rich Text object) or `.query_one(Static).render()`. Full SVG dump: `pilot.app.export_screenshot()` — returns SVG string.

**Strengths:** Zero extra dependencies beyond what's already in the venv. Fully deterministic. Runs in milliseconds. Directly exercises the actual Python code path. `query_one` and `query` work on live widgets — you can read DataTable row values, check Static content, verify footer bindings.

**Weaknesses:** Cannot answer "is the UX confusing?" — it only asserts what the developer explicitly programmed to check. Screen-as-text is clunky (SVG, not plain text). Writing journey tests is verbose.

**Concrete first step:** Write `tests/test_cockpit_pilot.py` with one test: launch the app, `await pilot.pause()`, assert `len(app._summaries) == 1`. Run: `CGL_LAB_ROOT=examples/hello-lab studio/.venv/bin/pytest tests/test_cockpit_pilot.py -v`.

---

### Option 2: pytest-textual-snapshot

**What it is:** Official Textualize pytest plugin. Captures an SVG screenshot after interactions and compares to a saved baseline. Built on `syrupy`. Textual's own test suite uses this internally.

**How it works mechanically:**

```python
# tests/test_cockpit_snapshot.py
import os
from pathlib import Path

def test_cockpit_federation_home(snap_compare):
    os.environ["CGL_LAB_ROOT"] = str(Path("examples/hello-lab").resolve())
    from studio.lab_tui.cockpit import CockpitApp
    assert snap_compare(CockpitApp(), terminal_size=(120, 40))

def test_cockpit_after_enter(snap_compare):
    os.environ["CGL_LAB_ROOT"] = str(Path("examples/hello-lab").resolve())
    from studio.lab_tui.cockpit import CockpitApp

    async def press_enter(pilot):
        await pilot.press("enter")
        await pilot.pause()

    assert snap_compare(CockpitApp(), terminal_size=(120, 40), run_before=press_enter)
```

First run with `--snapshot-update` generates SVG baselines under `tests/__snapshots__/`. Subsequent runs fail if the rendered output changes. Install: `studio/.venv/bin/pip install pytest-textual-snapshot`.

**Strengths:** Catches layout regressions automatically — if a widget moves, a border changes color, or a column disappears, the test fails. SVG diffs are human-readable in browsers. No coding required per regression — just add new screens to the snapshot set. Integrates with the existing pytest run.

**Weaknesses:** SVG comparison is brittle to whitespace and font rendering differences across machines. Every intentional layout change requires `--snapshot-update` (minor friction). Does not verify semantics — a blank screen would pass if it was the baseline.

**Concrete first step:** `pip install pytest-textual-snapshot`, write one `snap_compare` test for the Federation Home, run with `--snapshot-update` to create the baseline, commit the SVG under `tests/__snapshots__/`.

---

### Option 3: Claude-as-persona (custom interaction loop)

**What it is:** A Python script that runs the Textual app headlessly, serializes the current screen state as text, feeds it to a Claude subagent with a director persona prompt, receives a key decision, presses it, and loops. The agent reports whether it accomplished its stated goal.

**How it works mechanically:**

The interface layer (the part you build, ~100 lines):

```python
# tools/persona_driver.py
import asyncio, os, subprocess, json, sys
from pathlib import Path
from textual.pilot import Pilot

os.environ["CGL_LAB_ROOT"] = str(Path("examples/hello-lab").resolve())
sys.path.insert(0, str(Path(__file__).parents[1] / "studio"))
from lab_tui.cockpit import CockpitApp

def screen_to_text(app) -> str:
    """Extract readable state from the live app."""
    lines = []
    # Widget tree summary
    for w in app.screen.walk_children():
        cls = type(w).__name__
        wid = f"#{w.id}" if w.id else ""
        if cls == "DataTable":
            rows = [app.query_one("#lab-table").get_row_at(i)
                    for i in range(w.row_count)]
            lines.append(f"DataTable{wid}: {len(rows)} rows")
            for r in rows:
                lines.append(f"  row: {r}")
        elif cls == "Static":
            lines.append(f"Static{wid}: {str(w.renderable)[:120]}")
        elif cls in ("Header", "Footer"):
            lines.append(f"{cls}: {w.render()!s:.80}")
    lines.append(f"Active bindings: {[b.key for b in app.screen.active_bindings.values()]}")
    return "\n".join(lines)

async def persona_loop(goal: str, max_steps: int = 10):
    history = []
    async with CockpitApp().run_test(size=(120, 40)) as pilot:
        for step in range(max_steps):
            state = screen_to_text(pilot.app)
            prompt = build_prompt(goal, state, history)
            response = call_claude(prompt)   # env -u ANTHROPIC_API_KEY claude -p
            action = parse_action(response)  # {"key": "enter"} or {"done": true, "verdict": "..."}
            history.append({"state_summary": state[:300], "action": action})
            if action.get("done"):
                return action["verdict"], history
            await pilot.press(action["key"])
            await pilot.pause()
    return "max_steps_reached", history
```

The Claude call uses `env -u ANTHROPIC_API_KEY claude -p` with a structured prompt asking for JSON output: either `{"key": "q"}` or `{"done": true, "verdict": "goal achieved: saw hello-lab with needs_review status"}`.

**Strengths:** Answers design questions, not just regression questions. The persona notices when things are ambiguous or confusing. Reports natural-language findings. Can be asked to try multiple paths. Maps directly to how the developer thinks about the TUI ("would a director know what to do here?").

**Weaknesses:** Non-deterministic — LLM may navigate differently across runs. Token cost per run ($0.01–$0.05 with Sonnet). Slower than pure pytest (3–15 seconds per run). The `screen_to_text` bridge is custom work that needs maintenance as the app grows.

**Concrete first step:** Write the 100-line `tools/persona_driver.py` bridge, run it once against the hello-lab fixture. Print the verdict and history to stdout. No assertions needed yet — just observe whether the persona navigates correctly.

---

### Option 4: textual-mcp-server + Claude subagent

**What it is:** A pre-built MCP server (released 2026-02-17, v1.0.0, beta) that wraps Textual's Pilot API and exposes it as MCP tools. A Claude subagent configured with this MCP server can call `textual_launch`, `textual_snapshot`, `textual_press`, `textual_query`, and `textual_stop` directly.

**How it works mechanically:**

Install and configure:
```bash
pip install textual-mcp-server
```

MCP config entry (in `.claude/settings.json` `mcpServers`):
```json
{
  "textual": {
    "command": "textual-mcp",
    "args": []
  }
}
```

The `textual_snapshot` tool returns the widget tree with `[ref=N]` markers and focus state as plain text — readable by the LLM without custom serialization. `textual_query` takes a CSS selector and returns widget properties. `textual_screenshot` returns SVG.

A persona test as a Claude subagent prompt:
```
You are a director testing the Studio Cockpit TUI.
Goal: Determine which labs need review and what the recommended action is.

Tools available: textual_launch, textual_snapshot, textual_press, textual_query, textual_stop.

1. Launch the app: textual_launch("studio/lab_tui/cockpit.py")
   (env: CGL_LAB_ROOT=examples/hello-lab)
2. Call textual_snapshot to see what's on screen.
3. Navigate and read the Director Queue pane.
4. Report your findings as JSON: {"labs_needing_review": [...], "verdict": "..."}
5. Call textual_stop.
```

**Strengths:** The hardest part (screen serialization) is already built and maintained. `[ref=N]` markers let the LLM click/interact without knowing coordinates. Works with Claude Code's existing MCP infrastructure. The same MCP server can be reused for future screens (Lab Focus, Promotion Review) with zero extra serialization code.

**Weaknesses:** Extra dependency (MCP server process). Beta software — API may shift. The subagent call overhead is higher than a direct `claude -p` loop. MCP tool availability in subagents has known friction in Claude Code (GitHub issue #13605 as of early 2026).

**Concrete first step:** `pip install textual-mcp-server`, add the MCP server config, verify `textual_snapshot` output by calling it manually via the MCP inspector, then write a persona prompt as a skill or inline subagent call.

---

### Option 5: VHS tape files

**What it is:** Charm's VHS records terminal sessions from a `.tape` script into GIF, MP4, WebM, or ASCII/text output. You write a declarative script of keystrokes and timing; VHS plays it back in a virtual terminal.

**How it works mechanically:**

```tape
# cockpit-demo.tape
Output docs/demo/cockpit.gif
Output docs/demo/cockpit.txt

Set Shell "bash"
Set FontSize 14
Set Width 1200
Set Height 600

Env CGL_LAB_ROOT "examples/hello-lab"
Type "bin/cgl-cockpit"
Enter
Sleep 2s

# Navigate table
Down
Sleep 300ms
Down
Sleep 300ms
Enter
Sleep 1s

# Quit
Type "q"
Sleep 500ms
```

Run: `vhs cockpit-demo.tape`. The `.txt` output is terminal-captured text that can be stored as a golden file and diffed in CI.

**Strengths:** Produces shareable GIF/MP4 artifacts that non-developer reviewers (designer, PM) can watch. `.txt` output enables golden-file regression testing without pytest. The `.tape` format is readable and version-controlled.

**Weaknesses:** VHS is not installed on this system and requires a Go toolchain or binary download. The virtual terminal VHS uses is independent of Textual's headless driver — you are testing the real launched binary, not the in-process app. Timing-based (`Sleep`) rather than event-driven — flaky on slow machines. No structured assertions; failure detection is limited to golden-file diff or visual review.

**Concrete first step:** Install VHS (`go install github.com/charmbracelet/vhs@latest` or download binary). Write a 15-line `.tape` file for the cockpit. Run it, examine the `.txt` output, store it as a golden file in `tests/golden/cockpit.txt`.

---

### Option 6: tmux + libtmux loop

**What it is:** Launch the TUI in a tmux pane, use `libtmux` (Python API for tmux) to send keystrokes with `pane.send_keys()` and read terminal output with `pane.capture_pane()`, then strip ANSI codes and assert on the text.

**How it works mechanically:**

```python
import libtmux, time, re

server = libtmux.Server()
session = server.new_session(session_name="test-cockpit")
pane = session.active_window.active_pane
pane.send_keys("CGL_LAB_ROOT=examples/hello-lab bin/cgl-cockpit", enter=True)
time.sleep(2)
output = "\n".join(pane.capture_pane())
clean = re.sub(r'\x1b\[[0-9;]*m', '', output)
assert "hello-lab" in clean
pane.send_keys("q", enter=False)
session.kill_session()
```

**Strengths:** Tests the real binary end-to-end. Sees what a human sees. Language-agnostic — works for any TUI regardless of framework.

**Weaknesses:** Highest setup complexity (tmux dependency, session management, ANSI stripping). Timing-based waits are inherently flaky. The capture-pane approach sees rendered terminal output, not widget state — partial-line rendering issues are common. Requires tmux to be running (not always true in CI). Not integrated with pytest without significant glue.

**Concrete first step:** Only pursue this if you need to test the binary as shipped (e.g., post-install acceptance test). For development iteration, Options 1–4 are strictly better.

---

## Specific Recommendation for This Developer

### One-day setup

**Goal:** Stop clicking manually, catch regressions, get a basic persona loop working.

1. **Morning (2 hours):** Add `pytest-textual-snapshot`.
   - `studio/.venv/bin/pip install pytest-textual-snapshot`
   - Write `tests/test_cockpit_snapshot.py` with two `snap_compare` tests: Federation Home at rest, and after pressing `enter`.
   - Run `--snapshot-update` to generate baselines, commit the SVGs.
   - Now every `pytest` run catches layout regressions automatically.

2. **Afternoon (2–3 hours):** Build the persona driver.
   - Write `tools/persona_driver.py` (~100 lines) using the Option 3 pattern above.
   - Hard-code one goal: "Find which labs need review."
   - Print the step-by-step history and verdict to stdout.
   - Run it: `studio/.venv/bin/python tools/persona_driver.py`.
   - No assertions needed yet — just verify the loop works and the persona reports something sensible.

End of day: you have visual regression coverage and a working persona loop you can run on demand.

### One-week setup

**Goal:** Full persona testing pipeline, CI integration, multi-screen coverage.

- **Day 1–2:** As above.
- **Day 2–3:** Evaluate `textual-mcp-server`. Install, configure, run `textual_snapshot` against the cockpit, compare its widget-tree output to your custom `screen_to_text`. If the MCP output is sufficient, replace your custom serializer with it. This reduces ongoing maintenance.
- **Day 3–4:** As new screens land (Lab Focus, Promotion Review), write one `snap_compare` test per screen. Add one persona scenario per screen — the persona goal maps directly to the screen's purpose from the spec.
- **Day 4–5:** Wire persona tests into CI. The persona driver runs headlessly (no display needed — Textual's headless driver is already used). Add a `pytest` fixture that calls the persona driver as a subprocess and asserts the returned verdict contains "achieved". Budget 30–60 seconds per persona run in CI.
- **Day 5:** Write one VHS tape file for the most important demo path (Federation Home → Lab Focus → Promotion Review). Commit the GIF to `docs/demo/`. Send it to reviewers instead of asking them to run the TUI.

---

## Worked Example: "What's Blocked?" Persona Test

### Persona prompt / instructions

```
You are a Studio director. You have just opened the Studio Cockpit.
Your goal: Identify all labs that need review or are blocked, and determine
what the recommended next action is for each.

You have access to these tools:
- get_screen_state() -> str: returns the current widget tree as text
- press_key(key: str): presses a key (q, r, enter, j, k, up, down)
- done(verdict: str, findings: list[dict]): call this when you have enough
  information to answer the goal, or when you are stuck.

Rules:
- Do not quit the app until you have inspected the Director Queue pane.
- If you do not recognize a widget, press 'r' to refresh and try again.
- Maximum 15 steps.
- Output only valid JSON: {"action": "press_key", "key": "..."} or
  {"action": "done", "verdict": "...", "findings": [...]}
```

### Interaction loop

```
Step 1: get_screen_state()
Output:
  Header: "Studio Cockpit — hello-lab"
  DataTable#lab-table: 1 row
    row: ('!', 'hello-lab', 'research', 'Investigate Studio TUI options', '1', '1')
  Static#queue-pane: "hello-lab: 20260501-150000-scout-hello-lab: keep_evidence"
  Footer: bindings=[q, r, enter]

Persona decision: {"action": "done",
  "verdict": "goal achieved",
  "findings": [{"lab": "hello-lab", "status": "needs_review",
    "queue_item": "20260501-150000-scout-hello-lab",
    "recommendation": "keep_evidence",
    "suggested_action": "Review promotion candidate in Promotion Review screen"}]}
```

In this case the persona completes in 1 step because the Federation Home exposes all the needed information immediately. A more complex scenario would navigate to Lab Focus, inspect evidence, and return.

### What the test asserts

```python
# tests/test_persona_blocked_labs.py
def test_persona_finds_blocked_labs():
    verdict, findings = run_persona(
        goal="Find all labs needing review or blocked. Report lab IDs and recommendations.",
        max_steps=10
    )
    assert verdict == "goal achieved", f"Persona failed: {verdict}"
    lab_ids = [f["lab"] for f in findings]
    assert "hello-lab" in lab_ids
    recs = [f["recommendation"] for f in findings]
    assert any(r not in ("abandon", "dry_run") for r in recs)
```

The test fails if: (a) the persona couldn't navigate to the right information within 10 steps, (b) the persona declared success but missed the lab, or (c) the app crashed.

### Build time estimate

| Component | Time |
|---|---|
| `persona_driver.py` core loop | 2 hours |
| `screen_to_text()` for current cockpit widgets | 1 hour |
| Claude prompt tuning (get JSON output reliably) | 1 hour |
| `test_persona_blocked_labs.py` assertions | 30 minutes |
| **Total** | **~4.5 hours** |

With `textual-mcp-server` handling the serialization, the `screen_to_text` step drops to near zero — reducing total time to ~2.5 hours.

---

## Sources Consulted

- [Textual Testing Guide](https://textual.textualize.io/guide/testing/)
- [pytest-textual-snapshot GitHub](https://github.com/Textualize/pytest-textual-snapshot)
- [pytest-textual-snapshot PyPI](https://pypi.org/project/pytest-textual-snapshot/)
- [textual-mcp-server PyPI](https://pypi.org/project/textual-mcp-server/)
- [textual-mcp-server on Lobe Hub](https://lobehub.com/mcp/discohead-textual-mcp-server)
- [VHS by charmbracelet](https://github.com/charmbracelet/vhs)
- [Textology (Textual testing extensions)](https://github.com/pyranha-labs/textology)
- [libtmux Python API for tmux](https://pypi.org/project/libtmux/)
- [Textual Pilot API](https://textual.textualize.io/api/pilot/)
- Textual v0.85.2 source: `/home/agent/projects/studio-tui/studio/.venv/lib/python3.12/site-packages/textual/`
