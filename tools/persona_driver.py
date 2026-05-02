"""tools/persona_driver.py — LLM persona driver for Studio Cockpit TUI testing.

Runs the CockpitApp headlessly via Textual's run_test(), serializes screen
state to plain text, feeds it to a Claude subagent via `claude -p`, and loops
until the persona declares done() or max_steps is reached.

Standalone usage:
    CGL_LAB_ROOT=examples/hello-lab studio/.venv/bin/python tools/persona_driver.py --verbose

Pytest usage: imported by tests/test_persona.py.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Screen serializer
# ---------------------------------------------------------------------------

def _strip_rich_markup(text: str) -> str:
    """Remove Rich markup tags like [bold], [dim], [/dim], etc."""
    return re.sub(r'\[/?[^\[\]]*\]', '', str(text)).strip()


def serialize_screen(app) -> str:
    """Turn the live Textual app into a director-readable text snapshot.

    Returns plain text (~30-50 lines) with one section per meaningful widget.
    Avoids Rich markup — plain text is what the LLM reads best.
    """
    lines: list[str] = []

    # App title / subtitle
    title = getattr(app, 'title', '') or ''
    subtitle = getattr(app, 'sub_title', '') or ''
    lines.append(f"=== Studio Cockpit ===")
    lines.append(f"Title: {title}")
    if subtitle:
        lines.append(f"Subtitle: {subtitle}")
    lines.append("")

    # Walk the widget tree
    try:
        for widget in app.screen.walk_children():
            cls_name = type(widget).__name__

            if cls_name == "LabList":
                wid = f"#{widget.id}" if widget.id else ""
                lines.append(f"LabList{wid}:")
                try:
                    rows = list(widget.query("LabRow"))
                    lines.append(f"  Labs ({len(rows)} total):")
                    for i, row in enumerate(rows):
                        try:
                            summary = row._summary
                            from lab_tui.cockpit import _symbol, _orientation_summary
                            sym = _symbol(summary.status)
                            short_obj = _orientation_summary(summary)
                            expanded_mark = " [expanded]" if row.expanded else ""
                            focus_mark = " <-- focused" if row.has_focus else ""
                            lines.append(
                                f"    [{i}] {sym} {summary.lab_id} | {summary.kind} | "
                                f"{short_obj} | claws={len(summary.bundles)} "
                                f"promo={summary.promotion_candidates}"
                                f"{expanded_mark}{focus_mark}"
                            )
                            if row.expanded:
                                # Show first few lines of expansion body
                                body_static = row.query_one(".lab-row-body")
                                body_text = _strip_rich_markup(str(body_static.renderable))
                                for bline in body_text.splitlines()[:10]:
                                    if bline.strip():
                                        lines.append(f"      {bline}")
                        except Exception:
                            lines.append(f"    [{i}] (unreadable)")
                except Exception:
                    lines.append("  (rows unavailable)")
                lines.append("")

            elif cls_name == "LabHeaderStrip":
                wid = f"#{widget.id}" if widget.id else ""
                try:
                    content = _strip_rich_markup(str(widget.renderable))
                    if content:
                        lines.append(f"LabHeader{wid}: {content[:120]}")
                except Exception:
                    pass

            elif cls_name == "DirectorChat":
                wid = f"#{widget.id}" if widget.id else ""
                lines.append(f"DirectorChat{wid}:")
                try:
                    transcript = widget.get_transcript_text()
                    for line in transcript.splitlines()[:30]:
                        lines.append(f"  {line}")
                    # Note state
                    thinking = getattr(widget, "_thinking", False)
                    if thinking:
                        lines.append("  [status: thinking...]")
                    else:
                        lines.append("  [status: ready — input field active]")
                except Exception as exc:
                    lines.append(f"  (unreadable: {exc})")
                lines.append("")

            elif cls_name == "Static":
                wid = f"#{widget.id}" if widget.id else ""
                # Skip generic/unnamed statics that are likely layout containers
                if not widget.id and not getattr(widget, 'name', None):
                    continue
                try:
                    content = _strip_rich_markup(widget.renderable)
                    if content and len(content.strip()) > 0:
                        lines.append(f"Static{wid}: {content[:120]}")
                except Exception:
                    pass

            elif cls_name == "Header":
                try:
                    # Header title is already captured via app.title
                    pass
                except Exception:
                    pass

            elif cls_name == "Footer":
                try:
                    bindings = [b.key for b in app.screen.active_bindings.values()]
                    lines.append(f"Footer bindings: {bindings}")
                except Exception:
                    lines.append("Footer: (bindings unavailable)")
                lines.append("")

    except Exception as exc:
        lines.append(f"(walk_children error: {exc})")

    # Active notifications
    try:
        notifications = list(app.screen.query("Toast"))
        if not notifications:
            # Try alternative notification widget class names
            notifications = list(app.screen.query("Notification"))
        if notifications:
            lines.append("Notifications:")
            for n in notifications:
                try:
                    msg = _strip_rich_markup(n.renderable)
                    lines.append(f"  {msg[:120]}")
                except Exception:
                    lines.append("  (notification present)")
            lines.append("")
    except Exception:
        pass

    # Active bindings summary
    try:
        bindings = [(b.key, b.description) for b in app.screen.active_bindings.values()]
        lines.append(f"Active keys: {[(k, d) for k, d in bindings]}")
    except Exception:
        pass

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Claude persona call
# ---------------------------------------------------------------------------

def ask_persona(goal: str, screen_text: str, history: list) -> dict:
    """Call claude -p with the current screen state and get back a JSON action."""
    # Compress history to last 3 turns to keep context small
    compressed = history[-3:] if len(history) > 3 else history
    # Strip screen text from compressed history to save tokens
    compressed_slim = [
        {k: v for k, v in step.items() if k != "screen"}
        for step in compressed
    ]

    prompt = f"""You are a Studio director driving a TUI.

Your goal: {goal}

Available actions (return ONE as JSON, nothing else):
  {{"action": "press_key", "key": "<keyname>"}}
    Valid keys: q, r, enter, up, down, j, k, tab, escape
  {{"action": "done", "verdict": "<short reason>", "findings": [<list of dicts>]}}
    Call this when you have enough info to answer the goal,
    OR when you are stuck and cannot make progress.

Rules:
- Output ONLY a single JSON object. No prose, no markdown fences.
- Maximum 15 steps total. Be efficient.
- If a screen contains all the information you need, call done() immediately.
- Each finding dict should answer the goal — include lab id, status, recommendation, etc.
- "needs_review" status means the lab has promotion candidates awaiting director action.

Recent history (last few steps):
{json.dumps(compressed_slim, indent=2)}

CURRENT SCREEN:
{screen_text}

Respond with one JSON object now:"""

    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)  # force subscription billing per project convention

    try:
        result = subprocess.run(
            ["claude", "-p", "--output-format", "text", prompt],
            capture_output=True, text=True, timeout=120, env=env,
        )
    except FileNotFoundError:
        return {"action": "done", "verdict": "claude CLI not found on PATH", "findings": []}
    except subprocess.TimeoutExpired:
        return {"action": "done", "verdict": "claude CLI timed out after 120s", "findings": []}

    if result.returncode != 0:
        return {
            "action": "done",
            "verdict": f"claude error (exit {result.returncode}): {result.stderr[:200]}",
            "findings": [],
        }

    raw = result.stdout.strip()

    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Find first { ... } block (handle any surrounding noise)
    m = re.search(r'\{.*\}', raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    return {
        "action": "done",
        "verdict": f"unparseable persona response: {raw[:200]}",
        "findings": [],
    }


# ---------------------------------------------------------------------------
# Core persona loop
# ---------------------------------------------------------------------------

async def run_persona(goal: str, app_class, max_steps: int = 15, verbose: bool = False) -> dict:
    """Run the persona loop against app_class.

    Args:
        goal: Natural-language goal for the persona.
        app_class: A Textual App subclass (not instance).
        max_steps: Maximum interaction steps before giving up.
        verbose: If True, print each step's screen and decision.

    Returns:
        dict with keys: verdict, findings, steps, history
    """
    history = []

    async with app_class().run_test(size=(120, 40)) as pilot:
        for step in range(max_steps):
            await pilot.pause()
            screen_text = serialize_screen(pilot.app)
            history.append({"step": step, "screen": screen_text})

            if verbose:
                print(f"\n--- Step {step} ---")
                print(screen_text)

            decision = ask_persona(goal, screen_text, history)
            history[-1]["decision"] = decision

            if verbose:
                print(f"Decision: {json.dumps(decision, indent=2)}")

            if decision["action"] == "done":
                return {
                    "verdict": decision.get("verdict", "(no verdict)"),
                    "findings": decision.get("findings", []),
                    "steps": step + 1,
                    "history": history,
                }
            elif decision["action"] == "press_key":
                key = decision.get("key", "")
                valid_keys = {"q", "r", "enter", "up", "down", "j", "k", "tab", "escape"}
                if key not in valid_keys:
                    return {
                        "verdict": f"persona returned invalid key: {key!r}",
                        "findings": [],
                        "steps": step + 1,
                        "history": history,
                    }
                await pilot.press(key)
            else:
                return {
                    "verdict": f"persona returned malformed action: {decision}",
                    "findings": [],
                    "steps": step + 1,
                    "history": history,
                }

    return {
        "verdict": "max steps reached without done()",
        "findings": [],
        "steps": max_steps,
        "history": history,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an LLM persona against the Studio Cockpit TUI."
    )
    parser.add_argument(
        "--goal",
        default="Find all labs that need review or are blocked. Report lab IDs and recommendations.",
        help="Natural-language goal for the persona.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=15,
        help="Maximum interaction steps before giving up (default: 15).",
    )
    parser.add_argument(
        "--lab-root",
        default=None,
        help="Path to the federation root lab directory (default: examples/hello-lab).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each step's screen state and persona decision.",
    )
    args = parser.parse_args()

    # Resolve lab root
    harness_root = Path(__file__).resolve().parents[1]
    if args.lab_root:
        lab_root = Path(args.lab_root).resolve()
    else:
        lab_root = (harness_root / "examples" / "hello-lab").resolve()

    if not lab_root.exists():
        print(f"error: lab root does not exist: {lab_root}", file=sys.stderr)
        sys.exit(2)

    # Set env before importing CockpitApp (module-level code resolves the path)
    os.environ["CGL_LAB_ROOT"] = str(lab_root)

    # Add studio to path so lab_tui is importable
    studio_path = str(harness_root / "studio")
    if studio_path not in sys.path:
        sys.path.insert(0, studio_path)

    from lab_tui.cockpit import CockpitApp  # noqa: E402 (deferred intentionally)

    print(f"Persona goal: {args.goal}")
    print(f"Lab root: {lab_root}")
    print(f"Max steps: {args.max_steps}")
    print()

    result = asyncio.run(
        run_persona(
            goal=args.goal,
            app_class=CockpitApp,
            max_steps=args.max_steps,
            verbose=args.verbose,
        )
    )

    print(f"\n=== Persona Result ===")
    print(f"Steps used: {result['steps']}")
    print(f"Verdict:    {result['verdict']}")
    if result["findings"]:
        print(f"Findings:")
        for f in result["findings"]:
            print(f"  {json.dumps(f)}")
    else:
        print("Findings:   (none)")

    # Exit 0 on success signals, 1 otherwise
    verdict_lower = result["verdict"].lower()
    success_words = {"achieved", "found", "complete", "done", "identified", "located"}
    if any(w in verdict_lower for w in success_words):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
