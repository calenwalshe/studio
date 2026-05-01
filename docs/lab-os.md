# Studio as a lab operating system (target direction)

Studio is moving from a narrow "session harness" description toward a clearer
frame: a **human-in-the-loop lab operating system** for **director-oriented
intelligence work**.

This does **not** change v0 status. The current extraction work remains the
foundation. See [PLAN.md](../PLAN.md).

## What remains true in v0

- Studio is still a keyboard-driven harness around the existing primitives.
- Core concepts remain: **Lab, Supervisor, Claw, Arm, Bridge, Federation,
  Themes, Spine**.
- The director remains the single human operator coordinating multiple labs.

## Why the framing changes

"Lab OS" better describes the operating posture:

- Persistent multi-lab coordination, not one-off sessions.
- Human direction and judgment at every critical decision point.
- Traceable movement from raw work to decisions and publishable outcomes.

## Target-direction concepts (planned, not yet implemented)

These concepts shape where Studio is heading:

- **Orientation** — explicit director posture for each lab.
- **Evidence** — concrete support for decisions and recommendations.
- **Artifact Bundle** — a review-ready package of outputs + rationale.
- **Promotion Gate** — explicit quality/decision checkpoint before advancing.
- **Source Pack** — auditable set of sources behind an output.

Until these are implemented, they should be treated as design language,
not runtime guarantees.

## Where we are now

**Arc A — schema and example (this migration):**

- `.studio/` control-plane schema added to `examples/hello-lab/`: `lab.toml`,
  `orientations.toml`, `roles.toml`, `capabilities.toml`, `runtimes.toml`,
  `promotion.toml`, `sources.toml`.
- `.claws/<id>/` artifact bundle contract established as a hand-written fixture:
  `meta.json`, `trace.jsonl`, `evidence.jsonl`, `result.md`.
- `docs/specs/studio-lab-os-spec.md` published as the authoritative target
  architecture reference.
- `docs/specs/walkthrough-hello-lab.md` added as a guided teaching document.
- Top-level README updated to surface the lab OS direction.

The v0 harness is unmodified. All Arc A additions are declarative — no new
runtime behavior.

**Arc B — dry-run CLI (planned):**

- `cgl-orient create`, `cgl-orient list`, `cgl-claw spawn --orientation <id> --role <role> --dry-run`.
- Stubs that write artifact bundles without running a real claw.
- See spec §14 Phase 4.

**Arc C — promotion queue and capability checks (planned):**

- Bridge reads artifact bundles and surfaces promotion candidates.
- Capability gateway enforces at least: role must exist, capability profile must
  exist, output contract required, no ambient secrets by default.
- See spec §14 Phases 5–7.
