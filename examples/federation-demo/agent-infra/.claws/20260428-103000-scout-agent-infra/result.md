# Result — 20260428-103000-scout-agent-infra

**Role:** scout
**Orientation:** orient-agent-infra-survey
**Lab:** agent-infra
**Status:** finished
**Run:** 2026-04-28T10:30:00Z -> 2026-04-28T12:15:00Z

---

## Summary

This scout claw surveyed 23 CLI coding-agent harnesses tracked by the
awesome-cli-coding-agents list, with deep dives into Aider and Crystal as
the most architecturally distinct examples. Five claims were extracted covering
session management patterns, context-window strategies, and the artifact gap.

Key finding: no surveyed harness implements a structured artifact bundle
format comparable to Studio's meta.json + evidence.jsonl + trace.jsonl
contract. This is a genuine differentiator for Studio, not a duplication
of existing work.

---

## Evidence collected

**Claim 001 (high confidence):** Aider's worktree-per-session model is the
closest analogue to Studio's ephemeral claw worktrees.

**Claim 002 (high confidence):** Crystal's daemon-supervised process model
is the closest analogue to Studio's tmux supervisor.

**Claim 003 (medium confidence):** Three dominant harness patterns exist:
stateful REPL, oneshot subprocess, and long-running daemon.

**Claim 004 (high confidence):** Aider's repo-map context strategy is the
most mature approach to bounded context windows among surveyed harnesses.

**Claim 005 (high confidence):** No surveyed harness has a machine-readable
claims/evidence output layer. This is Studio's primary structural novelty.

---

## Recommendations

1. Route a researcher claw to synthesize cross-harness patterns and produce
   adoption recommendations for Studio's supervisor and session primitives.
2. Preserve claim-005 as a key differentiator claim in .intel/evidence/.
3. Do not adopt Aider's repo-map verbatim — Studio's per-lab source scope
   is a tighter contract than Aider's whole-repo tracking.

---

## Promotion recommendation

keep_evidence
