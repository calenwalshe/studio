# Result — 20260429-141500-researcher-agent-infra

**Role:** researcher
**Orientation:** orient-agent-infra-survey
**Lab:** agent-infra
**Status:** finished
**Run:** 2026-04-29T14:15:00Z -> 2026-04-29T15:42:00Z

---

## Summary

This researcher claw synthesized the five scout claims from the prior run
into three cross-harness pattern claims. The synthesis confirms that Studio's
architectural choices (worktree isolation, per-lab source scope, structured
artifact bundles) are independently validated by the convergent evolution of
the broader harness ecosystem.

The evidence package from both this run and the scout run is ready for
promotion to .intel/evidence/ as a structured knowledge base entry.

---

## Evidence collected

**Claim 001 (high confidence):** Worktree-based and process-based isolation
are convergent across harnesses. Every durable multi-session harness arrives
at filesystem isolation independently.

**Claim 002 (high confidence):** Context-window budgeting is a universal
concern. Every major harness has a dedicated module for it. Studio's
source_scope is a clean solution at the lab configuration level.

**Claim 003 (medium confidence):** Studio's source_scope + evidence.jsonl
claim-to-source tracing is architecturally superior to Aider's file-set
tracking for research workflows. The provenance chain survives session
boundaries in a way that git history alone cannot.

---

## Recommendations

1. Promote both scout and researcher evidence bundles to .intel/evidence/
   as a combined investigation record.
2. Draft an ADR capturing Studio's source scope design rationale against
   the alternatives surveyed.
3. No further scout or researcher claws are needed for this orientation.

---

## Promotion recommendation

merge
