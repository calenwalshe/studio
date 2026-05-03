"""tools/persona_capture.py — widescreen capturing variant of the persona driver.

Same interaction loop as persona_driver.py, but after each step:
  1. Calls pilot.app.export_screenshot() to capture an SVG.
  2. Renders the SVG to PNG at 1600px wide via cairosvg.
  3. Writes a manifest.json summarising the run.

Run IDs use the form YYYYMMDD-HHMMSS-<persona_slug>.

Standalone usage:
    studio/.venv/bin/python tools/persona_capture.py \\
        --persona-slug power-user \\
        --goal "Inspect the promotion candidates for hello-lab." \\
        --max-steps 10 \\
        --verbose

Outputs land in:
    tools/persona_runs/<run_id>/
        step-0.svg  step-0.png
        step-1.svg  step-1.png
        ...
        manifest.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import cairosvg  # already in the venv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TOOLS_DIR = Path(__file__).resolve().parent
RUNS_DIR = TOOLS_DIR / "persona_runs"


# ---------------------------------------------------------------------------
# Re-use serializer from persona_driver
# ---------------------------------------------------------------------------

def _strip_rich_markup(text: str) -> str:
    return re.sub(r'\[/?[^\[\]]*\]', '', str(text)).strip()


def serialize_screen(app) -> str:
    """Plain-text snapshot of the live Textual app (identical logic to persona_driver)."""
    lines: list[str] = []

    title = getattr(app, 'title', '') or ''
    subtitle = getattr(app, 'sub_title', '') or ''
    lines.append("=== Studio Cockpit ===")
    lines.append(f"Title: {title}")
    if subtitle:
        lines.append(f"Subtitle: {subtitle}")
    lines.append("")

    try:
        for widget in app.screen.walk_children():
            cls_name = type(widget).__name__

            if cls_name == "DataTable":
                wid = f"#{widget.id}" if widget.id else ""
                lines.append(f"DataTable{wid}:")
                try:
                    col_labels = [str(col.label) for col in widget.columns.values()]
                    lines.append(f"  Columns: {' | '.join(col_labels)}")
                except Exception:
                    pass
                try:
                    row_count = widget.row_count
                    lines.append(f"  Rows ({row_count} total):")
                    for i in range(row_count):
                        try:
                            row = widget.get_row_at(i)
                            row_str = " | ".join(str(cell) for cell in row)
                            cursor_mark = " <-- cursor" if widget.cursor_row == i else ""
                            lines.append(f"    [{i}] {row_str}{cursor_mark}")
                        except Exception:
                            lines.append(f"    [{i}] (unreadable)")
                except Exception:
                    lines.append("  (rows unavailable)")
                lines.append("")

            elif cls_name == "DirectorQueuePane":
                wid = f"#{widget.id}" if widget.id else ""
                lines.append(f"DirectorQueue{wid}:")
                try:
                    content = _strip_rich_markup(widget.renderable)
                    if content:
                        for line in content.splitlines()[:20]:
                            lines.append(f"  {line}")
                    else:
                        lines.append("  (empty)")
                except Exception:
                    lines.append("  (unreadable)")
                lines.append("")

            elif cls_name == "Static":
                wid = f"#{widget.id}" if widget.id else ""
                if not widget.id and not getattr(widget, 'name', None):
                    continue
                try:
                    content = _strip_rich_markup(widget.renderable)
                    if content and len(content.strip()) > 0:
                        lines.append(f"Static{wid}: {content[:120]}")
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

    try:
        notifications = list(app.screen.query("Toast"))
        if not notifications:
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

    try:
        bindings = [(b.key, b.description) for b in app.screen.active_bindings.values()]
        lines.append(f"Active keys: {[(k, d) for k, d in bindings]}")
    except Exception:
        pass

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Claude persona call (same as persona_driver, extended prompt for capture)
# ---------------------------------------------------------------------------

def ask_persona(goal: str, screen_text: str, history: list) -> dict:
    """Call claude -p with the current screen state and return a JSON action."""
    compressed = history[-3:] if len(history) > 3 else history
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
- If you cannot reach the required data (no navigation path exists in the UI), call done()
  immediately and report the gap in findings.

Recent history (last few steps):
{json.dumps(compressed_slim, indent=2)}

CURRENT SCREEN:
{screen_text}

Respond with one JSON object now:"""

    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)

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

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

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
# Screenshot helpers
# ---------------------------------------------------------------------------

def capture_step_screenshot(app, run_dir: Path, step_num: int) -> tuple[Path, Path]:
    """Export SVG + PNG for the current step. Returns (svg_path, png_path)."""
    svg_path = run_dir / f"step-{step_num}.svg"
    png_path = run_dir / f"step-{step_num}.png"

    svg_content: str = app.export_screenshot()
    svg_path.write_text(svg_content, encoding="utf-8")

    cairosvg.svg2png(
        url=str(svg_path),
        write_to=str(png_path),
        output_width=1600,
    )

    return svg_path, png_path


# ---------------------------------------------------------------------------
# Core persona loop with capture
# ---------------------------------------------------------------------------

async def run_persona_capture(
    goal: str,
    persona_slug: str,
    app_class,
    max_steps: int = 15,
    verbose: bool = False,
) -> dict:
    """Run the persona loop against app_class, capturing screenshots each step.

    Returns:
        dict with keys: run_id, verdict, findings, steps, history, run_dir
    """
    now = datetime.now(timezone.utc)
    run_id = now.strftime("%Y%m%d-%H%M%S") + f"-{persona_slug}"
    started_at = now.isoformat()

    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    history: list[dict] = []
    step_records: list[dict] = []

    async with app_class().run_test(size=(200, 50)) as pilot:
        for step in range(max_steps):
            await pilot.pause()

            # Capture screenshot BEFORE serializing for the persona
            svg_path, png_path = capture_step_screenshot(pilot.app, run_dir, step)

            screen_text = serialize_screen(pilot.app)
            history.append({"step": step, "screen": screen_text})

            if verbose:
                print(f"\n--- Step {step} ---")
                print(screen_text)

            decision = ask_persona(goal, screen_text, history)
            history[-1]["decision"] = decision

            if verbose:
                print(f"Decision: {json.dumps(decision, indent=2)}")

            step_records.append({
                "step_num": step,
                "svg_path": str(svg_path),
                "png_path": str(png_path),
                "screen_text": screen_text,
                "decision": decision,
            })

            if decision["action"] == "done":
                ended_at = datetime.now(timezone.utc).isoformat()
                verdict = decision.get("verdict", "(no verdict)")
                findings = decision.get("findings", [])

                manifest = {
                    "run_id": run_id,
                    "persona_slug": persona_slug,
                    "goal": goal,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "steps": step_records,
                    "final_verdict": verdict,
                    "findings": findings,
                }
                _write_manifest(run_dir, manifest)

                return {
                    "run_id": run_id,
                    "verdict": verdict,
                    "findings": findings,
                    "steps": step + 1,
                    "history": history,
                    "run_dir": str(run_dir),
                }

            elif decision["action"] == "press_key":
                key = decision.get("key", "")
                valid_keys = {"q", "r", "enter", "up", "down", "j", "k", "tab", "escape"}
                if key not in valid_keys:
                    ended_at = datetime.now(timezone.utc).isoformat()
                    verdict = f"persona returned invalid key: {key!r}"
                    manifest = {
                        "run_id": run_id,
                        "persona_slug": persona_slug,
                        "goal": goal,
                        "started_at": started_at,
                        "ended_at": ended_at,
                        "steps": step_records,
                        "final_verdict": verdict,
                        "findings": [],
                    }
                    _write_manifest(run_dir, manifest)
                    return {
                        "run_id": run_id,
                        "verdict": verdict,
                        "findings": [],
                        "steps": step + 1,
                        "history": history,
                        "run_dir": str(run_dir),
                    }
                await pilot.press(key)

            else:
                ended_at = datetime.now(timezone.utc).isoformat()
                verdict = f"persona returned malformed action: {decision}"
                manifest = {
                    "run_id": run_id,
                    "persona_slug": persona_slug,
                    "goal": goal,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "steps": step_records,
                    "final_verdict": verdict,
                    "findings": [],
                }
                _write_manifest(run_dir, manifest)
                return {
                    "run_id": run_id,
                    "verdict": verdict,
                    "findings": [],
                    "steps": step + 1,
                    "history": history,
                    "run_dir": str(run_dir),
                }

    # Max steps reached
    ended_at = datetime.now(timezone.utc).isoformat()
    verdict = "max steps reached without done()"
    manifest = {
        "run_id": run_id,
        "persona_slug": persona_slug,
        "goal": goal,
        "started_at": started_at,
        "ended_at": ended_at,
        "steps": step_records,
        "final_verdict": verdict,
        "findings": [],
    }
    _write_manifest(run_dir, manifest)
    return {
        "run_id": run_id,
        "verdict": verdict,
        "findings": [],
        "steps": max_steps,
        "history": history,
        "run_dir": str(run_dir),
    }


def _write_manifest(run_dir: Path, manifest: dict) -> None:
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Widescreen capturing persona driver for Studio Cockpit TUI testing."
    )
    parser.add_argument(
        "--persona-slug",
        required=True,
        help="Short identifier for this persona (used in run_id and manifest).",
    )
    parser.add_argument(
        "--goal",
        required=True,
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

    harness_root = Path(__file__).resolve().parents[1]

    if args.lab_root:
        lab_root = Path(args.lab_root).resolve()
    else:
        lab_root = (harness_root / "examples" / "hello-lab").resolve()

    if not lab_root.exists():
        print(f"error: lab root does not exist: {lab_root}", file=sys.stderr)
        sys.exit(2)

    os.environ["CGL_LAB_ROOT"] = str(lab_root)

    studio_path = str(harness_root / "studio")
    if studio_path not in sys.path:
        sys.path.insert(0, studio_path)

    from lab_tui.cockpit import CockpitApp  # noqa: E402

    print(f"Persona slug: {args.persona_slug}")
    print(f"Persona goal: {args.goal}")
    print(f"Lab root:     {lab_root}")
    print(f"Max steps:    {args.max_steps}")
    print(f"Runs dir:     {RUNS_DIR}")
    print()

    result = asyncio.run(
        run_persona_capture(
            goal=args.goal,
            persona_slug=args.persona_slug,
            app_class=CockpitApp,
            max_steps=args.max_steps,
            verbose=args.verbose,
        )
    )

    print(f"\n=== Persona Capture Result ===")
    print(f"Run ID:    {result['run_id']}")
    print(f"Run dir:   {result['run_dir']}")
    print(f"Steps:     {result['steps']}")
    print(f"Verdict:   {result['verdict']}")
    if result["findings"]:
        print("Findings:")
        for f in result["findings"]:
            print(f"  {json.dumps(f)}")
    else:
        print("Findings:  (none)")

    # Update the viewer index automatically after a run
    viewer_dir = TOOLS_DIR / "persona_viewer"
    make_index = viewer_dir / "make_index.py"
    if make_index.exists():
        try:
            subprocess.run(
                [sys.executable, str(make_index)],
                check=True,
                capture_output=not args.verbose,
            )
            if args.verbose:
                print("\nViewer index updated.")
        except subprocess.CalledProcessError as exc:
            print(f"Warning: make_index.py failed: {exc}", file=sys.stderr)

    verdict_lower = result["verdict"].lower()
    success_words = {"achieved", "found", "complete", "done", "identified", "located"}
    if any(w in verdict_lower for w in success_words):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
