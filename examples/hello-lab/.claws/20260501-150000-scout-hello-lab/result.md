# Result — 20260501-150000-scout-hello-lab

**Role:** scout
**Orientation:** orient-hello-lab-studio-exploration
**Lab:** hello-lab
**Status:** finished
**Run:** 2026-05-01T15:00:00Z → 2026-05-01T15:12:00Z

---

## Summary

This scout claw surveyed the Studio repo to establish a baseline understanding of the hello-lab example and the v0 harness architecture. The primary objective was to identify what is already implemented versus what remains as target architecture, with a focus on the artifact bundle contract.

The v0 harness is functional: tmux-backed supervisors, ephemeral worktree claws, and a lab/arm/bridge primitive set all exist as shell scripts in `bin/`. The `.studio/` schema (orientations, roles, capabilities) is present as draft TOML files in the hello-lab example. However, the `.claws/` artifact bundle contract has no implementation — no claw currently writes `meta.json`, `trace.jsonl`, or `evidence.jsonl`.

Three claims were extracted and are available in `evidence.jsonl` for promotion to `.intel/`.

---

## Evidence collected

**Claim 001 (high confidence):** The supervisor primitive is tmux. `bin/cgl-supervisor` is the authoritative implementation. This is well-established and not in question.

**Claim 002 (high confidence):** Claws use ephemeral git worktrees. ADR 0003 records the decision explicitly. The implementation exists in `bin/cgl-claw`.

**Claim 003 (medium confidence):** No `.claws/` directory or artifact bundles exist in the hello-lab example as of this scout run. Confidence is medium because the file listing is an indirect indicator — there is no spec violation, only an absence of the pattern being established by Arc A.2.

---

## Recommendations

1. The artifact bundle contract (this bundle's own format) should be documented and schema-validated before any claw is expected to produce it. Arc A.2 addresses this.
2. Once the schema exists, `bin/cgl-claw` should be updated to write at minimum `meta.json` and `result.md` on exit. This is Phase 5 in the spec roadmap.
3. The `.intel/evidence/` ingestion path (claims.jsonl, observations.jsonl) should be defined before evidence from multiple claws needs to be merged. That is a Phase 3/6 concern.

---

## Promotion recommendation

keep_evidence
