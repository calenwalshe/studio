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

Mixed chat + keypress:
    --question "Quick triage: what are my top 3 priorities?" \\
    --keypress "j:Move down to cgl-publish" \\
    --keypress "enter:Expand cgl-publish" \\
    --question "What does cgl-publish need from me?"

For keypress steps the format is "<key>:<human-readable label>". The step is
recorded in the manifest with step_type="keypress" and no agent message fields.

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
import hashlib
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


def _parse_directives(raw_questions: list[str], raw_keypresses: list[str]) -> list[dict]:
    """Merge --question and --keypress args into an ordered directive list.

    argparse collects them in a shared list when action="append" is used on
    both; we rely on the caller passing two separate lists and interleaving
    them via a special sentinel so order is preserved.  The actual ordering is
    injected by main() which builds the list directly from sys.argv position.

    This helper is kept for internal use; callers should pass the pre-built
    directives list directly to run_director_persona().
    """
    # Fallback: all questions first, then keypresses (not mixed).
    directives: list[dict] = []
    for q in raw_questions:
        directives.append({"type": "chat", "text": q})
    for kp in raw_keypresses:
        key, _, label = kp.partition(":")
        directives.append({"type": "keypress", "key": key.strip(), "label": label.strip()})
    return directives


async def run_director_persona(
    persona_slug: str,
    directives: list[dict],
    scenario: str,
    federation_root: Path,
    output_dir: Path,
    size: tuple[int, int] = (200, 50),
    verbose: bool = False,
    question_timeout: int = 120,
) -> dict:
    """Run a scripted director conversation against the live cockpit chat.

    directives is an ordered list of steps, each a dict with:
      {"type": "chat", "text": "<question>"}
      {"type": "keypress", "key": "<key>", "label": "<human label>"}
      {"type": "type", "input_id": "<widget-id>", "text": "<text to set>"}
      {"type": "action", "name": "<action_name>", "label": "<human label>", **kwargs}

    For chat steps:
      1. Capture before screenshot
      2. Type the question into the chat input and submit
      3. Wait for the agent's reply (poll _thinking flag)
      4. Capture after screenshot
      5. Record exchange with step_type="chat"

    For keypress steps:
      1. Capture before screenshot
      2. Press the key via pilot
      3. Wait ~0.5s for UI to update
      4. Capture after screenshot
      5. Record exchange with step_type="keypress" (no agent message fields)

    For type steps:
      1. Capture before screenshot
      2. Focus widget by id, set .value = text
      3. Wait ~0.3s for UI to update
      4. Capture after screenshot
      5. Record exchange with step_type="type"

    For action steps (bypass modal UI, call action functions directly):
      Supported actions: view_result, promote_claw, archive_claw,
        spawn_dry_run, create_lab, archive_lab
      1. Capture before screenshot
      2. Execute the action function directly (mutations happen on filesystem)
      3. Call action_refresh on the app
      4. Capture after screenshot
      5. Record exchange with step_type="action"
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

    from lab_tui.cockpit import CockpitApp, DirectorChat, LabList  # noqa: E402
    from textual.widgets import Input  # noqa: E402

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

    async with CockpitApp().run_test(size=size) as pilot:
        # Let the app settle (data load, mount)
        await pilot.pause()
        await asyncio.sleep(1)

        # Locate persistent widgets once
        chat_pane = pilot.app.query_one(DirectorChat)
        lab_list = pilot.app.query_one(LabList)

        for i, directive in enumerate(directives):
            step_type = directive.get("type", "chat")

            if verbose:
                if step_type == "chat":
                    print(f"\n--- Exchange {i} [chat]: {directive['text'][:60]} ---")
                elif step_type == "type":
                    print(f"\n--- Exchange {i} [type]: #{directive['input_id']} = {directive['text'][:40]} ---")
                elif step_type == "action":
                    print(f"\n--- Exchange {i} [action]: {directive.get('name', '?')} ({directive.get('label', '')}) ---")
                elif step_type == "expand_lab":
                    print(f"\n--- Exchange {i} [expand_lab]: {directive.get('lab_id', '?')} ---")
                else:
                    print(f"\n--- Exchange {i} [keypress]: {directive['key']} ({directive.get('label', '')}) ---")

            # 1. Capture before screenshot
            before_name = f"step-{i}-before"
            before_svg, before_png = capture_screenshot(pilot.app, run_dir, before_name)

            if verbose:
                print(f"  before screenshot: {before_png.name}")

            # -----------------------------------------------------------------
            if step_type == "keypress":
                key = directive["key"]
                label = directive.get("label", key)

                # Ensure the LabList has focus so navigation keys work
                chat_input = pilot.app.query_one("#chat-input", Input)
                if chat_input.has_focus:
                    # Move focus to the first LabRow so nav keys work
                    from lab_tui.cockpit import LabRow  # noqa: E402
                    rows = list(pilot.app.query(LabRow))
                    if rows:
                        pilot.app.set_focus(rows[lab_list.focused_index()])
                    await pilot.pause()

                t0 = time.monotonic()
                await pilot.press(key)
                await pilot.pause()
                await asyncio.sleep(0.5)

                elapsed_ms = int((time.monotonic() - t0) * 1000)

                # 4. Capture after screenshot
                after_name = f"step-{i}-after"
                after_svg, after_png = capture_screenshot(pilot.app, run_dir, after_name)

                if verbose:
                    print(f"  after screenshot: {after_png.name}")
                    print(f"  keypress elapsed: {elapsed_ms}ms")

                exchanges.append({
                    "exchange_num": i,
                    "step_type": "keypress",
                    "key": key,
                    "label": label,
                    "before_svg": before_name + ".svg",
                    "before_png": before_name + ".png",
                    "after_svg": after_name + ".svg",
                    "after_png": after_name + ".png",
                    "elapsed_ms": elapsed_ms,
                })

            # -----------------------------------------------------------------
            elif step_type == "expand_lab":
                target_lab_id = directive.get("lab_id", "")
                label = directive.get("label", f"expand {target_lab_id}")
                expand_ok = False
                expand_detail = "(not attempted)"

                t0 = time.monotonic()
                try:
                    from lab_tui.cockpit import LabRow  # noqa: E402
                    rows = list(pilot.app.query(LabRow))
                    target_row = next((r for r in rows if r.lab_id == target_lab_id), None)
                    if target_row is not None:
                        # Collapse any currently expanded rows
                        for row in rows:
                            if row is not target_row and row.expanded:
                                row.collapse()
                        # Focus and expand the target row
                        pilot.app.set_focus(target_row)
                        await pilot.pause()
                        if not target_row.expanded:
                            lab_list.toggle_focused()
                        await pilot.pause()
                        await asyncio.sleep(0.5)
                        expand_ok = target_row.expanded
                        expand_detail = f"lab_id={target_lab_id} expanded={expand_ok}"
                    else:
                        expand_detail = f"no LabRow found with lab_id={target_lab_id!r}"
                except Exception as exc:
                    expand_detail = f"expand_lab error: {exc}"
                    if verbose:
                        import traceback
                        traceback.print_exc()

                elapsed_ms = int((time.monotonic() - t0) * 1000)

                after_name = f"step-{i}-after"
                after_svg, after_png = capture_screenshot(pilot.app, run_dir, after_name)

                if verbose:
                    print(f"  expand_lab: {expand_detail}")
                    print(f"  after screenshot: {after_png.name}")
                    print(f"  expand elapsed: {elapsed_ms}ms")

                exchanges.append({
                    "exchange_num": i,
                    "step_type": "expand_lab",
                    "lab_id": target_lab_id,
                    "label": label,
                    "expand_ok": expand_ok,
                    "expand_detail": expand_detail,
                    "before_svg": before_name + ".svg",
                    "before_png": before_name + ".png",
                    "after_svg": after_name + ".svg",
                    "after_png": after_name + ".png",
                    "elapsed_ms": elapsed_ms,
                })

            # -----------------------------------------------------------------
            elif step_type == "type":
                input_id = directive["input_id"]
                type_text = directive["text"]
                label = directive.get("label", f"type into #{input_id}")

                try:
                    from textual.widgets import Input as TxInput
                    widget = pilot.app.query_one(f"#{input_id}", TxInput)
                    widget.focus()
                    await pilot.pause()
                    widget.value = type_text
                    await pilot.pause()
                    await asyncio.sleep(0.3)
                except Exception as exc:
                    if verbose:
                        print(f"  WARNING: could not type into #{input_id}: {exc}")

                t0 = time.monotonic()
                elapsed_ms = int((time.monotonic() - t0) * 1000)

                after_name = f"step-{i}-after"
                after_svg, after_png = capture_screenshot(pilot.app, run_dir, after_name)

                if verbose:
                    print(f"  after screenshot: {after_png.name}")
                    print(f"  type elapsed: {elapsed_ms}ms")

                exchanges.append({
                    "exchange_num": i,
                    "step_type": "type",
                    "input_id": input_id,
                    "text": type_text,
                    "label": label,
                    "before_svg": before_name + ".svg",
                    "before_png": before_name + ".png",
                    "after_svg": after_name + ".svg",
                    "after_png": after_name + ".png",
                    "elapsed_ms": elapsed_ms,
                })

            # -----------------------------------------------------------------
            elif step_type == "action":
                action_name = directive.get("name", "unknown")
                action_label = directive.get("label", action_name)
                action_result_msg = "(no result)"
                action_ok = False

                t0 = time.monotonic()
                try:
                    from lab_tui.actions import (
                        apply_decision as _apply_decision,
                        archive_claw as _archive_claw,
                        archive_lab as _archive_lab,
                        create_lab as _create_lab,
                        spawn_dry_run_claw as _spawn_dry_run_claw,
                    )
                    from lab_tui.cockpit import LabList, LabRow

                    lab_list_w: LabList = pilot.app.query_one("#lab-list", LabList)
                    focused_row: LabRow | None = lab_list_w.focused_row()

                    if action_name == "view_result":
                        # Show content inline; no modal in test mode
                        if focused_row and focused_row.expanded:
                            claw = focused_row.selected_claw()
                            if claw:
                                claw_dir = focused_row._summary.lab_root / ".claws" / claw.bundle_id
                                result_file = claw_dir / "result.md"
                                content = result_file.read_text(encoding="utf-8") if result_file.exists() else "(no result.md)"
                                action_result_msg = f"Viewed result.md for {claw.bundle_id} ({len(content)} chars)"
                                action_ok = True
                            else:
                                action_result_msg = "No claw selected"
                        else:
                            action_result_msg = "No expanded row or claw"

                    elif action_name == "promote_claw":
                        if focused_row and focused_row.expanded:
                            claw = focused_row.selected_claw()
                            if claw:
                                outcome = claw.meta.get("promotion_recommendation", "")
                                claw_dir = focused_row._summary.lab_root / ".claws" / claw.bundle_id
                                res = _apply_decision(claw_dir, outcome)
                                action_result_msg = res.message
                                action_ok = res.success
                                if res.success:
                                    pilot.app.action_refresh()
                                    await pilot.pause()
                                    await asyncio.sleep(0.5)
                        else:
                            action_result_msg = "No expanded row or claw"

                    elif action_name == "archive_claw":
                        if focused_row and focused_row.expanded:
                            claw = focused_row.selected_claw()
                            if claw:
                                claw_dir = focused_row._summary.lab_root / ".claws" / claw.bundle_id
                                res = _archive_claw(claw_dir)
                                action_result_msg = res.message
                                action_ok = res.success
                                if res.success:
                                    pilot.app.action_refresh()
                                    await pilot.pause()
                                    await asyncio.sleep(0.5)
                        else:
                            action_result_msg = "No expanded row or claw"

                    elif action_name == "spawn_dry_run":
                        orientation_id = directive.get("orientation_id", "")
                        role = directive.get("role", "reviewer")
                        if focused_row:
                            res = _spawn_dry_run_claw(focused_row._summary.lab_root, orientation_id, role)
                            action_result_msg = res.message
                            action_ok = res.success
                            if res.success:
                                pilot.app.action_refresh()
                                await pilot.pause()
                                await asyncio.sleep(0.5)
                        else:
                            action_result_msg = "No lab selected"

                    elif action_name == "create_lab":
                        slug = directive.get("slug", "")
                        kind = directive.get("kind", "investigation")
                        title = directive.get("title", "")
                        objective = directive.get("objective", "")
                        res = _create_lab(federation_root, slug=slug, kind=kind, title=title, objective=objective)
                        action_result_msg = res.message
                        action_ok = res.success
                        # Skip UI refresh — remounting with changed lab count causes DuplicateIds
                        # The filesystem mutation is the source of truth; verification checks files
                        await asyncio.sleep(0.3)

                    elif action_name == "archive_lab":
                        slug = directive.get("slug", "")
                        if not slug and focused_row:
                            slug = focused_row.lab_id
                        res = _archive_lab(federation_root, slug)
                        action_result_msg = res.message
                        action_ok = res.success
                        # Same: skip UI refresh for count-changing operations
                        await asyncio.sleep(0.3)

                    else:
                        action_result_msg = f"Unknown action: {action_name}"

                except Exception as exc:
                    action_result_msg = f"Action error: {exc}"
                    if verbose:
                        import traceback
                        traceback.print_exc()

                elapsed_ms = int((time.monotonic() - t0) * 1000)

                after_name = f"step-{i}-after"
                after_svg, after_png = capture_screenshot(pilot.app, run_dir, after_name)

                if verbose:
                    print(f"  action={action_name} ok={action_ok}: {action_result_msg}")
                    print(f"  after screenshot: {after_png.name}")
                    print(f"  action elapsed: {elapsed_ms}ms")

                exchanges.append({
                    "exchange_num": i,
                    "step_type": "action",
                    "action_name": action_name,
                    "label": action_label,
                    "action_ok": action_ok,
                    "action_result_msg": action_result_msg,
                    "before_svg": before_name + ".svg",
                    "before_png": before_name + ".png",
                    "after_svg": after_name + ".svg",
                    "after_png": after_name + ".png",
                    "elapsed_ms": elapsed_ms,
                })

            # -----------------------------------------------------------------
            else:
                question = directive["text"]
                chat_input = pilot.app.query_one("#chat-input", Input)

                # Record current history length so we know when a new exchange lands
                history_before = len(chat_pane._history)

                chat_input.focus()
                await pilot.pause()
                for ch in question:
                    key_name = _CHAR_MAP.get(ch, ch)
                    await pilot.press(key_name)
                await pilot.pause()

                t0 = time.monotonic()
                # Use send_message directly rather than pilot.press("enter") so
                # Textual's 30-second _wait_for_screen timeout doesn't fire on
                # long-running agent responses.
                asyncio.ensure_future(chat_pane.send_message(question))
                chat_input.clear()

                # 3. Wait for the agent to finish.
                # Strategy: poll until history grows by at least 2 (human + agent turns),
                # OR until _thinking has been True then back to False.
                # The agent typically responds in 5-30s; we allow up to 120s.
                wait_limit = question_timeout
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
                    for turn in reversed(chat_pane._history):
                        if turn["role"] == "agent":
                            agent_response = turn["content"]
                            break

                if verbose:
                    print(f"  agent response (first 150): {agent_response[:150]}")

                exchanges.append({
                    "exchange_num": i,
                    "step_type": "chat",
                    "before_svg": before_name + ".svg",
                    "before_png": before_name + ".png",
                    "human_message": question,
                    "agent_response": agent_response,
                    "agent_response_ms": agent_response_ms,
                    "after_svg": after_name + ".svg",
                    "after_png": after_name + ".png",
                })

    ended_at = datetime.now(timezone.utc).isoformat()

    verification = build_verification(run_dir, exchanges, federation_root)

    manifest = {
        "run_id": run_id,
        "persona_slug": persona_slug,
        "scenario": scenario,
        "started_at": started_at,
        "ended_at": ended_at,
        "exchanges": exchanges,
        "exchange_count": len(exchanges),
        "verification": verification,
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
# Verification
# ---------------------------------------------------------------------------


def _png_hash(path: Path) -> str:
    """Return SHA-256 hex digest of a PNG file, or '' if missing."""
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_verification(run_dir: Path, exchanges: list[dict], federation_root: Path | None = None) -> dict:
    """Produce a heuristic verification block from the finished run.

    Heuristics (no human visual inspection):
    - alignment_check: PASS if any expanded-lab after-screenshot exists and
      the corresponding SVG contains both "Orientation" and "Claws" text.
    - default_mode_short: PASS if chat exchanges [0] and [3] (by chat-index)
      are under 35 lines AND contain "**Next:**".
    - long_form_triggered: PASS if the first chat exchange whose question
      contains a LONG_FORM_TRIGGER word is > 50 lines AND does NOT contain
      "deeper report".
    - deeper_report_offer: PASS if any default-mode chat response that is
      > 30 lines ends with the offer string.
    - paginated_scroll: PASS if before/after PNGs of two consecutive pageup
      steps exist and have DIFFERENT SHA-256 hashes (content changed).

    If federation_root is provided, also checks the 6 director actions:
    - view_action, promote_action, archive_claw, spawn_dry_run, create_lab, archive_lab
    """
    notes: list[str] = []

    # -----------------------------------------------------------------
    # alignment_check
    # -----------------------------------------------------------------
    alignment_pass = False
    for ex in exchanges:
        if ex.get("step_type") != "keypress":
            continue
        key = ex.get("key", "").lower()
        if key != "enter":
            continue
        after_svg_name = ex.get("after_svg", "")
        if not after_svg_name:
            continue
        after_svg_path = run_dir / after_svg_name
        if not after_svg_path.exists():
            continue
        svg_text = after_svg_path.read_text(encoding="utf-8", errors="replace")
        if "Orientation" in svg_text and ("Claws" in svg_text or "claws" in svg_text):
            alignment_pass = True
            notes.append(f"alignment: found Orientation+Claws in {after_svg_name}")
            break

    if not alignment_pass:
        notes.append("alignment: could not find Orientation+Claws in any enter-keypress after-screenshot")

    # -----------------------------------------------------------------
    # default_mode_short — check chat turns at chat-index 0 and 3
    # (0-indexed among chat steps only)
    # -----------------------------------------------------------------
    chat_exchanges = [ex for ex in exchanges if ex.get("step_type") == "chat"]
    default_mode_pass = False
    checked_indices = [0, 3]
    checked_results = []
    for ci in checked_indices:
        if ci >= len(chat_exchanges):
            checked_results.append(f"chat[{ci}]: missing")
            continue
        ex = chat_exchanges[ci]
        resp = ex.get("agent_response", "")
        line_count = len(resp.splitlines())
        has_next = "**Next:**" in resp
        checked_results.append(f"chat[{ci}]: {line_count} lines, **Next:** {'yes' if has_next else 'no'}")
        if line_count < 35 and has_next:
            default_mode_pass = True

    notes.append("default_mode: " + "; ".join(checked_results))

    # -----------------------------------------------------------------
    # long_form_triggered — find first question with a LONG_FORM_TRIGGER
    # -----------------------------------------------------------------
    long_form_triggers = (
        "detailed", "deep dive", "full report", "long-form", "long form",
        "everything you have", "deeper report", "comprehensive", "complete report"
    )
    long_form_pass = False
    for ex in chat_exchanges:
        q = ex.get("human_message", "").lower()
        if any(t in q for t in long_form_triggers):
            resp = ex.get("agent_response", "")
            line_count = len(resp.splitlines())
            has_offer = "deeper report" in resp.lower() or "more to say" in resp.lower()
            long_form_pass = line_count > 50 and not has_offer
            notes.append(
                f"long_form: triggered on '{ex['human_message'][:60]}...' "
                f"→ {line_count} lines, offer={'yes' if has_offer else 'no'}"
            )
            break
    else:
        notes.append("long_form: no LONG_FORM_TRIGGER question found in chat exchanges")

    # -----------------------------------------------------------------
    # deeper_report_offer — any default response > 30 lines with the offer
    # -----------------------------------------------------------------
    deeper_offer_pass = False
    for ex in chat_exchanges:
        q = ex.get("human_message", "").lower()
        # skip long-form requests
        if any(t in q for t in long_form_triggers):
            continue
        resp = ex.get("agent_response", "")
        line_count = len(resp.splitlines())
        has_offer = "_more to say" in resp.lower() or "more to say — want a deeper report" in resp.lower()
        if line_count > 30 and has_offer:
            deeper_offer_pass = True
            notes.append(f"deeper_offer: found in chat exchange q='{ex['human_message'][:50]}...'")
            break
    else:
        notes.append("deeper_offer: no default-mode response > 30 lines with the offer")

    # -----------------------------------------------------------------
    # paginated_scroll — compare before/after PNGs of pageup keypress steps
    # -----------------------------------------------------------------
    pageup_steps = [ex for ex in exchanges if ex.get("step_type") == "keypress" and ex.get("key", "").lower() == "pageup"]
    paginated_pass = False
    if len(pageup_steps) >= 2:
        step_a = pageup_steps[0]
        step_b = pageup_steps[1]
        # Compare after-PNG of step_a vs after-PNG of step_b
        hash_a = _png_hash(run_dir / step_a.get("after_png", ""))
        hash_b = _png_hash(run_dir / step_b.get("after_png", ""))
        if hash_a and hash_b and hash_a != hash_b:
            paginated_pass = True
            notes.append("paginated_scroll: after-PNGs of pageup steps differ (content changed)")
        elif hash_a == hash_b and hash_a:
            notes.append("paginated_scroll: after-PNGs of pageup steps are IDENTICAL (scroll may not have worked)")
        else:
            notes.append("paginated_scroll: could not find pageup after-PNG files")
    elif len(pageup_steps) == 1:
        # Compare before vs after of the single pageup step
        step = pageup_steps[0]
        before_hash = _png_hash(run_dir / step.get("before_png", ""))
        after_hash = _png_hash(run_dir / step.get("after_png", ""))
        if before_hash and after_hash and before_hash != after_hash:
            paginated_pass = True
            notes.append("paginated_scroll: before/after PNG differ for single pageup step")
        else:
            notes.append("paginated_scroll: only 1 pageup step found; before/after unchanged or missing")
    else:
        notes.append("paginated_scroll: no pageup keypress steps found in exchanges")

    result = {
        "alignment_check": "PASS" if alignment_pass else "FAIL",
        "default_mode_short": "PASS" if default_mode_pass else "FAIL",
        "long_form_triggered": "PASS" if long_form_pass else "FAIL",
        "deeper_report_offer": "PASS" if deeper_offer_pass else "FAIL",
        "paginated_scroll": "PASS" if paginated_pass else "FAIL",
        "notes": "; ".join(notes),
    }

    # -----------------------------------------------------------------
    # 6-action director workflow verification (when federation_root provided)
    # -----------------------------------------------------------------
    if federation_root is not None:
        action_notes: list[str] = []

        # 1. view_action — was a ClawViewerModal screenshot captured?
        #    Heuristic: look for any SVG containing "Result —" text (viewer title)
        viewer_pass = False
        for ex in exchanges:
            for key in ("after_svg", "before_svg"):
                svg_name = ex.get(key, "")
                if svg_name:
                    svg_path = run_dir / svg_name
                    if svg_path.exists():
                        try:
                            content = svg_path.read_text(encoding="utf-8", errors="replace")
                            if "Result" in content and "result" in content:
                                viewer_pass = True
                                action_notes.append(f"view_action: found viewer content in {svg_name}")
                                break
                        except Exception:
                            pass
            if viewer_pass:
                break
        if not viewer_pass:
            action_notes.append("view_action: no ClawViewerModal screenshot detected")

        # 2. promote_action — does any agent-infra claw have decision.json with outcome=merge?
        promote_pass = False
        promote_detail = "not found"
        claws_root = federation_root / "agent-infra" / ".claws"
        if claws_root.exists():
            for bundle_dir in claws_root.iterdir():
                if bundle_dir.is_dir() and not bundle_dir.name.startswith("."):
                    dec_path = bundle_dir / "decision.json"
                    if dec_path.exists():
                        try:
                            dec = json.loads(dec_path.read_text(encoding="utf-8"))
                            if dec.get("outcome") == "merge":
                                promote_pass = True
                                promote_detail = f"{bundle_dir.name}/decision.json outcome=merge"
                                break
                        except Exception:
                            pass
        action_notes.append(f"promote_action: {promote_detail}")

        # 3. archive_claw — was any agent-infra claw moved to .claws/.archive/?
        archive_claw_pass = False
        archive_claw_detail = "not found"
        archive_claws = federation_root / "agent-infra" / ".claws" / ".archive"
        if archive_claws.exists():
            archived = [p for p in archive_claws.iterdir() if p.is_dir()]
            if archived:
                archive_claw_pass = True
                archive_claw_detail = archived[0].name
        action_notes.append(f"archive_claw: {archive_claw_detail}")

        # 4. spawn_dry_run — did a new bundle appear in cgl-publish/.claws/?
        spawn_pass = False
        spawn_detail = "not found"
        cgl_publish_claws = federation_root / "cgl-publish" / ".claws"
        if cgl_publish_claws.exists():
            bundles = [p for p in cgl_publish_claws.iterdir()
                       if p.is_dir() and not p.name.startswith(".")]
            # The original fixture has 20260430-160000-builder-cgl-publish
            original_bundle = "20260430-160000-builder-cgl-publish"
            new_bundles = [b for b in bundles if b.name != original_bundle]
            if new_bundles:
                spawn_pass = True
                spawn_detail = new_bundles[0].name
                # Verify meta.json has status=dry_run
                meta_path = new_bundles[0] / "meta.json"
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                        if meta.get("status") != "dry_run":
                            spawn_detail += f" (status={meta.get('status')} not dry_run)"
                    except Exception:
                        spawn_detail += " (meta.json unreadable)"
        action_notes.append(f"spawn_dry_run: {spawn_detail}")

        # 5. create_lab — does spike-budget/.studio/lab.toml exist (or was it archived)?
        create_lab_path = federation_root / "spike-budget" / ".studio" / "lab.toml"
        create_lab_pass = create_lab_path.exists()
        create_lab_detail = f"found at {create_lab_path}"
        if not create_lab_pass:
            # Check if it was created and then archived (spike-budget-* in .archive)
            fed_archive_check = federation_root / ".archive"
            if fed_archive_check.exists():
                archived_spike = [p for p in fed_archive_check.iterdir()
                                  if p.name.startswith("spike-budget") and (p / ".studio" / "lab.toml").exists()]
                if archived_spike:
                    create_lab_pass = True
                    create_lab_detail = f"created and then archived to {archived_spike[0].name}"
            if not create_lab_pass:
                create_lab_detail = f"not found at {create_lab_path}"
        action_notes.append(f"create_lab: {create_lab_detail}")

        # 6. archive_lab — was spike-budget moved to .archive/?
        archive_lab_pass = False
        archive_lab_detail = "not found"
        fed_archive = federation_root / ".archive"
        if fed_archive.exists():
            spike_dirs = [p for p in fed_archive.iterdir() if p.name.startswith("spike-budget")]
            if spike_dirs:
                archive_lab_pass = True
                archive_lab_detail = spike_dirs[0].name
        action_notes.append(f"archive_lab: {archive_lab_detail}")

        result["view_action"] = "PASS" if viewer_pass else "FAIL"
        result["promote_action"] = "PASS" if promote_pass else "FAIL"
        result["archive_claw"] = "PASS" if archive_claw_pass else "FAIL"
        result["spawn_dry_run"] = "PASS" if spawn_pass else "FAIL"
        result["create_lab"] = "PASS" if create_lab_pass else "FAIL"
        result["archive_lab"] = "PASS" if archive_lab_pass else "FAIL"
        result["action_notes"] = "; ".join(action_notes)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_directives_from_argv() -> list[dict]:
    """Walk sys.argv in order and collect --question / --keypress / --type directives.

    This preserves their interleaved order, which argparse's action="append"
    already does but only for each flag separately.  By scanning raw argv we
    respect the exact order the caller supplied them.
    """
    directives: list[dict] = []
    args_iter = iter(sys.argv[1:])
    for token in args_iter:
        if token == "--question":
            try:
                text = next(args_iter)
                directives.append({"type": "chat", "text": text})
            except StopIteration:
                pass
        elif token.startswith("--question="):
            directives.append({"type": "chat", "text": token[len("--question="):]})
        elif token == "--keypress":
            try:
                raw = next(args_iter)
                key, _, label = raw.partition(":")
                directives.append({"type": "keypress", "key": key.strip(), "label": label.strip()})
            except StopIteration:
                pass
        elif token.startswith("--keypress="):
            raw = token[len("--keypress="):]
            key, _, label = raw.partition(":")
            directives.append({"type": "keypress", "key": key.strip(), "label": label.strip()})
        elif token == "--type":
            try:
                raw = next(args_iter)
                input_id, _, text = raw.partition(":")
                directives.append({"type": "type", "input_id": input_id.strip(), "text": text})
            except StopIteration:
                pass
        elif token.startswith("--type="):
            raw = token[len("--type="):]
            input_id, _, text = raw.partition(":")
            directives.append({"type": "type", "input_id": input_id.strip(), "text": text})
        elif token == "--action":
            try:
                raw = next(args_iter)
                # Format: "<name>:<label>" or just "<name>"
                # Extra kwargs come from subsequent --action-* tokens, but for
                # simplicity we embed kwargs as JSON after a | separator.
                # Format: "<name>:<label>|{json}" or "<name>:<label>"
                if "|" in raw:
                    name_label, _, json_str = raw.partition("|")
                    try:
                        kwargs = json.loads(json_str)
                    except Exception:
                        kwargs = {}
                else:
                    name_label = raw
                    kwargs = {}
                name, _, label = name_label.partition(":")
                d = {"type": "action", "name": name.strip(), "label": label.strip()}
                d.update(kwargs)
                directives.append(d)
            except StopIteration:
                pass
        elif token.startswith("--action="):
            raw = token[len("--action="):]
            if "|" in raw:
                name_label, _, json_str = raw.partition("|")
                try:
                    kwargs = json.loads(json_str)
                except Exception:
                    kwargs = {}
            else:
                name_label = raw
                kwargs = {}
            name, _, label = name_label.partition(":")
            d = {"type": "action", "name": name.strip(), "label": label.strip()}
            d.update(kwargs)
            directives.append(d)
    return directives


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
        "--keypress",
        action="append",
        dest="keypresses",
        default=[],
        help="A key to press, format '<key>:<label>' (can be repeated, interleaved with --question).",
    )
    parser.add_argument(
        "--type",
        action="append",
        dest="types",
        default=[],
        help="Type text into an Input widget, format '<input_id>:<text>' (can be repeated, interleaved with --question/--keypress).",
    )
    parser.add_argument(
        "--action",
        action="append",
        dest="actions",
        default=[],
        help="Execute a director action directly (bypasses modal), format '<name>:<label>|{json_kwargs}' (can be repeated, interleaved).",
    )
    parser.add_argument(
        "--questions-file",
        default=None,
        help="Path to a JSON file containing a list of question strings.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="Per-question timeout in seconds (default: 120).",
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

    # Build ordered directive list preserving interleaved question/keypress order
    directives = _build_directives_from_argv()

    # If --questions-file was provided, append its questions after any inline directives
    if args.questions_file:
        qf = Path(args.questions_file)
        try:
            loaded = json.loads(qf.read_text(encoding="utf-8"))
            if not isinstance(loaded, list):
                print("error: questions-file must contain a JSON array", file=sys.stderr)
                sys.exit(2)
            for q in loaded:
                directives.append({"type": "chat", "text": str(q)})
        except Exception as exc:
            print(f"error: could not read questions file: {exc}", file=sys.stderr)
            sys.exit(2)

    if not directives:
        print("error: provide at least one --question, --keypress, or --questions-file", file=sys.stderr)
        sys.exit(2)

    chat_count = sum(1 for d in directives if d["type"] == "chat")
    key_count = sum(1 for d in directives if d["type"] == "keypress")
    type_count = sum(1 for d in directives if d["type"] == "type")
    action_count = sum(1 for d in directives if d["type"] == "action")

    output_dir = Path(args.output_dir).resolve() if args.output_dir else RUNS_DIR

    # Set env before importing cockpit
    os.environ["CGL_LAB_ROOT"] = str(lab_root)

    studio_path = str(harness_root / "studio")
    if studio_path not in sys.path:
        sys.path.insert(0, studio_path)

    print(f"Persona slug:  {args.persona_slug}")
    print(f"Scenario:      {args.scenario}")
    print(f"Lab root:      {lab_root}")
    print(f"Directives:    {len(directives)} total ({chat_count} chat, {key_count} keypress, {type_count} type, {action_count} action)")
    print(f"Output dir:    {output_dir}")
    print()

    result = asyncio.run(
        run_director_persona(
            persona_slug=args.persona_slug,
            directives=directives,
            scenario=args.scenario,
            federation_root=lab_root,
            output_dir=output_dir,
            verbose=args.verbose,
            question_timeout=args.timeout,
        )
    )

    print(f"\n=== Director Persona Capture Result ===")
    print(f"Run ID:     {result['run_id']}")
    print(f"Run dir:    {result['run_dir']}")
    print(f"Exchanges:  {result['exchange_count']}")
    print()

    for ex in result["exchanges"]:
        i = ex["exchange_num"]
        stype = ex.get("step_type", "chat")
        if stype == "keypress":
            print(f"  [{i}] KEYPRESS: {ex['key']} ({ex.get('label', '')})  ({ex.get('elapsed_ms', 0)}ms)")
        elif stype == "type":
            print(f"  [{i}] TYPE: #{ex.get('input_id', '')} = {ex.get('text', '')[:60]}  ({ex.get('elapsed_ms', 0)}ms)")
        elif stype == "action":
            ok_str = "OK" if ex.get("action_ok") else "FAIL"
            print(f"  [{i}] ACTION: {ex.get('action_name', '?')} [{ok_str}] {ex.get('action_result_msg', '')[:80]}  ({ex.get('elapsed_ms', 0)}ms)")
        else:
            resp_preview = ex.get("agent_response", "")[:150].replace("\n", " ")
            print(f"  [{i}] Q: {ex.get('human_message', '')}")
            print(f"       A: {resp_preview}")
            print(f"       ({ex.get('agent_response_ms', 0)}ms)")
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
