"""tools/director_persona_capture.py — Director persona capture driver.

Runs a scripted human-director conversation against the live cockpit chat pane,
capturing before/after screenshots for each exchange.

Unlike persona_capture.py (which drives the TUI via key-presses), this driver
types pre-scripted questions into the Director Chat input, waits for the real
director agent subprocess to respond, and captures the cockpit state before
and after each exchange.

Usage:
    studio/.venv/bin/python tools/director_persona_capture.py \\
        --persona-slug human-director-triage \\
        --scenario "First-time director triages the federation" \\
        --lab-root examples/hello-lab \\
        --question "What needs my attention right now?" \\
        --question "Walk me through the keep_evidence claw."

Or load questions from a JSON file:
    --questions-file questions.json   # list of strings

Outputs land in:
    tools/persona_runs/<run_id>/
        step-0-before.svg  step-0-before.png
        step-0-after.svg   step-0-after.png
        ...
        manifest.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import cairosvg

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TOOLS_DIR = Path(__file__).resolve().parent
RUNS_DIR = TOOLS_DIR / "persona_runs"

# ---------------------------------------------------------------------------
# Screenshot helpers
# ---------------------------------------------------------------------------


def capture_screenshot(app, run_dir: Path, name: str) -> tuple[Path, Path]:
    """Export SVG + PNG. Returns (svg_path, png_path)."""
    svg_path = run_dir / f"{name}.svg"
    png_path = run_dir / f"{name}.png"

    svg_content: str = app.export_screenshot()
    svg_path.write_text(svg_content, encoding="utf-8")

    cairosvg.svg2png(
        url=str(svg_path),
        write_to=str(png_path),
        output_width=1600,
    )

    return svg_path, png_path


# ---------------------------------------------------------------------------
# Core director persona loop
# ---------------------------------------------------------------------------


async def run_director_persona(
    persona_slug: str,
    questions: list[str],
    scenario: str,
    federation_root: Path,
    output_dir: Path,
    size: tuple[int, int] = (200, 50),
    verbose: bool = False,
) -> dict:
    """Run a scripted director conversation against the live cockpit chat.

    Each iteration:
      1. Capture screenshot (cockpit at-rest before this question)
      2. Set the chat input value to the question and submit
      3. Wait for the agent's reply (poll _thinking flag up to 120s)
      4. Capture screenshot (cockpit showing the exchange)
      5. Record the exchange in the manifest
    """
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%d-%H%M%S") + f"-{persona_slug}"
    started_at = now.isoformat()

    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    exchanges: list[dict] = []

    # Import here so CGL_LAB_ROOT env is already set
    harness_root = TOOLS_DIR.parent
    studio_path = str(harness_root / "studio")
    if studio_path not in sys.path:
        sys.path.insert(0, studio_path)

    from lab_tui.cockpit import CockpitApp, DirectorChat  # noqa: E402
    from textual.widgets import Input  # noqa: E402

    async with CockpitApp().run_test(size=size) as pilot:
        # Let the app settle (data load, mount)
        await pilot.pause()
        await asyncio.sleep(1)

        # Locate persistent chat pane widget once
        chat_pane = pilot.app.query_one(DirectorChat)

        for i, question in enumerate(questions):
            if verbose:
                print(f"\n--- Exchange {i}: {question[:60]} ---")

            # 1. Capture before screenshot
            before_name = f"step-{i}-before"
            before_svg, before_png = capture_screenshot(pilot.app, run_dir, before_name)

            if verbose:
                print(f"  before screenshot: {before_png.name}")

            # 2. Focus input, type the question, submit
            chat_input = pilot.app.query_one("#chat-input", Input)

            # Record current history length so we know when a new exchange lands
            history_before = len(chat_pane._history)

            # Focus and type character by character (most reliable in run_test).
            # Special characters need mapped key names.
            _CHAR_MAP = {
                " ": "space",
                "?": "question_mark",
                "!": "exclamation_mark",
                ".": "full_stop",
                ",": "comma",
                "-": "minus",
                "_": "underscore",
                "'": "apostrophe",
                "/": "slash",
                "\\": "backslash",
                ":": "colon",
                ";": "semicolon",
            }
            chat_input.focus()
            await pilot.pause()
            for ch in question:
                key_name = _CHAR_MAP.get(ch, ch)
                await pilot.press(key_name)
            await pilot.pause()

            t0 = time.monotonic()
            await pilot.press("enter")

            # 3. Wait for the agent to finish.
            # Strategy: poll until history grows by at least 2 (human + agent turns),
            # OR until _thinking has been True then back to False.
            # The agent typically responds in 5-30s; we allow up to 120s.
            wait_limit = 120  # seconds
            poll_interval = 1

            # First wait for _thinking to become True (max 5s)
            for _ in range(5):
                await asyncio.sleep(1)
                if chat_pane._thinking:
                    break

            # Now wait for _thinking to go False again
            while True:
                await asyncio.sleep(poll_interval)
                thinking = chat_pane._thinking
                hist_len = len(chat_pane._history)
                elapsed = time.monotonic() - t0
                # Done when not thinking AND new history entries appeared
                if not thinking and hist_len > history_before:
                    break
                if elapsed > wait_limit:
                    if verbose:
                        print(f"  WARNING: agent did not respond within {wait_limit}s")
                    break

            agent_response_ms = int((time.monotonic() - t0) * 1000)

            # Give the UI one more frame to render
            await pilot.pause()
            await asyncio.sleep(0.5)

            # 4. Capture after screenshot
            after_name = f"step-{i}-after"
            after_svg, after_png = capture_screenshot(pilot.app, run_dir, after_name)

            if verbose:
                print(f"  after screenshot: {after_png.name}")
                print(f"  agent response time: {agent_response_ms}ms")

            # 5. Extract agent response from chat history
            agent_response = ""
            if len(chat_pane._history) >= 2:
                # Last pair in history: human then agent
                # Find the most recent agent turn
                for turn in reversed(chat_pane._history):
                    if turn["role"] == "agent":
                        agent_response = turn["content"]
                        break

            if verbose:
                print(f"  agent response (first 150): {agent_response[:150]}")

            exchanges.append({
                "exchange_num": i,
                "before_svg": before_name + ".svg",
                "before_png": before_name + ".png",
                "human_message": question,
                "agent_response": agent_response,
                "agent_response_ms": agent_response_ms,
                "after_svg": after_name + ".svg",
                "after_png": after_name + ".png",
            })

    ended_at = datetime.now(timezone.utc).isoformat()

    manifest = {
        "run_id": run_id,
        "persona_slug": persona_slug,
        "scenario": scenario,
        "started_at": started_at,
        "ended_at": ended_at,
        "exchanges": exchanges,
        "exchange_count": len(exchanges),
    }

    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "exchange_count": len(exchanges),
        "exchanges": exchanges,
        "started_at": started_at,
        "ended_at": ended_at,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Director persona capture driver — scripted director conversation."
    )
    parser.add_argument(
        "--persona-slug",
        required=True,
        help="Short identifier for this persona run.",
    )
    parser.add_argument(
        "--scenario",
        required=True,
        help="Human-readable description of the scenario being run.",
    )
    parser.add_argument(
        "--lab-root",
        default=None,
        help="Path to the federation root lab directory.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory under which to create the run folder (default: tools/persona_runs/).",
    )
    parser.add_argument(
        "--question",
        action="append",
        dest="questions",
        default=[],
        help="A question to ask (can be repeated, will be asked in order).",
    )
    parser.add_argument(
        "--questions-file",
        default=None,
        help="Path to a JSON file containing a list of question strings.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-exchange progress.",
    )
    args = parser.parse_args()

    harness_root = Path(__file__).resolve().parents[1]

    if args.lab_root:
        lab_root = Path(args.lab_root).resolve()
    else:
        lab_root = (harness_root / "examples" / "hello-lab").resolve()

    if not lab_root.exists():
        print(f"error: lab root does not exist: {lab_root}", file=sys.stderr)
        sys.exit(2)

    # Build question list
    questions: list[str] = list(args.questions)
    if args.questions_file:
        qf = Path(args.questions_file)
        try:
            loaded = json.loads(qf.read_text(encoding="utf-8"))
            if not isinstance(loaded, list):
                print(f"error: questions-file must contain a JSON array", file=sys.stderr)
                sys.exit(2)
            questions.extend(str(q) for q in loaded)
        except Exception as exc:
            print(f"error: could not read questions file: {exc}", file=sys.stderr)
            sys.exit(2)

    if not questions:
        print("error: provide at least one --question or --questions-file", file=sys.stderr)
        sys.exit(2)

    output_dir = Path(args.output_dir).resolve() if args.output_dir else RUNS_DIR

    # Set env before importing cockpit
    os.environ["CGL_LAB_ROOT"] = str(lab_root)

    studio_path = str(harness_root / "studio")
    if studio_path not in sys.path:
        sys.path.insert(0, studio_path)

    print(f"Persona slug: {args.persona_slug}")
    print(f"Scenario:     {args.scenario}")
    print(f"Lab root:     {lab_root}")
    print(f"Questions:    {len(questions)}")
    print(f"Output dir:   {output_dir}")
    print()

    result = asyncio.run(
        run_director_persona(
            persona_slug=args.persona_slug,
            questions=questions,
            scenario=args.scenario,
            federation_root=lab_root,
            output_dir=output_dir,
            verbose=args.verbose,
        )
    )

    print(f"\n=== Director Persona Capture Result ===")
    print(f"Run ID:     {result['run_id']}")
    print(f"Run dir:    {result['run_dir']}")
    print(f"Exchanges:  {result['exchange_count']}")
    print()

    for ex in result["exchanges"]:
        i = ex["exchange_num"]
        resp_preview = ex["agent_response"][:150].replace("\n", " ")
        print(f"  [{i}] Q: {ex['human_message']}")
        print(f"       A: {resp_preview}")
        print(f"       ({ex['agent_response_ms']}ms)")
        print()

    # Update viewer index
    viewer_dir = TOOLS_DIR / "persona_viewer"
    make_index = viewer_dir / "make_index.py"
    if make_index.exists():
        import subprocess
        try:
            subprocess.run(
                [sys.executable, str(make_index)],
                check=True,
                capture_output=not args.verbose,
            )
            print("Viewer index updated.")
        except subprocess.CalledProcessError as exc:
            print(f"Warning: make_index.py failed: {exc}", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
