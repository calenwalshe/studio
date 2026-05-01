"""Director agent — Claude subprocess that acts as the human director's delegate.

Reads lab state via the loaders module and answers director questions.
Each invocation is one-shot (claude -p), with conversation history packed
into the prompt for continuity.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure lab_tui siblings are importable when this module is run directly
_MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(_MODULE_ROOT / "studio") not in sys.path:
    sys.path.insert(0, str(_MODULE_ROOT / "studio"))

from lab_tui.loaders import discover_labs, LabSummary  # noqa: E402


DIRECTOR_SYSTEM = """You are the Director Agent for Studio — a human-in-the-loop lab operating system.

You are the human director's delegate. The human talks to you in plain language and you act on their behalf. You have full read access to all lab state and you can describe it, summarize it, recommend actions, or surface what needs decision.

Your tone:
- Concise. Director time is expensive.
- Cite specifics from the lab state (lab id, claw id, claim id, recommendation) so the human can verify.
- When recommending an action, name the action and the smallest next step. Do not produce wall-of-text plans.
- Distinguish between what you SEE (state) and what you RECOMMEND (judgment). Use markdown.
- If asked something you don't have data for, say so. Do not guess.

You CANNOT take actions yet — Studio's promotion mutations are not implemented in v0. You can only read state and recommend. If asked to do something, describe what you would do and ask the human to approve.

The lab state available to you is in the LAB STATE SNAPSHOT below. It is a structured summary of every lab in the federation including orientations, claws, evidence claims, and trace events. Use it as the source of truth."""


def _read_jsonl_records(path: Path, limit: int = 5) -> list[dict]:
    """Read up to `limit` records from a .jsonl file. Returns [] if missing."""
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(records) >= limit:
                break
    return records


def render_lab_snapshot(federation_root: Path) -> str:
    """Render full lab state as a director-readable text block.

    Includes: each lab's id/kind/status/orientation/claws + for each claw the
    promotion recommendation, claim count, trace event count, the first line of
    result.md, and sample claims from evidence.jsonl.
    """
    summaries = discover_labs(federation_root)
    if not summaries:
        return "(no labs found in federation)"

    lines: list[str] = []

    for lab in summaries:
        lines.append(f"## LAB: {lab.lab_id} ({lab.kind}) — status: {lab.status}")
        lines.append(f"   status reason: {lab.status_reason}")
        lines.append(f"   title: {lab.title}")

        if lab.orientations:
            orient = lab.orientations[0]
            lines.append(
                f"   orientation: {orient.id} — {orient.objective}"
            )
            # Additional orientation fields if available
            stop_rule = getattr(orient, "stop_rule", None)
            if stop_rule:
                lines.append(f"   stop rule: {stop_rule}")
        else:
            lines.append("   orientation: (none)")

        lines.append(f"   claws ({len(lab.bundles)}):")

        if not lab.bundles:
            lines.append("     (no claws run yet)")
        else:
            for bundle in lab.bundles:
                rec = bundle.meta.get("promotion_recommendation", "?")
                role = bundle.meta.get("role", "?")
                status = bundle.meta.get("status", "?")
                lines.append(
                    f"     - {bundle.bundle_id}:"
                    f" role={role},"
                    f" status={status},"
                    f" recommendation={rec},"
                    f" claims={bundle.claim_count},"
                    f" trace_events={bundle.trace_count}"
                )

                # First line of result.md
                if bundle.result_text:
                    first_line = bundle.result_text.strip().splitlines()[0]
                    lines.append(f"       result first line: {first_line}")

                # Sample claims from evidence.jsonl
                evidence_path = (
                    lab.lab_root / ".claws" / bundle.bundle_id / "evidence.jsonl"
                )
                claims = _read_jsonl_records(evidence_path, limit=3)
                if claims:
                    sample = claims[0]
                    claim_text = sample.get("claim", "")
                    confidence = sample.get("confidence", "?")
                    lines.append(
                        f"       sample claim: [{confidence}] {claim_text}"
                    )
                    if len(claims) > 1:
                        lines.append(
                            f"       (+ {len(claims) - 1} more claims in evidence.jsonl)"
                        )

        lines.append("")

    return "\n".join(lines).rstrip()


def build_prompt(
    federation_root: Path,
    history: list[dict],
    user_message: str,
) -> str:
    """Construct the full prompt for one director-agent turn.

    history is a list of {"role": "human"|"agent", "content": str} from prior turns.
    Returns the full string to send to claude -p.
    """
    snapshot = render_lab_snapshot(federation_root)
    parts = [
        DIRECTOR_SYSTEM,
        "",
        "=== LAB STATE SNAPSHOT ===",
        snapshot,
        "",
        "=== CONVERSATION SO FAR ===",
    ]
    for turn in history:
        parts.append(f"{turn['role']}: {turn['content']}")
    parts.append(f"human: {user_message}")
    parts.append("")
    parts.append("Respond as the director agent. Use markdown. Be specific and concise.")
    return "\n".join(parts)


async def ask_director(
    federation_root: Path,
    history: list[dict],
    user_message: str,
    timeout: int = 90,
) -> str:
    """Send a message to the director agent. Returns the markdown response.

    Runs claude -p in a subprocess, async-friendly so the TUI doesn't block.
    """
    prompt = build_prompt(federation_root, history, user_message)
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)  # force subscription billing

    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", "--output-format", "text", prompt,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        return f"_(agent timeout after {timeout}s)_"

    if proc.returncode != 0:
        err_text = stderr.decode("utf-8", errors="replace")[:200]
        return f"_(agent error: {err_text})_"

    return stdout.decode("utf-8", errors="replace").strip()
