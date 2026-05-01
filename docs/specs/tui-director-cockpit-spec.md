# Studio TUI — Director Cockpit Specification

> Branch: `tui/director-cockpit-spec`  
> Status: Draft implementation spec for a coding agent.  
> Scope: TUI/interface development only. This spec translates the lab-OS architecture into concrete screens, flows, state models, and acceptance criteria.

## 1. Purpose

The Studio TUI is the director cockpit for lab work.

It should not primarily feel like a terminal multiplexer or a grid of agent panes. It should feel like a control surface for answering:

```text
What is each lab pointed at?
What has each lab learned?
What is currently acting?
What needs my decision?
What can be promoted into durable lab state?
```

The TUI exists to help one human director operate many labs without losing control, provenance, or promotion discipline.

## 2. Product framing

Studio is a human-in-the-loop lab operating system. The director orients labs toward sources, questions, systems, workflows, or build goals. Studio coordinates supervisors and bounded claws to acquire evidence, synthesize findings, build tools, verify outputs, and promote durable work into systems, surfaces, investigations, and spine.

The TUI is where that becomes visible and actionable.

Core rule:

```text
Agents may act in bounded contexts.
Studio records, routes, and summarizes.
The director promotes.
```

## 3. Existing primitives to preserve

Do not discard the current vocabulary. The TUI should make these existing concepts clearer:

- **Director** — the single human operator.
- **Federation** — cross-lab view.
- **Lab** — bounded domain of work.
- **Supervisor** — persistent lab coordinator.
- **Claw** — bounded worker execution.
- **Arm** — long-lived alternate branch/worktree.
- **Themes** — executive event stream / summaries.
- **Spine** — reusable skills, runbooks, ADRs, and promoted patterns.
- **Bridge** — current TUI/control surface concept.

The new interface adds stronger control points around those primitives:

- **Orientation** — what a lab is pointed at right now.
- **Evidence** — sourced claims and observations.
- **Artifact Bundle** — log/result/trace/evidence/diff outputs from work.
- **Promotion Candidate** — something awaiting director judgment.
- **Promotion Gate** — director decision point.
- **Source Pack** — reusable source acquisition/tooling bundle.
- **Capability Envelope** — bounded permissions for a claw.

## 4. Primary interface principle

The TUI should optimize for decisions, not spectacle.

Bad center of gravity:

```text
I watch agents type into terminals.
```

Correct center of gravity:

```text
I point labs at goals, inspect what happened, and decide what becomes durable.
```

## 5. Primary screens

The initial TUI should have five conceptual screens:

1. **Federation Home** — cross-lab command center.
2. **Lab Focus** — one lab's orientation, work, evidence, and artifacts.
3. **Promotion Review** — artifact/evidence review and director decision.
4. **Capability Request** — inspect/approve/deny a proposed execution envelope.
5. **Chat / Command Pane** — contextual director conversation and command surface.

The first implementation can be simpler than the full layout, but it must preserve these concepts.

---

## 6. Screen: Federation Home

### 6.1 Purpose

Default director view across all labs.

Answers:

```text
What labs exist?
What is each lab pointed at?
Which labs are active, blocked, stale, or waiting for review?
What needs my attention now?
What patterns are emerging across labs?
```

### 6.2 Layout sketch

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ STUDIO / FEDERATION                                                         │
│ Director cockpit across all labs                                            │
├──────────────────────┬──────────────────────────┬──────────────────────────┤
│ Labs                 │ Director Queue            │ Cross-Lab Intelligence   │
├──────────────────────┼──────────────────────────┼──────────────────────────┤
│ ● systems/studio     │ Needs review              │ Patterns emerging        │
│   lab OS migration   │ - spec candidate          │ - source packs recur     │
│                      │ - 2 evidence bundles      │ - capability gap common  │
│ ◐ investigation/ai   │ - failed builder claw      │ - worktrees baseline     │
│   ecosystem patterns │                          │                          │
│                      │ Active decisions          │ Shared source packs      │
│ ! systems/sources    │ - promote artifact #12    │ - github-repo-research   │
│   blocked: approval  │ - approve network scout   │ - web-research           │
│                      │                          │                          │
│ ○ surface/snake      │ Stale labs                │ Risks                    │
│   idle               │ - surface/demo            │ - no capability gate     │
│                      │ - investigation/ads       │ - no promotion queue     │
└──────────────────────┴──────────────────────────┴──────────────────────────┘
```

### 6.3 Minimum viable Federation Home

Must show:

- lab slug
- lab kind
- current orientation summary, if any
- status: active, idle, blocked, stale, needs_review
- active claws count
- unreviewed artifact count
- promotion candidate count
- blockers / asks
- next recommended action, if available

### 6.4 Suggested visual status vocabulary

```text
● active
◐ needs review
! blocked
○ idle
… stale
✓ healthy / complete
```

Use plain text first. Do not depend on color alone.

### 6.5 Data model for a lab row

```json
{
  "slug": "systems/studio",
  "kind": "systems",
  "orientation_id": "orient-lab-os-migration",
  "orientation_summary": "Migrate old harness docs into lab OS spec",
  "status": "needs_review",
  "supervisor_status": "parked",
  "active_claws": 1,
  "unreviewed_artifacts": 2,
  "promotion_candidates": 1,
  "blockers": [],
  "stale_since": null,
  "next_action": "review promotion candidate"
}
```

---

## 7. Screen: Lab Focus

### 7.1 Purpose

Drill into one lab. This is where the director steers the lab.

Answers:

```text
What is this lab currently oriented toward?
What is the supervisor doing?
Which role-based claws are active/done/blocked?
What evidence and themes have emerged?
What artifacts are awaiting review?
```

### 7.2 Layout sketch

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ LAB: investigation/agent-infra                                              │
├─────────────────────────────────────────────────────────────────────────────┤
│ Orientation                                                                 │
│ Compare agent infrastructure patterns and decide what Studio should adopt.  │
│ Sources: awesome-cli-coding-agents, selected repos, current Studio repo     │
│ Stop rule: director review after first spec                                 │
├──────────────────────────────┬──────────────────────────────────────────────┤
│ Work                          │ Evidence / Themes                           │
├──────────────────────────────┼──────────────────────────────────────────────┤
│ scout       done              │ claim-001: worktrees are baseline            │
│ researcher  running           │ claim-002: dashboards converge on queues     │
│ builder     proposed          │ claim-003: sandboxing is infrastructure      │
│ reviewer    waiting           │                                              │
│ curator     idle              │ Theme: governance beats session grids        │
├──────────────────────────────┴──────────────────────────────────────────────┤
│ Actions: [o] orient  [s] spawn role  [r] review  [p] promote  [f] federation│
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.3 Minimum viable Lab Focus

Must show:

- lab slug and kind
- current orientation
- sources in scope
- stop rule
- supervisor session status
- claws grouped by role/status
- recent themes
- recent artifacts
- promotion candidates

### 7.4 Role grouping

Role-based claws should be visible as a workflow, not random processes:

```text
scout       gather sources/signals
researcher  synthesize evidence
builder     build tools/systems/surfaces/connectors
reviewer    verify and critique
operator    run approved workflows
curator     graduate reusable knowledge into spine
```

---

## 8. Screen: Promotion Review

### 8.1 Purpose

This is the most important screen. It is where Studio becomes different from a session runner.

The promotion screen answers:

```text
What did this artifact prove or change?
Is it sourced?
Was it verified?
What are the risks?
Should this become durable lab state?
```

### 8.2 Layout sketch

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ PROMOTION REVIEW                                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ Candidate: source-pack spec                                                 │
│ Lab: investigation/agent-infra                                               │
│ Role: researcher                                                             │
│ Orientation: compare infrastructure patterns                                 │
├──────────────────────────────┬──────────────────────────────────────────────┤
│ Artifact Bundle               │ Verification                                 │
├──────────────────────────────┼──────────────────────────────────────────────┤
│ ✓ meta.json                   │ ✓ provenance present                          │
│ ✓ result.md                   │ ✓ no code execution                           │
│ ✓ evidence.jsonl              │ ? claims need review                          │
│ ✓ trace.jsonl                 │ ✕ no reviewer pass yet                        │
│                              │                                               │
│ Recommendation: keep_evidence │                                               │
├──────────────────────────────┴──────────────────────────────────────────────┤
│ Summary                                                                     │
│ The researcher found that agent infrastructure splits into routing,          │
│ sandboxing, credentials, browser automation, and source packs.               │
├─────────────────────────────────────────────────────────────────────────────┤
│ Decision: [a] abandon  [k] keep evidence  [c] continue  [m] merge           │
│           [u] publish  [g] graduate to spine                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.3 Promotion candidate types

The UI should eventually support:

- evidence
- investigation_update
- system_change
- surface_change
- runbook_candidate
- skill_candidate
- source_pack_candidate

### 8.4 Promotion outcomes

The UI should eventually support:

- abandon
- keep_evidence
- continue
- merge
- publish
- graduate_to_spine

### 8.5 Minimum viable Promotion Review

Must show:

- artifact id/path
- lab slug
- role
- result summary
- files present in artifact bundle
- evidence count
- trace count
- changed files, if any
- promotion recommendation
- decision command hints

Initial implementation may only display and not mutate. Mutation can dispatch to primitives later.

---

## 9. Screen: Capability Request

### 9.1 Purpose

Inspect and approve/deny what a claw is allowed to do before it acts.

This screen prevents the system from becoming “agent inherits my whole machine.”

### 9.2 Layout sketch

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ CAPABILITY REQUEST                                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ Lab: investigation/agent-infra                                               │
│ Role: scout                                                                  │
│ Source Pack: github-repo-research                                            │
│ Runtime: claude -p                                                           │
├──────────────────────────────┬──────────────────────────────────────────────┤
│ Allowed                       │ Denied                                       │
├──────────────────────────────┼──────────────────────────────────────────────┤
│ read repo docs                │ write source code                            │
│ fetch public GitHub files     │ access secrets                               │
│ write .claws artifacts        │ run install scripts                          │
│ write evidence.jsonl          │ publish / deploy                             │
├──────────────────────────────┴──────────────────────────────────────────────┤
│ Approval needed: network access to public GitHub                             │
│ Decision: [a] approve once  [d] deny  [e] edit profile                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 9.3 Minimum viable Capability Request

Spec-only at first. The first implementation can render capability information from files without enforcing it.

Must show:

- role
- capability profile
- runtime
- allowed tools
- denied/default-denied capabilities
- whether approval is required

---

## 10. Chat / Command Pane

### 10.1 Purpose

The chat pane is the director’s command and reasoning surface.

It should not be an unbounded chatbot. It should be contextual, action-oriented, and file-backed.

```text
Chat is the interface.
Files are the memory.
Git is the promotion log.
```

### 10.2 Chat scopes

The chat must have an explicit scope:

- Federation
- Lab
- Artifact
- Capability Request
- Source Pack

Scope determines what context is loaded and what commands are suggested.

### 10.3 Federation chat examples

```text
What needs my attention today?
Which labs are blocked?
Summarize all promotion candidates.
Which source packs are emerging across labs?
Show labs without active orientation.
Compare findings from agent-infra and systems/studio.
```

### 10.4 Lab chat examples

```text
What is this lab pointed at?
Spawn a scout for this orientation.
Summarize the last three artifacts.
Create a builder task from this evidence.
What should happen next?
```

### 10.5 Artifact chat examples

```text
What did this claw prove?
Are the claims sourced?
What would a reviewer say?
Should I promote this?
Turn this into a runbook candidate.
```

### 10.6 Capability chat examples

```text
Why does this claw need network?
What happens if I deny shell?
Limit it to read-only GitHub access.
Approve this once.
```

### 10.7 Action-card style

Chat responses should produce proposed actions, not just prose.

Example:

```text
Director:
Compare these infrastructure patterns against Studio.

Studio:
I can create a research orientation.

Proposed orientation:
- Lab: investigation/agent-infra
- Sources: awesome-cli-coding-agents, Studio repo
- Roles: scout → researcher → curator
- Output: evidence bundle + gap analysis + spec
- Stop rule: director review before implementation

Actions:
[Create orientation] [Edit sources] [Spawn scout] [Cancel]
```

Initial TUI may not implement full chat. If not implemented, reserve layout space and document command equivalents.

---

## 11. Navigation model

Recommended navigation:

```text
Federation
  ├─ open lab
  │    └─ Lab Focus
  │         └─ open artifact
  │              └─ Promotion Review
  ├─ open blocker
  │    └─ Capability Request
  └─ open pattern
       └─ Cross-Lab Synthesis / Source Pack view
```

Suggested keys:

```text
f  federation
enter open selected item
esc/backspace go back
j/k or arrows move selection
/ search/filter
o  orient lab
s  spawn role/claw
r  review selected candidate
p  promote selected candidate
a  abandon selected candidate/claw
e  evidence
tr trace
c  capability/profile
?  help
q  quit/detach
```

Do not over-optimize keybindings before the data model works.

---

## 12. Data sources for the TUI

The TUI should be file-first and read-only by default.

Potential inputs:

```text
.studio/lab.toml
.studio/orientations.toml
.studio/roles.toml
.studio/capabilities.toml
.studio/promotion.toml
.studio/sources.toml
.claws/<id>/meta.json
.claws/<id>/result.md
.claws/<id>/trace.jsonl
.claws/<id>/evidence.jsonl
.intel/themes/*.jsonl
runbooks/
decisions/
.claude/skills/
```

The current Bridge can continue dispatching mutations to `cgl-*` primitives. Avoid direct mutation from UI until the command semantics are stable.

---

## 13. State model

### 13.1 LabStatus

```python
@dataclass
class LabStatus:
    slug: str
    kind: str
    title: str | None
    orientation_id: str | None
    orientation_summary: str | None
    status: str  # active | idle | blocked | stale | needs_review
    supervisor_status: str | None
    active_claws: int
    unreviewed_artifacts: int
    promotion_candidates: int
    blockers: list[str]
    stale_since: str | None
    next_action: str | None
```

### 13.2 ArtifactSummary

```python
@dataclass
class ArtifactSummary:
    id: str
    lab_slug: str
    role: str
    path: str
    status: str
    result_path: str | None
    evidence_count: int
    trace_count: int
    changed_files_count: int
    promotion_recommendation: str | None
    created_at: str | None
```

### 13.3 PromotionCandidate

```python
@dataclass
class PromotionCandidate:
    id: str
    candidate_type: str
    lab_slug: str
    artifact_id: str
    title: str
    summary: str
    recommendation: str
    required_checks: list[str]
    passed_checks: list[str]
    failed_checks: list[str]
```

### 13.4 CapabilityRequest

```python
@dataclass
class CapabilityRequest:
    id: str
    lab_slug: str
    role: str
    runtime: str
    capability_profile: str
    allowed: list[str]
    denied: list[str]
    approval_required: bool
    reason: str | None
```

These are suggested shapes, not required class names.

---

## 14. TUI implementation guidance

### 14.1 Architecture

Prefer simple, testable modules:

```text
studio/tui/
  app.py
  screens/
    federation.py
    lab_focus.py
    promotion_review.py
    capability_request.py
    chat.py
  models.py
  loaders.py
  actions.py
  widgets.py
```

If the current repo already has `studio/bridge/` or `studio/lab_tui/`, adapt this organization to the existing layout instead of creating redundant modules.

### 14.2 Loader responsibilities

`loaders.py` should read file-backed state and degrade gracefully when files are missing.

Missing `.studio/` should not crash the TUI. Show a setup hint.

Missing `.claws/` should show zero artifacts.

Invalid JSON/TOML should produce a visible warning row, not a traceback.

### 14.3 Read-only first

Initial TUI mutations should be minimal. Prefer:

- show command hints
- shell out to existing `cgl-*` primitives only when explicit
- write nothing silently
- make promotion decisions explicit

### 14.4 Tests

Add tests for loaders and state model before heavy UI tests.

Minimum tests:

- parse example `.studio` files
- load lab rows from example lab
- load artifact bundle from sample `.claws/<id>/`
- handle missing files gracefully
- detect promotion candidates from artifact metadata

---

## 15. MVP acceptance criteria

A first TUI development pass is successful if:

- It launches without requiring real lab secrets or private CGL data.
- It can point at `examples/hello-lab`.
- It renders a Federation Home with at least one lab row.
- It renders Lab Focus for a selected lab.
- It can display current orientation if present.
- It can list artifact bundles from `.claws/` if present.
- It can display a Promotion Review screen for one artifact.
- It can display a Capability Request/Profile screen from `.studio/capabilities.toml`.
- It clearly distinguishes implemented behavior from future/spec-only behavior.
- It remains file-backed and inspectable.

---

## 16. Non-goals for this branch

Do not implement:

- web UI
- mobile UI
- daemon/service
- database
- crawler
- background scheduler
- live external API integrations
- credential broker
- actual container sandboxing
- model/provider routing
- auto-merge or auto-publish

Do not rebrand Studio as a generic session runner. The TUI should emphasize lab orientation, evidence, artifacts, and promotion.

---

## 17. Coding agent instructions

When using a coding agent to implement this branch:

```text
Work on the TUI director cockpit branch.
Use docs/specs/tui-director-cockpit-spec.md as the source of truth.
Keep changes small and reviewable.
Prefer file-backed state over services.
Do not implement web, database, daemon, crawler, or secrets.
Preserve existing cgl-* primitives and Bridge concepts.
If existing TUI code exists, adapt it rather than replacing it wholesale.
Mark future/spec-only concepts clearly.
Add tests for loaders before adding complex UI behavior.
```

Recommended build sequence:

```text
1. Add example .studio files and sample .claws artifact if missing.
2. Add TUI data models/loaders.
3. Render Federation Home from file-backed state.
4. Add Lab Focus screen.
5. Add Promotion Review screen.
6. Add Capability Request/Profile screen.
7. Add simple command/chat placeholder pane.
8. Wire key navigation.
9. Add tests and smoke instructions.
```

---

## 18. North star

The TUI should make the director feel:

```text
I can see the whole operation.
I know what each lab is pointed at.
I know what agents did.
I know what needs my judgment.
I can decide what becomes durable.
```

That is the interface.
