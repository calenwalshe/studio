"""Dual judges for Examiner sessions.

judge_workflow_completion: did the Examiner accomplish the workflow's intent?
judge_reasoning_quality: did the agent responses meet the system's quality bar?

Both call claude -p with structured-output prompts; both return strict shapes.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Judge system prompts
# ---------------------------------------------------------------------------

WORKFLOW_JUDGE_SYSTEM = """You are a workflow completion judge for the Studio TUI eval harness.

You receive: a workflow definition, an Examiner persona's session transcript, and a working federation directory.

Your job:
1. For EACH canonical step in the workflow, decide if it was executed in the transcript (true/false).
2. For EACH expected_artifact, decide if the file actually exists in the working directory (true/false).
3. Compute an overall score = (executed_steps_count + present_artifacts_count) / (total_steps + total_artifacts).
4. Decide if the workflow PASSED (score >= 0.75 and at least one artifact present).
5. Write a 2-4 sentence reasoning summary.

Output STRICT JSON only:
{
  "score": 0.0-1.0,
  "passed": bool,
  "reasoning": "...",
  "canonical_steps_executed": [bool, ...],
  "expected_artifacts_present": [bool, ...]
}
"""


REASONING_JUDGE_SYSTEM = """You are a reasoning quality judge for the Studio TUI eval harness.

You receive an Examiner persona's session transcript including chat exchanges with the Chief of Staff and Lab Agents.

For EACH chat-type turn in the transcript (where decision.action == 'chat'), evaluate the AGENT's response on:

- scope_discipline: did the agent stay in its scope? Chief at federation-level, Lab Agents on their own lab only.
- evidence_grounded: was each specific claim in the response supported by the lab snapshot? "ok" if grounded, "hallucinated" if invented, "underspecified" if vague.
- honest_about_gaps: did the agent acknowledge limitations (e.g. "I don't have the full claim text") rather than confabulating?
- issues: list specific issues you saw in this response.

Score per response: 1.0 if all 3 dimensions ok and no major issues; 0.5 if minor issue; 0.0 if scope violation or hallucination.

Output STRICT JSON only:
{
  "score": 0.0-1.0,
  "per_response": [
    {"turn": int, "score": 0.0-1.0, "scope_discipline": "ok|violated", "evidence_grounded": "ok|hallucinated|underspecified", "honest_about_gaps": bool, "issues": [...]}
  ]
}
"""


# ---------------------------------------------------------------------------
# Claude subprocess helper
# ---------------------------------------------------------------------------

async def _run_claude_with_json(prompt: str, system: str, timeout: int = 90) -> dict:
    """Subprocess to claude -p, parse JSON from output, retry once on parse failure."""
    full = f"{system}\n\n{prompt}\n\nRespond with ONLY the JSON object. No prose."
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)

    for attempt in range(2):
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", "--output-format", "text", full,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            if attempt == 0:
                continue
            return {"_judge_error": "timeout"}
        raw = stdout.decode("utf-8", errors="replace").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Strip markdown fences if present
            stripped = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
            stripped = re.sub(r"\s*```\s*$", "", stripped, flags=re.MULTILINE)
            try:
                return json.loads(stripped.strip())
            except json.JSONDecodeError:
                pass
            # Fall back to greedy JSON object extraction
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
        if attempt == 0:
            full = (
                full
                + "\n\nReminder: output ONLY a single JSON object. No markdown fences. No prose."
            )
    return {"_judge_error": "failed_to_parse_json"}


# ---------------------------------------------------------------------------
# Artifact pattern resolution
# ---------------------------------------------------------------------------

def _resolve_artifact_pattern(pattern: str, lab_root: Path) -> list[Path]:
    """Resolve <lab>, <claw_id>, <new-bundle-id>, <new-slug>, <federation> tokens.

    Returns a list of candidate Paths. The caller checks any(p.exists() ...).

    Substitution rules:
    - <lab>       -> each non-hidden subdirectory of lab_root
    - <claw_id>   -> each non-hidden bundle under <lab>/.claws/
    - <new-bundle-id> -> same as <claw_id> (alias for clarity in workflow text)
    - <new-slug>  -> each non-hidden subdirectory of lab_root (newly created labs)
    - <federation> -> lab_root itself (strip prefix)
    """
    # Normalise tokens that are semantically identical
    pattern = pattern.replace("<new-bundle-id>", "<claw_id>")
    pattern = pattern.replace("<new-slug>", "<lab>")

    if "<federation>/" in pattern:
        remainder = pattern.replace("<federation>/", "")
        return [lab_root / remainder]

    if "<lab>" in pattern:
        candidates: list[Path] = []
        for lab_dir in lab_root.iterdir():
            if not lab_dir.is_dir() or lab_dir.name.startswith("."):
                continue
            after_lab = pattern.replace("<lab>", lab_dir.name)
            if "<claw_id>" in after_lab:
                claws_dir = lab_dir / ".claws"
                if claws_dir.exists():
                    for bundle_dir in claws_dir.iterdir():
                        if bundle_dir.is_dir() and not bundle_dir.name.startswith("."):
                            final = after_lab.replace("<claw_id>", bundle_dir.name)
                            candidates.append(lab_root / final)
            else:
                candidates.append(lab_root / after_lab)
        return candidates

    # No substitution tokens — treat as a literal path relative to lab_root
    return [lab_root / pattern]


# ---------------------------------------------------------------------------
# Transcript compression helpers
# ---------------------------------------------------------------------------

def _compress_transcript(transcript: list[dict]) -> str:
    """Produce a compact human-readable transcript for judge prompts."""
    lines: list[str] = []
    for t in transcript:
        d = t.get("decision", {})
        action = d.get("action", "?")
        turn = t.get("turn", "?")
        reason = d.get("reason", "")[:80]
        if action == "chat":
            text = d.get("text", "")[:80]
            lines.append(f"Turn {turn}: chat -> {text!r} (reason: {reason})")
        elif action == "done":
            lines.append(f"Turn {turn}: DONE — {reason}")
        else:
            lines.append(f"Turn {turn}: {action} (reason: {reason})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public judges
# ---------------------------------------------------------------------------

async def judge_workflow_completion(
    transcript: list[dict],
    workflow: dict,
    lab_root: Path,
) -> dict:
    """Judge whether the Examiner accomplished the workflow.

    Returns:
        {
            "score": float,
            "passed": bool,
            "reasoning": str,
            "canonical_steps_executed": list[bool],
            "expected_artifacts_present": list[bool],
        }
    """
    expected_artifacts: list[str] = workflow.get("expected_artifact", [])

    # Deterministic filesystem check — overrides whatever the LLM thinks
    artifacts_present: list[bool] = []
    for art in expected_artifacts:
        candidates = _resolve_artifact_pattern(art, lab_root)
        artifacts_present.append(any(p.exists() for p in candidates))

    canonical_steps: list[str] = workflow.get("canonical_steps", [])
    transcript_text = _compress_transcript(transcript)

    prompt = f"""WORKFLOW:
{json.dumps(workflow, indent=2)}

TRANSCRIPT (compact):
{transcript_text}

ARTIFACT PRE-CHECK (filesystem inspected for you — do NOT override these):
{json.dumps(list(zip(expected_artifacts, artifacts_present)), indent=2)}

Evaluate each of the {len(canonical_steps)} canonical_steps against the transcript (true/false per step).
Use the artifact pre-check values verbatim in expected_artifacts_present.
Compute score = (executed_steps + present_artifacts) / (total_steps + total_artifacts).
Pass if score >= 0.75 and at least one artifact is true.
Write 2-4 sentence reasoning."""

    result = await _run_claude_with_json(prompt, WORKFLOW_JUDGE_SYSTEM)

    if "_judge_error" in result:
        # Return a safe fallback that preserves deterministic artifact data
        n_steps = len(canonical_steps)
        steps_bool = [False] * n_steps
        n_art = len(expected_artifacts)
        total = max(n_steps + n_art, 1)
        art_true = sum(artifacts_present)
        score = art_true / total
        return {
            "score": round(score, 3),
            "passed": False,
            "reasoning": f"Judge LLM call failed ({result.get('_judge_error')}). Artifact pre-check: {art_true}/{n_art} present.",
            "canonical_steps_executed": steps_bool,
            "expected_artifacts_present": artifacts_present,
            "_judge_error": result["_judge_error"],
        }

    # Always override the artifact field with our deterministic result
    result["expected_artifacts_present"] = artifacts_present

    # Validate shape — fill missing fields rather than crashing
    if "canonical_steps_executed" not in result:
        result["canonical_steps_executed"] = [False] * len(canonical_steps)
    if "score" not in result:
        steps_true = sum(1 for b in result["canonical_steps_executed"] if b)
        art_true = sum(artifacts_present)
        total = max(len(canonical_steps) + len(expected_artifacts), 1)
        result["score"] = round((steps_true + art_true) / total, 3)
    if "passed" not in result:
        result["passed"] = (
            result["score"] >= 0.75 and any(artifacts_present)
        )
    if "reasoning" not in result:
        result["reasoning"] = "(no reasoning returned by judge)"

    return result


async def judge_reasoning_quality(
    transcript: list[dict],
    lab_root: Path,
) -> dict:
    """Judge each chat-type turn's reasoning quality.

    Returns:
        {
            "score": float,       # mean of per_response scores
            "per_response": [
                {
                    "turn": int,
                    "score": float,
                    "scope_discipline": "ok|violated",
                    "evidence_grounded": "ok|hallucinated|underspecified",
                    "honest_about_gaps": bool,
                    "issues": list[str],
                }
            ]
        }
    """
    chat_turns = [
        (i, t)
        for i, t in enumerate(transcript)
        if t.get("decision", {}).get("action") == "chat"
    ]

    if not chat_turns:
        return {
            "score": 1.0,
            "per_response": [],
            "_note": "no chat turns to judge",
        }

    # Render federation snapshot as the ground-truth reference for the judge
    # We import here to avoid a hard dependency at module load time
    _studio_root = Path(__file__).resolve().parents[2] / "studio"
    if str(_studio_root) not in sys.path:
        sys.path.insert(0, str(_studio_root))

    try:
        from lab_tui.chat_agents import render_federation_snapshot
        snapshot = render_federation_snapshot(lab_root)
    except Exception as exc:
        snapshot = f"(snapshot unavailable: {exc})"

    # Build items list: for each chat turn, the agent's reply is in the NEXT
    # turn's screen (the Examiner captures screen state after each action).
    items: list[dict] = []
    for idx, (i, t) in enumerate(chat_turns):
        human_msg = t.get("decision", {}).get("text", "")
        next_turn = transcript[i + 1] if i + 1 < len(transcript) else None
        agent_reply = (
            next_turn.get("screen", "")[:1500] if next_turn else "(no after-state captured)"
        )
        items.append({
            "turn": t.get("turn", i),
            "human": human_msg[:200],
            "agent_reply": agent_reply,
        })

    prompt = f"""LAB STATE SNAPSHOT (source of truth for grounding claims):
{snapshot}

CHAT TURNS TO JUDGE (human message + agent reply):
{json.dumps(items, indent=2)}

For each turn, judge the agent_reply against the snapshot.
One entry per turn in per_response.
Compute overall score as the mean of per-response scores."""

    result = await _run_claude_with_json(prompt, REASONING_JUDGE_SYSTEM)

    if "_judge_error" in result:
        return {
            "score": 0.0,
            "per_response": [],
            "_judge_error": result["_judge_error"],
        }

    # Validate and repair shape
    per_response = result.get("per_response", [])
    scores = [r.get("score", 0.0) for r in per_response]
    mean_score = sum(scores) / len(scores) if scores else 1.0

    result["score"] = round(mean_score, 3)
    result["per_response"] = per_response
    return result
