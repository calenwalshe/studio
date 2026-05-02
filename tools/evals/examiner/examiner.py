"""Examiner persona — long-running TUI test pilot.

Each invocation = one session. Picks an uncovered workflow from the library,
executes it adaptively, logs findings, updates state. Across many sessions
builds a coverage map and issue ledger.

Run: studio/.venv/bin/python tools/evals/examiner/examiner.py [--max-turns N] [--workflow ID]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TOOLS_DIR = Path(__file__).resolve().parents[2]   # tools/
HARNESS_ROOT = TOOLS_DIR.parent                    # studio-tui/
STATE_DIR = TOOLS_DIR / "evals" / "examiner"
STATE_FILE = STATE_DIR / "state.json"
FINDINGS_FILE = STATE_DIR / "findings.jsonl"
COVERAGE_FILE = STATE_DIR / "coverage.md"
SESSIONS_DIR = STATE_DIR / "sessions"
WORKFLOWS_DIR = TOOLS_DIR / "evals" / "workflows"

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

EXAMINER_IDENTITY = """You are the Examiner — a disciplined, persistent tester of the Studio TUI cockpit.

Your role is NOT a normal director. You are an evaluator with a mandate:
- Methodically exercise every Studio feature
- Cover canonical workflows
- Log every surprise as a finding
- Build a public coverage map across sessions

You hold STATE across sessions. You know what you've tried. You don't repeat work without reason.

Behaviors:
- Pick the workflow to exercise based on uncovered_priority
- Execute it adaptively — read what the agent says, choose your next move
- ALWAYS evaluate: did this surface behave as expected?
- When something surprises you, log a finding
- When you've completed a workflow's intent, declare done

You do NOT pretend to be a user shipping a product. You ARE the system's exam.

Action targeting rules: When you decide to promote, archive_claw, or spawn, you MUST include
`lab_id` (the lab id from the table) and for claw-targeted actions `claw_index` (0-based integer,
default 0 = first claw shown in the expansion). For promote, optionally specify `outcome`; if you
say `auto` or omit it, the action defaults to the claw's own promotion_recommendation. For
archive_lab, include `lab_id`. Omitting these fields causes the action to fail with a logged
error — the next turn will show you what happened."""

# ---------------------------------------------------------------------------
# State dataclass
# ---------------------------------------------------------------------------


@dataclass
class ExaminerState:
    started_at: str
    session_count: int
    workflows_covered: list[str]
    workflows_remaining: list[str]
    features_exercised: dict[str, int]   # {feature_name: usage_count}
    open_issues: list[str]               # finding ids
    next_session_priority: Optional[str] = None  # workflow id or None for auto-pick


def _default_state(workflow_ids: list[str]) -> ExaminerState:
    return ExaminerState(
        started_at=datetime.now(timezone.utc).isoformat(),
        session_count=0,
        workflows_covered=[],
        workflows_remaining=list(workflow_ids),
        features_exercised={},
        open_issues=[],
        next_session_priority=None,
    )


def _state_to_dict(s: ExaminerState) -> dict:
    return {
        "started_at": s.started_at,
        "session_count": s.session_count,
        "workflows_covered": s.workflows_covered,
        "workflows_remaining": s.workflows_remaining,
        "features_exercised": s.features_exercised,
        "open_issues": s.open_issues,
        "next_session_priority": s.next_session_priority,
    }


def _state_from_dict(d: dict) -> ExaminerState:
    return ExaminerState(
        started_at=d.get("started_at", ""),
        session_count=d.get("session_count", 0),
        workflows_covered=d.get("workflows_covered", []),
        workflows_remaining=d.get("workflows_remaining", []),
        features_exercised=d.get("features_exercised", {}),
        open_issues=d.get("open_issues", []),
        next_session_priority=d.get("next_session_priority"),
    )


# ---------------------------------------------------------------------------
# State I/O
# ---------------------------------------------------------------------------


def load_workflows() -> list[dict]:
    """Load all YAMLs from tools/evals/workflows/."""
    if not WORKFLOWS_DIR.exists():
        return []
    workflows = []
    for path in sorted(WORKFLOWS_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                workflows.append(data)
        except Exception:
            pass
    return workflows


def load_state() -> ExaminerState:
    """Init or load state.json. If missing, scan workflows/ to seed remaining list."""
    workflow_ids = [w.get("id", "") for w in load_workflows() if w.get("id")]
    if not STATE_FILE.exists():
        return _default_state(workflow_ids)
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        state = _state_from_dict(raw)
        # Merge in any new workflow ids not yet tracked
        all_known = set(state.workflows_covered) | set(state.workflows_remaining)
        for wid in workflow_ids:
            if wid not in all_known:
                state.workflows_remaining.append(wid)
        return state
    except Exception:
        return _default_state(workflow_ids)


def save_state(state: ExaminerState) -> None:
    """Write state.json atomically."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(_state_to_dict(state), indent=2), encoding="utf-8")
    tmp.rename(STATE_FILE)


# ---------------------------------------------------------------------------
# Workflow selection
# ---------------------------------------------------------------------------


def pick_next_workflow(state: ExaminerState, workflows: list[dict]) -> dict:
    """Return the next workflow to run.

    Priority: workflows_remaining first, then round-robin covered.
    Falls back to first workflow if lists are empty.
    """
    if not workflows:
        raise ValueError("No workflows found in tools/evals/workflows/")

    # Honor next_session_priority if set
    if state.next_session_priority:
        match = next((w for w in workflows if w.get("id") == state.next_session_priority), None)
        if match:
            return match

    # Next uncovered
    if state.workflows_remaining:
        wid = state.workflows_remaining[0]
        match = next((w for w in workflows if w.get("id") == wid), None)
        if match:
            return match

    # Round-robin covered
    if state.workflows_covered:
        # Pick the one least recently done (first in covered list = oldest)
        for wid in state.workflows_covered:
            match = next((w for w in workflows if w.get("id") == wid), None)
            if match:
                return match

    return workflows[0]


# ---------------------------------------------------------------------------
# Finding ID generator
# ---------------------------------------------------------------------------


def _current_max_finding_id() -> int:
    """Read findings.jsonl to find the highest F-NNN id."""
    if not FINDINGS_FILE.exists():
        return 0
    max_id = 0
    try:
        for line in FINDINGS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                fid = obj.get("id", "")
                m = re.match(r"F-(\d+)", str(fid))
                if m:
                    max_id = max(max_id, int(m.group(1)))
            except Exception:
                pass
    except Exception:
        pass
    return max_id


_finding_counter: list[int] = []  # mutable singleton, initialized per session


def _init_finding_counter() -> None:
    _finding_counter.clear()
    _finding_counter.append(_current_max_finding_id())


def next_finding_id() -> str:
    _finding_counter[0] += 1
    return f"F-{_finding_counter[0]:03d}"


# ---------------------------------------------------------------------------
# Screen serialization
# ---------------------------------------------------------------------------


def _scope_key(scope: dict) -> str:
    """Mirror of DirectorChat's internal scope-key derivation."""
    if scope.get("kind") == "chief":
        return "chief"
    return f"lab:{scope.get('lab_id', 'unknown')}"


def _append_chat_transcript(app, screen_text: str) -> str:
    """Read DirectorChat._histories directly from the live app and append the
    most recent turns of conversation to the screen text. The PaginatedTranscript
    widget doesn't expose its content via SVG export reliably; pulling from
    _histories is the source of truth.
    """
    try:
        harness_studio = HARNESS_ROOT / "studio"
        if str(harness_studio) not in sys.path:
            sys.path.insert(0, str(harness_studio))
        from lab_tui.cockpit import DirectorChat
        chats = list(app.query(DirectorChat))
        if not chats:
            return screen_text + "\n[chat: no DirectorChat widget found]"
        chat = chats[0]
        scope = chat._scope
        history = chat._histories.get(_scope_key(scope), [])

        block = ["", "=== CHAT TRANSCRIPT (live, from DirectorChat._history) ==="]
        scope_label = "Chief of Staff" if scope.get("kind") == "chief" else f"Lab Agent: {scope.get('lab_id', '?')}"
        block.append(f"Current scope: {scope_label}")
        if not history:
            block.append("(empty — no exchanges in this scope yet)")
        else:
            # Show last 4 turns (8 messages = 4 q/a pairs)
            for turn in history[-8:]:
                role = turn.get("role", "?")
                content = turn.get("content", "")
                if len(content) > 600:
                    content = content[:600] + " [...truncated]"
                block.append(f"\n{role}: {content}")
        block.append("=== END CHAT TRANSCRIPT ===")
        return screen_text + "\n" + "\n".join(block)
    except Exception as e:
        return screen_text + f"\n[chat transcript read failed: {e}]"


def _extract_widget_text(widget) -> str:
    """Extract human-readable text from a widget. Handles Static, Label, RichLog,
    nested children. Avoids SVG / CSS leakage by NOT calling export_screenshot.
    """
    out = []

    # If this widget itself has renderable text:
    rend = getattr(widget, "renderable", None)
    if rend is not None:
        # Rich Text or string
        if hasattr(rend, "plain"):
            out.append(rend.plain)
        elif isinstance(rend, str):
            out.append(rend)
        else:
            try:
                out.append(str(rend))
            except Exception:
                pass

    # Walk children — but cap depth + breadth to avoid runaway
    try:
        for child in widget.children[:30]:  # breadth cap
            child_text = _extract_widget_text(child)
            if child_text:
                out.append(child_text)
    except Exception:
        pass

    text = "\n".join(o for o in out if o)
    # Sanitize: no SVG, no @font-face. If we somehow get markup, strip it.
    if "@font-face" in text or "<svg" in text:
        text = ""  # Drop entirely — would poison the LLM's context
    return text


def serialize_screen_for_examiner(app) -> str:
    """Walk the live widget tree and produce a director-readable text snapshot.

    Replaces the prior SVG-export approach which leaked @font-face CSS into the
    output. We walk the focused screen's mounted widgets in DOM order and call
    each widget's render() text — Textual widgets expose readable content via
    Static.renderable, Header.title, Footer bindings, DataTable cells, RichLog
    lines, and PaginatedTranscript blocks.
    """
    parts = []

    # Header / title
    parts.append(f"=== {app.title or 'Studio Cockpit'} ===")
    if hasattr(app, "sub_title") and app.sub_title:
        parts.append(f"subtitle: {app.sub_title}")

    # Status strip — the LabHeaderStrip widget
    try:
        harness_studio = HARNESS_ROOT / "studio"
        if str(harness_studio) not in sys.path:
            sys.path.insert(0, str(harness_studio))
        from lab_tui.cockpit import LabHeaderStrip
        for strip in app.query(LabHeaderStrip):
            text = _extract_widget_text(strip)
            if text:
                parts.append(f"\n[header strip] {text}")
    except Exception:
        pass

    # Lab list — walk LabRows in order
    try:
        from lab_tui.cockpit import LabList, LabRow
        lab_lists = list(app.query(LabList))
        if lab_lists:
            parts.append(f"\n[LabList — {len(list(lab_lists[0].query(LabRow)))} rows]")
            parts.append(f"focus: {'lab list' if lab_lists[0].has_focus_within else 'elsewhere'}")
            for row in lab_lists[0].query(LabRow):
                lab_id = getattr(row, "lab_id", "?")
                expanded = getattr(row, "expanded", False) or row.has_class("expanded")
                row_focus = ">" if row.has_focus else " "
                parts.append(f"  {row_focus} {'[v]' if expanded else '[>]'} {lab_id}")
                if expanded:
                    body_text = _extract_widget_text(row)
                    # Indent the body
                    for line in body_text.splitlines():
                        if line.strip():
                            parts.append(f"      {line}")
    except Exception as e:
        parts.append(f"[lablist read failed: {e}]")

    # Chat pane (use the existing _append_chat_transcript helper which already works)
    base = "\n".join(parts)
    return _append_chat_transcript(app, base)


# ---------------------------------------------------------------------------
# LLM call — claude -p
# ---------------------------------------------------------------------------


async def _run_claude(prompt: str, timeout: int = 60) -> str:
    """Run claude -p with a prompt string, return stdout."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "env", "-u", "ANTHROPIC_API_KEY",
            "claude", "-p", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return '{"action":"done","reason":"LLM timeout","findings":[],"workflow_progress":"done"}'
        return stdout.decode("utf-8", errors="replace").strip()
    except Exception as exc:
        return f'{{"action":"done","reason":"LLM error: {exc}","findings":[],"workflow_progress":"done"}}'


def parse_decision(raw: str) -> dict:
    """Parse the Examiner LLM JSON response. Returns safe defaults on failure."""
    # Strip markdown code fences if present
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        inner = [l for l in lines if not l.startswith("```")]
        raw = "\n".join(inner).strip()

    try:
        return json.loads(raw)
    except Exception:
        # Try to extract JSON object from the text
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
        return {
            "action": "done",
            "reason": f"parse error: {raw[:100]}",
            "findings": [],
            "workflow_progress": "done",
        }


def build_examiner_prompt(
    workflow: dict,
    state: ExaminerState,
    screen: str,
    history: list[dict],
    turn_count: int,
    turns_remaining: int,
) -> str:
    """Construct the Examiner's per-turn prompt.

    Includes: identity, current workflow + intent + canonical_steps, current
    screen, last 3 turns of context, state summary (covered workflows, open
    issues count), turn budget remaining.

    Output format strict: JSON only, no prose.
    """
    covered = ", ".join(state.workflows_covered) or "(none yet)"
    open_count = len(state.open_issues)
    feat_summary = json.dumps(state.features_exercised) if state.features_exercised else "{}"

    canonical = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(workflow.get("canonical_steps", [])))
    exercises = ", ".join(workflow.get("exercises", []))
    expected = "\n".join(f"  - {a}" for a in workflow.get("expected_artifact", []))
    notes = workflow.get("notes_to_persona", "")

    history_text = ""
    if history:
        history_text = "LAST TURNS:\n"
        for t in history:
            dec = t.get("decision", {})
            history_text += f"  Turn {t.get('turn','?')}: action={dec.get('action','?')} progress={dec.get('workflow_progress','?')}\n"
            if dec.get("reason"):
                history_text += f"    reason: {dec['reason'][:100]}\n"

    return f"""{EXAMINER_IDENTITY}

---
CURRENT SESSION STATE
  Session #:         {state.session_count + 1}
  Turn:              {turn_count} / budget {turn_count + turns_remaining}
  Turns remaining:   {turns_remaining}
  Workflows covered: {covered}
  Open issues:       {open_count}
  Features exercised this session: {feat_summary}

---
ACTIVE WORKFLOW
  ID:      {workflow.get('id', '?')}
  Name:    {workflow.get('name', '?')}
  Intent:  {workflow.get('intent', '?')}
  Exercises: {exercises}

Canonical steps:
{canonical}

Expected artifacts:
{expected}

Notes to persona: {notes}

---
CURRENT SCREEN (truncated to 2000 chars):
{screen[:2000]}

---
{history_text}

---
OUTPUT RULES — STRICT:
Respond with ONLY valid JSON. No prose. No markdown. No explanation outside the JSON.

{{
  "action": "<one of: chat | keypress | expand | view_result | promote | archive_claw | spawn | create_lab | archive_lab | done>",
  "text": "<chat message to send, only for action=chat>",
  "key": "<textual key name, only for action=keypress>",
  "lab_id": "<lab slug, for expand/create_lab/archive_lab/spawn>",
  "claw_index": <integer, for view_result/promote/archive_claw>,
  "outcome": "<promotion outcome, for promote: abandon|keep_evidence|continue|merge|publish|graduate_to_spine>",
  "spawn_role": "<role string, for spawn>",
  "spawn_orientation_id": "<orientation id, for spawn>",
  "create_lab_args": {{"slug":"...","kind":"...","title":"...","objective":"..."}},
  "reason": "<one sentence: why this action right now>",
  "findings": [
    {{
      "severity": "<low|medium|high|critical>",
      "kind": "<bug|ux|missing_feature|unexpected_behavior|wrong_output>",
      "summary": "<short description>",
      "evidence": "<what you observed on screen>"
    }}
  ],
  "workflow_progress": "<intro|midway|near-done|done>"
}}

Omit keys that don't apply to the chosen action. The "findings" list may be empty [].
If you have completed the workflow intent OR exhausted the turn budget, set action=done.
"""


async def ask_examiner(
    *,
    workflow: dict,
    state: ExaminerState,
    screen: str,
    history: list[dict],
    turn_count: int,
    turns_remaining: int,
) -> dict:
    """One call to claude -p. Returns decision dict."""
    prompt = build_examiner_prompt(workflow, state, screen, history, turn_count, turns_remaining)
    raw = await _run_claude(prompt, timeout=60)
    return parse_decision(raw)


# ---------------------------------------------------------------------------
# Screenshot save helper
# ---------------------------------------------------------------------------


async def _save_screenshot(app, session_dir: Path, turn: int, phase: str) -> Path:
    """Export SVG + PNG to session_dir. Returns PNG path."""
    try:
        import cairosvg
        svg_text = app.export_screenshot()
        svg_path = session_dir / f"turn-{turn:03d}-{phase}.svg"
        png_path = session_dir / f"turn-{turn:03d}-{phase}.png"
        svg_path.write_text(svg_text, encoding="utf-8")
        cairosvg.svg2png(url=str(svg_path), write_to=str(png_path), output_width=1600)
        return png_path
    except Exception as exc:
        # Write an error placeholder so callers don't crash
        fallback = session_dir / f"turn-{turn:03d}-{phase}.txt"
        fallback.write_text(f"screenshot error: {exc}", encoding="utf-8")
        return fallback


# ---------------------------------------------------------------------------
# Feature name mapper
# ---------------------------------------------------------------------------


def feature_name_for_action(decision: dict) -> str:
    action = decision.get("action", "unknown")
    mapping = {
        "chat": "chief_chat",
        "keypress": f"keypress_{decision.get('key', 'unknown')}",
        "expand": "lab_expansion",
        "view_result": "view_result",
        "promote": "promote_action",
        "archive_claw": "archive_claw",
        "spawn": "spawn_dry_run",
        "create_lab": "create_lab",
        "archive_lab": "archive_lab",
        "done": "session_done",
    }
    return mapping.get(action, action)


# ---------------------------------------------------------------------------
# Action executor
# ---------------------------------------------------------------------------


async def execute_action(pilot, app, decision: dict, work_root: Path) -> bool:
    """Translate decision to actual TUI action. Returns True on success."""
    action = decision.get("action", "done")

    try:
        # Lazy import inside the async context where app is live
        harness_studio = HARNESS_ROOT / "studio"
        if str(harness_studio) not in sys.path:
            sys.path.insert(0, str(harness_studio))

        from lab_tui.actions import (
            apply_decision as _apply_decision,
            archive_claw as _archive_claw,
            archive_lab as _archive_lab,
            create_lab as _create_lab,
            spawn_dry_run_claw as _spawn_dry_run_claw,
        )
        from lab_tui.cockpit import DirectorChat, LabList, LabRow
        from textual.widgets import Input

        # ----------------------------------------------------------------
        if action == "chat":
            text = decision.get("text", "")
            if not text:
                return False

            chat_pane = app.query_one(DirectorChat)

            # send_message is async and waits internally for the agent reply
            # before returning (_thinking goes False, history appended).
            # We await it directly; the 90-second outer limit is enforced by
            # asyncio.wait_for so a hung agent doesn't stall the session forever.
            try:
                await asyncio.wait_for(chat_pane.send_message(text), timeout=90)
            except asyncio.TimeoutError:
                # Reply didn't arrive in time — poll once more then continue
                pass

            await pilot.pause()
            await asyncio.sleep(0.5)
            return True

        # ----------------------------------------------------------------
        elif action == "keypress":
            key = decision.get("key", "")
            if not key:
                return False

            # Focus lab list for nav keys
            chat_input = app.query_one("#chat-input", Input)
            if chat_input.has_focus:
                rows = list(app.query(LabRow))
                if rows:
                    lab_list_w = app.query_one("#lab-list", LabList)
                    idx = lab_list_w.focused_index() if hasattr(lab_list_w, "focused_index") else 0
                    app.set_focus(rows[min(idx, len(rows) - 1)])
                await pilot.pause()

            await pilot.press(key)
            await pilot.pause()
            await asyncio.sleep(0.5)
            return True

        # ----------------------------------------------------------------
        elif action == "expand":
            lab_id = decision.get("lab_id", "")
            lab_list_w = app.query_one("#lab-list", LabList)
            rows = list(app.query(LabRow))
            target = next((r for r in rows if r.lab_id == lab_id), None)
            if target is None:
                return False
            for row in rows:
                if row is not target and row.expanded:
                    row.collapse()
            app.set_focus(target)
            await pilot.pause()
            if not target.expanded:
                lab_list_w.toggle_focused()
            await pilot.pause()
            await asyncio.sleep(0.5)
            return target.expanded

        # ----------------------------------------------------------------
        elif action == "view_result":
            lab_list_w = app.query_one("#lab-list", LabList)
            focused_row = lab_list_w.focused_row() if hasattr(lab_list_w, "focused_row") else None
            if focused_row and focused_row.expanded:
                claw_index = decision.get("claw_index", 0)
                # Scroll selection to desired claw index
                for _ in range(claw_index):
                    await pilot.press("j")
                    await pilot.pause()
                claw = focused_row.selected_claw()
                if claw:
                    claw_dir = focused_row._summary.lab_root / ".claws" / claw.bundle_id
                    result_file = claw_dir / "result.md"
                    _ = result_file.read_text(encoding="utf-8") if result_file.exists() else "(no result.md)"
                    return True
            return False

        # ----------------------------------------------------------------
        elif action == "promote":
            # MODAL BYPASS — resolve lab + claw from decision dict directly,
            # falling back to focused UI row only if lab_id is absent.
            try:
                from lab_tui.loaders import load_lab_summary as _load_lab_summary

                lab_id = decision.get("lab_id")
                claw_index = int(decision.get("claw_index", 0))

                if lab_id:
                    target_lab_root = work_root / lab_id
                    summary = _load_lab_summary(target_lab_root)
                    if not summary.bundles or claw_index >= len(summary.bundles):
                        decision["_action_result"] = {
                            "success": False,
                            "message": f"claw_index {claw_index} out of range (lab has {len(summary.bundles)} bundles)",
                        }
                        return False
                    claw = summary.bundles[claw_index]
                    claw_dir = target_lab_root / ".claws" / claw.bundle_id
                else:
                    # Fallback: try focused UI row
                    lab_list_w = app.query_one("#lab-list", LabList)
                    focused_row = lab_list_w.focused_row() if hasattr(lab_list_w, "focused_row") else None
                    if not (focused_row and focused_row.expanded):
                        decision["_action_result"] = {
                            "success": False,
                            "message": "promote requires lab_id in decision dict (no focused expanded row)",
                        }
                        return False
                    claw = focused_row.selected_claw()
                    if not claw:
                        decision["_action_result"] = {"success": False, "message": "no claw selected"}
                        return False
                    claw_dir = focused_row._summary.lab_root / ".claws" / claw.bundle_id

                outcome = decision.get("outcome") or ""
                if not outcome or outcome == "auto":
                    outcome = claw.promotion_recommendation or "keep_evidence"

                res = _apply_decision(claw_dir, outcome)
                decision["_action_result"] = {
                    "success": res.success,
                    "message": res.message,
                    "path": str(res.artifact_path) if res.artifact_path else None,
                }
                if res.success:
                    app.action_refresh()
                    await pilot.pause()
                    await asyncio.sleep(0.5)
                return res.success
            except Exception as exc:
                decision["_action_result"] = {"success": False, "message": f"exception: {exc}"}
                return False

        # ----------------------------------------------------------------
        elif action == "archive_claw":
            # MODAL BYPASS — resolve lab + claw from decision dict directly.
            try:
                from lab_tui.loaders import load_lab_summary as _load_lab_summary

                lab_id = decision.get("lab_id")
                claw_index = int(decision.get("claw_index", 0))

                if lab_id:
                    target_lab_root = work_root / lab_id
                    summary = _load_lab_summary(target_lab_root)
                    if not summary.bundles or claw_index >= len(summary.bundles):
                        decision["_action_result"] = {
                            "success": False,
                            "message": f"claw_index {claw_index} out of range (lab has {len(summary.bundles)} bundles)",
                        }
                        return False
                    claw = summary.bundles[claw_index]
                    claw_dir = target_lab_root / ".claws" / claw.bundle_id
                else:
                    # Fallback: try focused UI row
                    lab_list_w = app.query_one("#lab-list", LabList)
                    focused_row = lab_list_w.focused_row() if hasattr(lab_list_w, "focused_row") else None
                    if not (focused_row and focused_row.expanded):
                        decision["_action_result"] = {
                            "success": False,
                            "message": "archive_claw requires lab_id in decision dict (no focused expanded row)",
                        }
                        return False
                    claw = focused_row.selected_claw()
                    if not claw:
                        decision["_action_result"] = {"success": False, "message": "no claw selected"}
                        return False
                    claw_dir = focused_row._summary.lab_root / ".claws" / claw.bundle_id

                res = _archive_claw(claw_dir)
                decision["_action_result"] = {
                    "success": res.success,
                    "message": res.message,
                    "path": str(res.artifact_path) if res.artifact_path else None,
                }
                if res.success:
                    app.action_refresh()
                    await pilot.pause()
                    await asyncio.sleep(0.5)
                return res.success
            except Exception as exc:
                decision["_action_result"] = {"success": False, "message": f"exception: {exc}"}
                return False

        # ----------------------------------------------------------------
        elif action == "spawn":
            try:
                lab_list_w = app.query_one("#lab-list", LabList)
                focused_row = lab_list_w.focused_row() if hasattr(lab_list_w, "focused_row") else None
                orientation_id = decision.get("spawn_orientation_id", "")
                role = decision.get("spawn_role", "reviewer")
                lab_id = decision.get("lab_id", "")
                if lab_id:
                    spawn_lab_root = work_root / lab_id
                elif focused_row:
                    spawn_lab_root = focused_row._summary.lab_root
                else:
                    decision["_action_result"] = {
                        "success": False,
                        "message": "spawn requires lab_id in decision dict",
                    }
                    return False
                if not orientation_id:
                    # Auto-pick first orientation
                    from lab_tui.loaders import load_lab_summary as _load_lab_summary
                    summary = _load_lab_summary(spawn_lab_root)
                    if not summary.orientations:
                        decision["_action_result"] = {
                            "success": False,
                            "message": f"no orientations found in lab {lab_id}",
                        }
                        return False
                    orientation_id = summary.orientations[0].id
                res = _spawn_dry_run_claw(spawn_lab_root, orientation_id, role, harness_root=HARNESS_ROOT)
                decision["_action_result"] = {
                    "success": res.success,
                    "message": res.message,
                    "path": str(res.artifact_path) if res.artifact_path else None,
                }
                if res.success:
                    app.action_refresh()
                    await pilot.pause()
                    await asyncio.sleep(0.5)
                return res.success
            except Exception as exc:
                decision["_action_result"] = {"success": False, "message": f"exception: {exc}"}
                return False

        # ----------------------------------------------------------------
        elif action == "create_lab":
            try:
                args = decision.get("create_lab_args", {})
                res = _create_lab(
                    work_root,
                    slug=args.get("slug", "examiner-test-lab"),
                    kind=args.get("kind", "investigation"),
                    title=args.get("title", "Examiner Test Lab"),
                    objective=args.get("objective", "Created by Examiner during testing"),
                )
                decision["_action_result"] = {
                    "success": res.success,
                    "message": res.message,
                    "path": str(res.artifact_path) if res.artifact_path else None,
                }
                await asyncio.sleep(0.3)
                return res.success
            except Exception as exc:
                decision["_action_result"] = {"success": False, "message": f"exception: {exc}"}
                return False

        # ----------------------------------------------------------------
        elif action == "archive_lab":
            try:
                lab_id = decision.get("lab_id", "")
                if not lab_id:
                    lab_list_w = app.query_one("#lab-list", LabList)
                    focused_row = lab_list_w.focused_row() if hasattr(lab_list_w, "focused_row") else None
                    if focused_row:
                        lab_id = focused_row.lab_id
                if not lab_id:
                    decision["_action_result"] = {
                        "success": False,
                        "message": "archive_lab requires lab_id in decision dict",
                    }
                    return False
                res = _archive_lab(work_root, lab_id)
                decision["_action_result"] = {
                    "success": res.success,
                    "message": res.message,
                    "path": str(res.artifact_path) if res.artifact_path else None,
                }
                await asyncio.sleep(0.3)
                return res.success
            except Exception as exc:
                decision["_action_result"] = {"success": False, "message": f"exception: {exc}"}
                return False

        # ----------------------------------------------------------------
        elif action == "done":
            return True

        return False

    except Exception as exc:
        print(f"  [execute_action] error: {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Coverage doc
# ---------------------------------------------------------------------------


def update_coverage_doc(state: ExaminerState, manifest: dict) -> None:
    """Rebuild coverage.md from state.json — idempotent."""
    workflow_judgment = manifest.get("workflow_judgment", {})
    quality_judgment = manifest.get("quality_judgment", {})

    lines = [
        "# Examiner Coverage",
        "",
        f"_Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_",
        "",
        f"Sessions run: {state.session_count}",
        f"Open issues: {len(state.open_issues)}",
        "",
        "## Workflow Coverage",
        "",
        "| Workflow | Status |",
        "|----------|--------|",
    ]

    all_wids = list(state.workflows_covered) + list(state.workflows_remaining)
    for wid in all_wids:
        status = "covered" if wid in state.workflows_covered else "pending"
        lines.append(f"| {wid} | {status} |")

    lines += [
        "",
        "## Features Exercised",
        "",
        "| Feature | Uses |",
        "|---------|------|",
    ]
    for feat, count in sorted(state.features_exercised.items(), key=lambda x: -x[1]):
        lines.append(f"| {feat} | {count} |")

    lines += [
        "",
        "## Last Session",
        "",
        f"- Session ID: {manifest.get('session_id', '?')}",
        f"- Workflow: {manifest.get('workflow_id', '?')}",
        f"- Turns: {manifest.get('turns', '?')}",
        f"- Findings: {len(manifest.get('findings', []))}",
    ]

    if workflow_judgment:
        lines += [
            "",
            "### Workflow Judgment",
            f"- Passed: {workflow_judgment.get('passed', '?')}",
            f"- Score: {workflow_judgment.get('score', '?')}",
            f"- Reasoning: {str(workflow_judgment.get('reasoning', ''))[:200]}",
        ]

    if quality_judgment:
        lines += [
            "",
            "### Quality Judgment",
            f"- Score: {quality_judgment.get('score', '?')}",
        ]

    lines.append("")

    COVERAGE_FILE.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Core session runner
# ---------------------------------------------------------------------------


async def run_session(workflow: dict, state: ExaminerState, max_turns: int = 30) -> dict:
    """Run one Examiner session against a workflow. Returns session manifest dict."""
    # Set up working directory — fresh copy of federation-demo each session
    work_root = Path("/tmp/examiner-fed-work")
    if work_root.exists():
        shutil.rmtree(work_root)
    federation_source = HARNESS_ROOT / "examples" / "federation-demo"
    shutil.copytree(str(federation_source), str(work_root))

    session_id = (
        datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        + f"-examiner-{workflow['id']}"
    )
    session_dir = SESSIONS_DIR / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    _init_finding_counter()

    transcript: list[dict] = []
    findings: list[dict] = []
    features_this_session: dict[str, int] = {}
    started_at = datetime.now(timezone.utc).isoformat()

    # Set env before importing cockpit
    os.environ["CGL_LAB_ROOT"] = str(work_root)
    studio_path = str(HARNESS_ROOT / "studio")
    if studio_path not in sys.path:
        sys.path.insert(0, studio_path)

    from lab_tui.cockpit import CockpitApp

    app = CockpitApp()

    async with app.run_test(size=(200, 50)) as pilot:
        await pilot.pause(0.5)
        await asyncio.sleep(1)

        for turn in range(max_turns):
            # Capture before screenshot
            before_path = await _save_screenshot(app, session_dir, turn, "before")

            # Read screen (chat transcript appended inside serialize_screen_for_examiner)
            screen_text = serialize_screen_for_examiner(app)

            # Ask Examiner LLM what to do
            decision = await ask_examiner(
                workflow=workflow,
                state=state,
                screen=screen_text,
                history=transcript[-3:],
                turn_count=turn,
                turns_remaining=max_turns - turn,
            )

            transcript.append({
                "turn": turn,
                "screen": screen_text[:500],
                "decision": decision,
                "before_screenshot": before_path.name,
            })

            # Log findings the Examiner declared this turn
            for f in decision.get("findings", []):
                f = dict(f)
                f["id"] = next_finding_id()
                f["session"] = session_id
                f["workflow"] = workflow["id"]
                f["turn"] = turn
                findings.append(f)
                state.open_issues.append(f["id"])

            if decision.get("action") == "done":
                transcript[-1]["completion_reason"] = decision.get("reason", "")
                break

            # Execute action
            success = await execute_action(pilot, app, decision, work_root)
            transcript[-1]["action_success"] = success

            # Capture after screenshot
            after_path = await _save_screenshot(app, session_dir, turn, "after")
            transcript[-1]["after_screenshot"] = after_path.name

            # Track feature usage
            feat = feature_name_for_action(decision)
            state.features_exercised[feat] = state.features_exercised.get(feat, 0) + 1
            features_this_session[feat] = features_this_session.get(feat, 0) + 1

            await pilot.pause(0.3)

    ended_at = datetime.now(timezone.utc).isoformat()

    # Run judges if available (other agent provides these)
    workflow_judgment: dict = {}
    quality_judgment: dict = {}
    try:
        # Ensure HARNESS_ROOT is in sys.path so tools.evals.judges is importable
        # regardless of how the script was invoked.
        if str(HARNESS_ROOT) not in sys.path:
            sys.path.insert(0, str(HARNESS_ROOT))
        from tools.evals.judges import judge_workflow_completion, judge_reasoning_quality  # noqa: E402
        workflow_judgment = await judge_workflow_completion(transcript, workflow, work_root)
        quality_judgment = await judge_reasoning_quality(transcript, work_root)
    except ImportError:
        workflow_judgment = {
            "score": 0.0,
            "reasoning": "judges.py not yet available (Build B pending)",
            "passed": False,
        }
        quality_judgment = {
            "score": 0.0,
            "per_response": [],
        }
    except Exception as exc:
        workflow_judgment = {"score": 0.0, "reasoning": f"judge error: {exc}", "passed": False}
        quality_judgment = {"score": 0.0, "per_response": []}

    # Append findings to findings.jsonl
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with FINDINGS_FILE.open("a", encoding="utf-8") as fh:
        for finding in findings:
            fh.write(json.dumps(finding) + "\n")

    manifest = {
        "session_id": session_id,
        "workflow_id": workflow["id"],
        "started_at": started_at,
        "ended_at": ended_at,
        "turns": len(transcript),
        "transcript": transcript,
        "findings": findings,
        "workflow_judgment": workflow_judgment,
        "quality_judgment": quality_judgment,
        "features_exercised_this_session": features_this_session,
    }

    (session_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Update state: mark workflow covered if judgment passed
    if workflow_judgment.get("passed"):
        wid = workflow["id"]
        if wid not in state.workflows_covered:
            state.workflows_covered.append(wid)
        if wid in state.workflows_remaining:
            state.workflows_remaining.remove(wid)
    state.session_count += 1
    # Clear next_session_priority once consumed
    state.next_session_priority = None
    save_state(state)

    # Rebuild coverage doc
    update_coverage_doc(state, manifest)

    return manifest


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Examiner — persistent Studio TUI test pilot."
    )
    parser.add_argument("--max-turns", type=int, default=30, help="Turn budget per session.")
    parser.add_argument("--workflow", help="Force specific workflow id.")
    args = parser.parse_args()

    state = load_state()
    workflows = load_workflows()

    if not workflows:
        print("No workflows found in tools/evals/workflows/. Build B hasn't delivered them yet.")
        print("State initialised, no session run.")
        save_state(state)
        return

    workflow = pick_next_workflow(state, workflows)
    if args.workflow:
        workflow = next((w for w in workflows if w.get("id") == args.workflow), workflow)

    print(f"Session #{state.session_count + 1}: workflow={workflow['id']} ({workflow.get('name', '?')})")
    print(f"  Max turns: {args.max_turns}")
    print(f"  Work root: /tmp/examiner-fed-work")
    print()

    manifest = await run_session(workflow, state, max_turns=args.max_turns)

    print(f"Done. Turns used: {manifest['turns']}")
    print(f"Findings logged: {len(manifest['findings'])}")
    wj = manifest.get("workflow_judgment", {})
    print(f"Workflow judgment passed: {wj.get('passed', '?')}")
    print(f"Session dir: {SESSIONS_DIR / manifest['session_id']}")
    print(f"Coverage doc: {COVERAGE_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
