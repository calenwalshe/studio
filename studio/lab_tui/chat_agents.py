"""Tiered chat agents for the Studio cockpit.

Three tiers in the model:
- Director: the human (not represented here)
- ChiefOfStaffAgent: federation-wide chat
- LabAgent: per-lab chat, scoped to one lab

Each agent maintains its own system prompt and uses the same `claude -p`
subprocess pipeline. Conversation history is held by the cockpit per-scope.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

# Ensure lab_tui siblings are importable when this module is run directly
_MODULE_ROOT = Path(__file__).resolve().parents[2]
if str(_MODULE_ROOT / "studio") not in sys.path:
    sys.path.insert(0, str(_MODULE_ROOT / "studio"))

from lab_tui.loaders import LabSummary, discover_labs, load_lab_summary  # noqa: E402
from lab_tui.chat_sessions import get_or_create_session, send_message, reset_session  # noqa: E402


CHIEF_OF_STAFF_SYSTEM = """You are the Chief of Staff for Studio — a human-in-the-loop lab operating system.

You serve the human director. You have full read access to ALL labs in the federation. You can describe state, summarize across labs, identify cross-lab patterns and dependencies, and recommend what needs the director's attention.

You are the FEDERATION-LEVEL agent. For deep details about a single lab — its specific orientation, individual claw histories, the actual evidence text — defer to that lab's agent (the director can zoom in to talk to it directly). You handle:
- Cross-lab triage and prioritization
- Federation-wide patterns ("3 labs are stuck on the same kind of problem")
- Routing the director to the right lab
- Executive summaries spanning multiple labs

You CANNOT take actions yet — Studio's promotion mutations are not implemented in v0. You can only read and recommend.

DELEGATION: when a question is best answered by a specific lab's agent (deep
internals, evidence text, claw-by-claw analysis), you may delegate by emitting:

{{delegate:<lab-id>:<your specific question for that lab agent>}}

Place the marker on its OWN line in your response. The cockpit will route the
question to that lab's agent and splice the reply back into your response in
place of the marker. Use this when the human asks something where a lab
agent's deeper context will materially improve the answer.

Do NOT delegate for federation-level questions (cross-lab patterns, prioritization,
summaries spanning multiple labs) — those are yours to answer directly.

Format: {{delegate:agent-infra:What does the convergent worktree-per-session pattern claim mean operationally?}}

RESPONSE FORMAT — STRICT (same contract as before):

Default response budget: roughly 25-30 lines visible. Treat it as 2 chat blocks max.

Rules:
- Open with the answer in 1-2 lines. The director wants the headline FIRST.
- Use markdown structure: bullets, sub-bullets, bold for the key term.
- One paragraph = one idea. Never run two ideas into one paragraph.
- ALWAYS end with a single concrete action the human can take. Format it as: "**Next:** <one short imperative sentence>"
- If you have more material than fits the budget: end the response with this exact line on its own:
  "_More to say — want a deeper report?_"
  Do NOT include the deeper material preemptively. Stop.
- Cite specifics: lab id, claw id, claim id, recommendation. Don't say "the claw" — say which one.
- If a question is really about ONE lab's internals, suggest the director zoom in: "_For the inside view, expand <lab-id> and ask its lab agent directly._"
- For prioritization questions: pick ONE lab and ONE action. Don't survey.
- Never produce a response that ends without a named lab+action in **Next:**.

TRIAGE QUESTIONS — SPECIAL RULE:

When the human asks any of: "what needs my attention", "what should I do",
"what's the priority", "where do I focus", "where should I start", "triage",
or any other question that asks for prioritization across labs:

1. OPEN with EXACTLY this format on its own line — NO PREAMBLE before it:
   "**Top priority: <lab-id> — <one-verb action>**"

   Example: "**Top priority: cgl-publish — review the merge claw**"

2. Follow with at most 3 bullet points justifying WHY this is the top priority.
   Each bullet <= 1 line. Cite a specific claw id, claim, or recommendation.

3. After the justification, IF other labs also need attention, list them as
   secondary priorities under a "Then:" header — one per line, lab id + one
   verb. NO sub-bullets. Maximum 3 secondary priorities.

4. End with **Next:** as before, but now it must reference YOUR top priority
   action.

Example response shape:

  **Top priority: cgl-publish — review the merge claw**

  - Builder claw 20260430-160000-builder-cgl-publish recommends `merge`
  - Two labs (distribution-engine, future surfaces) are blocked on this primitive
  - The script was verified via dry-run against staging

  Then:
  - agent-infra: accept the researcher merge
  - hello-lab: keep the scout's evidence

  **Next:** Open cgl-publish, expand it, press 'p' on the builder claw.

This format is REQUIRED for any prioritization question. OPEN every prioritization
response with the **Top priority:** line. No exceptions. Surveys without a single
named priority are a failure mode.

Long-form mode: triggered by "detailed", "deep dive", "full report", "long-form", "everything you have". When triggered, no length cap.

Tone: concise. Skip preamble. Distinguish what you SEE (state) from what you RECOMMEND (judgment).

The FEDERATION SNAPSHOT below is your source of truth. Use it.
"""


LAB_AGENT_SYSTEM_TEMPLATE = """You are the Lab Agent for {lab_id} — a single bounded lab in the Studio federation.

You serve the human director (and the Chief of Staff agent who may delegate to you). You have deep knowledge of ONE lab's state: its orientation, its claws, its evidence, its trace events, its decisions.

You are the LAB-LEVEL agent. Stay in scope:
- Answer about THIS lab. Do not opine on other labs unless directly asked.
- Cite specific claw IDs, claim IDs, evidence text from THIS lab.
- Propose specific next claws for THIS lab — name the role, the orientation, what the claw should do.
- Be willing to disagree with a claw's promotion recommendation if the evidence supports it.

You CANNOT take actions yet. You can only read and recommend.

RESPONSE FORMAT — same strict contract as the Chief of Staff:
- Default <=25-30 lines.
- Open with the answer.
- End with **Next:** <action>.
- Long-form mode triggered by "detailed", "deep dive", etc.
- Use markdown. Skip preamble.

Difference vs. Chief of Staff: when the question is really about other labs or the federation as a whole, say: "_That's a federation-level question. Collapse this lab and ask the Chief of Staff._"

The LAB SNAPSHOT below is your source of truth — it includes the orientation, all claws, FULL evidence text (not just first lines), and trace events for {lab_id}. Use it.
"""


LONG_FORM_TRIGGERS = (
    "detailed", "deep dive", "full report", "long-form", "long form",
    "everything you have", "deeper report", "comprehensive", "complete report"
)


def is_long_form_request(user_message: str) -> bool:
    """Return True if the user message requests a long-form / uncapped response."""
    msg = user_message.lower()
    return any(trigger in msg for trigger in LONG_FORM_TRIGGERS)


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


def render_federation_snapshot(federation_root: Path) -> str:
    """Render summary of EVERY lab in the federation.

    Each lab gets: id, kind, status, orientation, claw count, top recommendations.
    First-line of result.md per claw + ONE sample claim per claw. Stays compact.
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
            lines.append(f"   orientation: {orient.id} — {orient.objective}")
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

                # Sample claim from evidence.jsonl
                evidence_path = (
                    lab.lab_root / ".claws" / bundle.bundle_id / "evidence.jsonl"
                )
                claims = _read_jsonl_records(evidence_path, limit=3)
                if claims:
                    sample = claims[0]
                    claim_text = sample.get("claim", "")
                    confidence = sample.get("confidence", "?")
                    lines.append(f"       sample claim: [{confidence}] {claim_text}")
                    if len(claims) > 1:
                        lines.append(f"       (+ {len(claims) - 1} more claims in evidence.jsonl)")

        lines.append("")

    return "\n".join(lines).rstrip()


def render_lab_snapshot(lab_root: Path) -> str:
    """Render DEEP detail for ONE lab.

    Includes:
    - Lab id, title, kind, status, status_reason
    - Full orientation: id, objective, sources, status, stop_rule, constraints
    - For each claw: id, role, status, recommendation, decision (if any)
        - FULL result.md (not just first line)
        - ALL claims from evidence.jsonl with full text + confidence
        - Trace event types + count
    - Skip .archive/
    """
    summary = load_lab_summary(lab_root)
    parts = [
        f"## LAB: {summary.lab_id} ({summary.kind}) — status: {summary.status}",
        f"   reason: {summary.status_reason}",
        f"   title: {summary.title}",
    ]
    for o in summary.orientations:
        parts.append(f"\n### Orientation: {o.id}")
        parts.append(f"   objective: {o.objective}")
        sources = getattr(o, "sources", [])
        parts.append(f"   sources: {', '.join(sources) if sources else '(none)'}")
        parts.append(f"   status: {getattr(o, 'status', '?')}")
        stop_rule = getattr(o, "stop_rule", None)
        parts.append(f"   stop rule: {stop_rule if stop_rule else '(none)'}")
        constraints = getattr(o, "constraints", {})
        parts.append(f"   constraints: {dict(constraints) if constraints else '(none)'}")

    parts.append(f"\n### Claws ({len(summary.bundles)})")
    for b in summary.bundles:
        parts.append(f"\n  Claw: {b.bundle_id}")
        parts.append(f"    role: {b.meta.get('role', '?')}")
        parts.append(f"    status: {b.meta.get('status', '?')}")
        parts.append(f"    recommendation: {b.promotion_recommendation}")
        if b.decision:
            parts.append(
                f"    decision: {b.decision.get('outcome')} "
                f"(decided_at={b.decision.get('decided_at')})"
            )
        else:
            parts.append("    decision: (none — awaiting director)")

        # Full result.md
        if b.result_text:
            parts.append("    result.md:")
            for line in b.result_text.splitlines():
                parts.append(f"      {line}")

        # All claims — derive path from lab_root + .claws + bundle_id
        claws_path = summary.lab_root / ".claws" / b.bundle_id
        ev_path = claws_path / "evidence.jsonl"
        if ev_path.exists():
            parts.append(f"    claims ({b.claim_count}):")
            for ln in ev_path.read_text(encoding="utf-8").splitlines():
                if ln.strip():
                    try:
                        c = json.loads(ln)
                        parts.append(f"      [{c.get('confidence', '?')}] {c.get('claim', '')}")
                        if c.get("support"):
                            parts.append(f"        support: {c['support']}")
                    except json.JSONDecodeError:
                        continue

    return "\n".join(parts)


def build_chief_prompt(
    federation_root: Path,
    history: list[dict],
    user_message: str,
) -> str:
    """Construct the full prompt for a Chief of Staff agent turn."""
    snapshot = render_federation_snapshot(federation_root)
    parts = [
        CHIEF_OF_STAFF_SYSTEM,
        "",
        "=== FEDERATION SNAPSHOT ===",
        snapshot,
        "",
        "=== CONVERSATION SO FAR ===",
    ]
    for turn in history:
        parts.append(f"{turn['role']}: {turn['content']}")
    parts.append(f"human: {user_message}")
    parts.append("")
    if is_long_form_request(user_message):
        parts.append("LONG-FORM MODE ACTIVE: no length cap on this response. Still end with **Next:** action.")
    else:
        parts.append(
            "DEFAULT MODE: <=25-30 lines. End with **Next:** action. "
            "If you'd overflow, end with: _More to say — want a deeper report?_"
        )
    return "\n".join(parts)


def build_lab_prompt(
    lab_root: Path,
    lab_id: str,
    history: list[dict],
    user_message: str,
) -> str:
    """Construct the full prompt for a Lab Agent turn."""
    snapshot = render_lab_snapshot(lab_root)
    system = LAB_AGENT_SYSTEM_TEMPLATE.format(lab_id=lab_id)
    parts = [
        system,
        "",
        f"=== LAB SNAPSHOT: {lab_id} ===",
        snapshot,
        "",
        "=== CONVERSATION SO FAR ===",
    ]
    for turn in history:
        parts.append(f"{turn['role']}: {turn['content']}")
    parts.append(f"human: {user_message}")
    parts.append("")
    if is_long_form_request(user_message):
        parts.append("LONG-FORM MODE ACTIVE: no length cap on this response.")
    else:
        parts.append("DEFAULT MODE: <=25-30 lines.")
    return "\n".join(parts)


async def _run_claude(prompt: str, timeout: int = 90) -> str:
    """Run claude -p with a full prompt string. Returns the text response."""
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


DELEGATE_RE = re.compile(r"\{\{delegate:([a-z][a-z0-9-]*):([^}]+)\}\}")


async def expand_delegations(response: str, federation_root: Path, max_depth: int = 1) -> str:
    """Find {{delegate:lab-id:question}} markers in response and replace
    each with a lab agent's reply (prefixed with attribution).

    max_depth=1 means: lab agents themselves cannot trigger nested delegations
    (we never call expand_delegations on a lab agent's reply). This prevents
    infinite recursion and keeps cost bounded.
    """
    matches = list(DELEGATE_RE.finditer(response))
    if not matches:
        return response
    parts = []
    last_end = 0
    for m in matches:
        parts.append(response[last_end:m.start()])
        lab_id, question = m.group(1), m.group(2).strip()
        lab_root = federation_root / lab_id
        if not (lab_root / ".studio" / "lab.toml").exists():
            parts.append(f"\n_(delegation failed: no such lab '{lab_id}')_\n")
            last_end = m.end()
            continue
        try:
            reply = await ask_lab_agent(lab_root, lab_id, [], question, timeout=90)
        except Exception as e:
            parts.append(f"\n_(delegation to {lab_id} failed: {e})_\n")
            last_end = m.end()
            continue
        parts.append(
            f"\n\n**Routed to {lab_id}:** _{question}_\n\n"
            f"> {reply.replace(chr(10), chr(10) + '> ')}\n\n"
        )
        last_end = m.end()
    parts.append(response[last_end:])
    return "".join(parts)


async def ask_chief_of_staff(
    federation_root: Path,
    history: list[dict],
    user_message: str,
    timeout: int = 120,
) -> str:
    """Send a message to the Chief of Staff session.

    history is now ignored — Claude Code holds the conversation server-side.
    Kept in the signature for back-compat with existing callers; the next
    refactor pass should remove it.
    """
    snapshot = render_federation_snapshot(federation_root)
    system = (
        CHIEF_OF_STAFF_SYSTEM
        + "\n\n=== FEDERATION SNAPSHOT (frozen at session start) ===\n"
        + snapshot
    )

    session = get_or_create_session(
        scope_key="chief",
        cwd=federation_root,
        system_prompt=system,
    )
    raw = await send_message(session, user_message, timeout=timeout)
    expanded = await expand_delegations(raw, federation_root)
    return expanded


async def ask_lab_agent(
    lab_root: Path,
    lab_id: str,
    history: list[dict],
    user_message: str,
    timeout: int = 120,
) -> str:
    """Send a message to a Lab Agent session (one per lab).

    history is now ignored — Claude Code holds the conversation server-side.
    Kept in the signature for back-compat with existing callers.
    """
    snapshot = render_lab_snapshot(lab_root)
    system = (
        LAB_AGENT_SYSTEM_TEMPLATE.format(lab_id=lab_id)
        + f"\n\n=== LAB SNAPSHOT: {lab_id} (frozen at session start) ===\n"
        + snapshot
    )

    session = get_or_create_session(
        scope_key=f"lab:{lab_id}",
        cwd=lab_root,
        system_prompt=system,
    )
    return await send_message(session, user_message, timeout=timeout)


def refresh_chief_session() -> bool:
    """Discard the chief session so next message starts fresh with current snapshot."""
    return reset_session("chief")


def refresh_lab_session(lab_id: str) -> bool:
    """Discard a lab session so next message starts fresh with current snapshot."""
    return reset_session(f"lab:{lab_id}")
