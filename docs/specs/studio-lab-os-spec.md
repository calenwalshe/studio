# Studio Lab OS — App Specification

> Status: Draft architecture specification. This document describes the target direction for Studio and intentionally distinguishes implemented v0 behavior from planned capabilities.

## 1. One-line definition

Studio is a human-in-the-loop lab operating system for director-oriented intelligence work: the director orients labs toward sources, questions, systems, and build goals; Studio coordinates supervisors and bounded claws to acquire evidence, build tools, synthesize findings, verify outputs, and promote durable work into systems, surfaces, investigations, and spine.

## 2. Product thesis

Existing agent tools mostly answer: “How do I run many coding agents at once?” Studio answers: “How do I turn directed agent work into durable lab state without losing human control?”

Studio is not an always-on sensing machine. The director explicitly orients a lab toward a source, question, market, repo, API, dataset, workflow, or build goal. The lab then performs bounded acquisition, synthesis, building, verification, and promotion.

Core rule:

```text
Agents may act in bounded contexts.
Studio records, routes, and summarizes.
The director promotes.
```

## 3. Current v0 baseline

The existing repo describes Studio as a director-multiplexed lab management harness on top of tmux + Claude Code. The current primitives are still valuable and should be preserved:

- Lab — a long-lived directory/domain of work.
- Supervisor — persistent Claude session for a lab.
- Claw — ephemeral background worker in a git worktree.
- Arm — long-lived alternate worktree/branch.
- Bridge — director TUI/federation view.
- Federation — cross-lab layer.
- Themes — executive log from activity.
- Spine — reusable skills, runbooks, and ADRs.

This spec layers governance, evidence, orientation, capabilities, and promotion around those primitives.

## 4. Target architecture

```text
DIRECTOR
  │
  │ creates orientation
  ▼
ORIENTATION BRIEF
  objective + source scope + constraints + budget + stop rule
  │
  ▼
LAB
  bounded domain of work: surface / investigation / systems / tool-building
  │
  ▼
SUPERVISOR
  persistent coordinator for the lab
  │
  │ plans roles
  ▼
ROLE-BASED CLAW REQUEST
  scout / researcher / builder / reviewer / operator / curator
  │
  ▼
CAPABILITY GATEWAY
  role policy + lab policy + task policy + human approval when needed
  │
  ▼
EXECUTION ENVELOPE
  runtime + worktree/container + tool access + scoped secrets + audit trace
  │
  ▼
CLAW / ARM EXECUTION
  bounded work in isolated branch/worktree
  │
  ▼
ARTIFACT + EVIDENCE BUNDLE
  log + result + trace + evidence + diffs + screenshots + provenance
  │
  ▼
VERIFICATION
  tests + review + source checks + capability audit
  │
  ▼
DIRECTOR PROMOTION GATE
  abandon / keep evidence / continue / merge / publish / graduate to spine
  │
  ▼
DURABLE LAB STATE
  systems/ + surfaces/ + research/ + runbooks/ + skills/ + decisions/
```

## 5. Core concepts

### 5.1 Director

The single human operator. The director chooses orientation, resolves ambiguity, approves promotion, and decides what becomes durable.

### 5.2 Federation

The cross-lab control layer. It surfaces stale work, blocked asks, active claws, evidence candidates, promotion candidates, and investment/attention dashboards.

### 5.3 Lab

A bounded domain of work and governance. A lab is not just a folder; it is the arena where source scope, role policy, evidence, builds, decisions, and reusable knowledge cohere.

Lab kinds:

- surface — public-facing or user-facing output.
- investigation — research effort with evidence, questions, cycles, and budget.
- systems — internal tools, infrastructure, operations, and lab capabilities.

Potential future kind:

- source-pack — reusable acquisition/tooling bundle promoted out of one lab for reuse across labs.

### 5.4 Orientation

A director-scoped intent for a lab.

An orientation answers:

- What is this lab pointed at?
- Why does it matter?
- Which sources are in scope?
- What constraints apply?
- What output is expected?
- When should the work stop for review?

Example:

```yaml
id: orient-2026-05-01-agent-infra
lab: investigation/agent-infra
objective: Compare agent infrastructure patterns and identify what Studio should adopt.
sources:
  - github: bradAGI/awesome-cli-coding-agents
  - current_repo: calenwalshe/studio
constraints:
  - do not run untrusted code
  - preserve provenance for claims
  - produce spec before implementation
roles:
  - scout
  - researcher
  - curator
outputs:
  - evidence bundle
  - gap analysis
  - architecture spec
stop_rule: director review after first spec
```

### 5.5 Supervisor

Persistent lab coordinator. The supervisor keeps context for the lab, interprets director orientation, delegates to claws, and reports back.

The supervisor should not do long execution directly when a claw can do bounded work.

### 5.6 Claw

A bounded worker execution. In v0, a claw is a one-shot Claude process in a git worktree. In the target architecture, each claw has:

- role
- orientation id
- source scope
- capability profile
- runtime adapter
- tool permissions
- output contract
- artifact bundle
- promotion recommendation

Roles:

- scout — find and capture sources/signals.
- researcher — synthesize evidence and produce analysis.
- builder — build tools, systems, surfaces, or connectors.
- reviewer — verify, critique, test, and source-check.
- operator — run approved workflows against external systems.
- curator — graduate reusable knowledge into spine.

### 5.7 Arm

A long-lived branch/worktree for extended alternate directions. Arms are useful when work is too broad or exploratory for a claw but not yet ready to become its own lab.

### 5.8 Spine

The lab’s reusable operating memory:

- `.claude/skills/`
- `runbooks/`
- `decisions/`
- reusable source packs
- promoted patterns and procedures

Spine is Git-native where possible: durable knowledge should be inspectable, diffable, branchable, and reviewable.

### 5.9 Source Pack

A reusable acquisition or tooling bundle for a class of sources.

A source pack may define:

- connector configuration
- tool adapters
- evidence schema
- skills
- runbooks
- capability requirements
- verification checks

Examples:

- GitHub repo research
- web research
- API-backed data acquisition
- analytics or telemetry ingestion
- SEO/ads/source-code publishing workflow

Recurring source acquisition is a promoted capability, not the default behavior.

## 6. File-backed control plane

Studio should prefer plain files over hidden runtime state. Proposed structure:

```text
<lab>/
  .studio/
    lab.toml
    orientations.toml
    roles.toml
    capabilities.toml
    runtimes.toml
    tools.toml
    promotion.toml
    sources.toml
  .claws/
    <id>/
      meta.json
      result.md
      trace.jsonl
      evidence.jsonl
      changes.patch
      screenshots/
  .intel/
    themes/
      <lab-slug>.jsonl
    evidence/
      observations.jsonl
      claims.jsonl
      sources.jsonl
  .claude/
    skills/
  runbooks/
  decisions/
  systems/
  surfaces/
  research/
    investigations/
```

## 7. `.studio` schema draft

### 7.1 lab.toml

```toml
id = "hello-lab"
title = "Hello Lab"
kind = "federation-root"
version = 1

[director]
mode = "single-human"

[paths]
surfaces = "surfaces"
systems = "systems"
investigations = "research/investigations"
spine_skills = ".claude/skills"
runbooks = "runbooks"
decisions = "decisions"
intel = ".intel"
claws = ".claws"
```

### 7.2 orientations.toml

```toml
[[orientation]]
id = "orient-example-agent-infra"
lab = "investigation/agent-infra"
objective = "Compare agent infrastructure patterns and produce Studio recommendations."
status = "draft"
stop_rule = "director_review_after_first_spec"
roles = ["scout", "researcher", "curator"]
sources = ["github-awesome-cli-agents", "studio-current-repo"]
outputs = ["evidence_bundle", "gap_analysis", "spec"]

[orientation.constraints]
run_untrusted_code = false
install_dependencies = false
require_provenance = true
implementation_allowed = false
```

### 7.3 roles.toml

```toml
[roles.scout]
description = "Gather sources and raw observations."
default_runtime = "claude_print"
default_capability = "research_readonly"
outputs = ["evidence.jsonl", "result.md"]

[roles.researcher]
description = "Synthesize evidence into patterns, gaps, and recommendations."
default_runtime = "claude_print"
default_capability = "research_readonly"
outputs = ["result.md", "evidence.jsonl"]

[roles.builder]
description = "Build tools, systems, surfaces, or connectors."
default_runtime = "claude"
default_capability = "build_worktree"
outputs = ["changes.patch", "result.md", "trace.jsonl"]

[roles.reviewer]
description = "Verify claims, test changes, and critique outputs."
default_runtime = "claude_print"
default_capability = "review_readonly"
outputs = ["review.md", "trace.jsonl"]

[roles.operator]
description = "Run approved workflows against external systems."
default_runtime = "claude_print"
default_capability = "operator_scoped"
outputs = ["trace.jsonl", "result.md"]

[roles.curator]
description = "Graduate reusable knowledge into spine."
default_runtime = "claude_print"
default_capability = "spine_write"
outputs = ["runbook_candidate.md", "skill_candidate.md", "decision_candidate.md"]
```

### 7.4 capabilities.toml

```toml
[capabilities.research_readonly]
filesystem = "read-lab-write-artifacts"
network = "ask"
shell = "none"
secrets = []
tools = ["github.fetch", "web.fetch"]
promotion = "human"

[capabilities.build_worktree]
filesystem = "worktree"
network = "ask"
shell = "allowlisted"
secrets = []
tools = ["shell", "git", "tests"]
promotion = "human"

[capabilities.operator_scoped]
filesystem = "worktree"
network = "restricted"
shell = "allowlisted"
secrets = ["scoped-only"]
tools = ["approved-api-tools"]
promotion = "human"
```

### 7.5 runtimes.toml

```toml
[runtimes.claude]
command = "claude"
mode = "interactive"
status = "implemented-v0"

[runtimes.claude_print]
command = "claude -p"
mode = "oneshot"
status = "implemented-v0"

[runtimes.codex]
command = "codex"
mode = "oneshot"
status = "future"
```

### 7.6 promotion.toml

```toml
[outcomes]
allowed = [
  "abandon",
  "keep_evidence",
  "continue",
  "merge",
  "publish",
  "graduate_to_spine"
]

[candidate_types]
allowed = [
  "evidence",
  "investigation_update",
  "system_change",
  "surface_change",
  "runbook_candidate",
  "skill_candidate",
  "source_pack_candidate"
]

[checks.default]
require_result = true
require_meta = true
require_trace = true
require_director_approval = true
```

### 7.7 sources.toml

```toml
[sources.github-awesome-cli-agents]
type = "github_repo"
url = "https://github.com/bradAGI/awesome-cli-coding-agents"
source_pack = "github-repo-research"

[sources.studio-current-repo]
type = "github_repo"
url = "https://github.com/calenwalshe/studio"
source_pack = "github-repo-research"
```

## 8. Artifact contract

Every claw should leave a directory like:

```text
.claws/<id>/
  meta.json
  result.md
  trace.jsonl
  evidence.jsonl
  changes.patch
  screenshots/
```

### 8.1 meta.json

```json
{
  "id": "20260501-150000-scout-agent-infra",
  "orientation_id": "orient-example-agent-infra",
  "lab_slug": "investigation/agent-infra",
  "role": "scout",
  "runtime": "claude_print",
  "capability_profile": "research_readonly",
  "source_scope": ["github-awesome-cli-agents"],
  "status": "finished",
  "started_at": "2026-05-01T15:00:00Z",
  "ended_at": "2026-05-01T15:12:00Z",
  "promotion_recommendation": "keep_evidence"
}
```

### 8.2 trace.jsonl

Each line records a meaningful action:

```json
{"ts":"2026-05-01T15:01:00Z","event":"source_opened","source":"github-awesome-cli-agents","path":"README.md"}
{"ts":"2026-05-01T15:05:00Z","event":"claim_extracted","claim_id":"claim-001"}
```

### 8.3 evidence.jsonl

Each line is a claim with provenance:

```json
{"id":"claim-001","claim":"Session managers commonly combine worktrees with dashboards.","source":"https://github.com/bradAGI/awesome-cli-coding-agents","support":"Crystal, Parallel Code, Catnip, and vibe-tree entries mention git worktrees.","confidence":"medium"}
```

### 8.4 result.md

Human-readable summary:

```markdown
# Result

## Summary
...

## Evidence collected
...

## Recommendations
...

## Promotion recommendation
keep_evidence
```

## 9. Capability gateway

The capability gateway decides what a claw may do before it runs.

Flow:

```text
Supervisor proposes claw
  ↓
Resolve role policy
  ↓
Resolve lab policy
  ↓
Resolve source/tool requirements
  ↓
Check whether human approval is needed
  ↓
Construct execution envelope
  ↓
Run claw
  ↓
Write audit trace
```

The gateway must eventually answer:

- Can this claw use the network?
- Can it open a browser?
- Can it run shell commands?
- Can it write files outside its worktree?
- Can it access credentials?
- Which tools may it call?
- What artifacts must it write?

v0 may only model these capabilities declaratively. Enforcement can arrive incrementally.

## 10. Execution envelope

An execution envelope is the bounded context a claw runs inside.

Components:

- runtime adapter — Claude now, other runtimes later.
- filesystem boundary — worktree by default.
- sandbox profile — local, container, or stricter future environment.
- tool adapters — shell, git, browser, GitHub, web, API connectors.
- credential grants — scoped, short-lived, never raw ambient secrets by default.
- audit trace — every meaningful action recorded.

Worktree isolation is necessary but not sufficient. Worktrees isolate code changes; they do not govern network, secrets, or external actions.

## 11. Source packs and directed acquisition

Studio is director-oriented, not always-on.

```text
Director orientation
  ↓
Source scope
  ↓
Source pack
  ↓
Acquisition claw
  ↓
Evidence bundle
  ↓
Research synthesis
  ↓
Promotion decision
```

A source pack defines how to acquire evidence from a class of sources.

Example source-pack structure:

```text
source-packs/
  github-repo-research/
    source-pack.toml
    evidence-schema.json
    skills/
    runbooks/
    permissions.toml
```

One-off acquisition can graduate into a source pack when it proves reusable.

## 12. Promotion queue

The Bridge should evolve from a monitor into a decision surface.

Promotion candidate types:

- evidence
- investigation_update
- system_change
- surface_change
- runbook_candidate
- skill_candidate
- source_pack_candidate

Outcomes:

- abandon
- keep_evidence
- continue
- merge
- publish
- graduate_to_spine

Diagram:

```text
Artifact bundle
  ↓
Verification checks
  ↓
Promotion candidate
  ↓
Director gate
  ├─ abandon
  ├─ keep evidence
  ├─ continue
  ├─ merge
  ├─ publish
  └─ graduate to spine
```

## 13. Codex coding app workflow

Codex should be used as a builder/reviewer/spec worker for Studio itself.

Working pattern:

```text
GitHub issue
  ↓
Codex task on one branch
  ↓
Small diff
  ↓
Codex self-review as reviewer claw
  ↓
Human review
  ↓
Merge or revise
```

Codex prompt template:

```text
Work on GitHub issue #N.
Use the issue body as source of truth.
Keep the diff small.
Do only this issue.
Distinguish implemented behavior from target direction.
Do not add daemons, databases, crawlers, or secrets.
Summarize changed files and follow-up issues.
```

Research/spec prompt template:

```text
You are acting as a researcher/specification worker for Studio.

Goal:
Research the listed sources, extract architecture patterns, and produce a spec.

Rules:
- Do not run untrusted code.
- Do not install dependencies.
- Do not implement product code until the spec is reviewed.
- Every non-obvious claim must include provenance.
- Separate observations from recommendations.
- Separate implemented-now from future-direction.

Output:
- evidence bundle
- spec
- follow-up issues
```

## 14. Implementation roadmap

### Phase 0 — Preserve v0 extraction

- Keep tmux + Claude Code harness working.
- Keep harness/data separation.
- Keep PATH-only consumption unless changed by ADR.
- Finish examples and install path.

### Phase 1 — Docs and architecture

- Reframe README and concepts.
- Add lab OS spec.
- Add diagrams.
- Add gaps analysis.

### Phase 2 — File-backed control plane

- Add `.studio` examples.
- Add orientation schema.
- Add roles/capabilities/promotion schema.

### Phase 3 — Artifact and evidence contracts

- Standardize `.claws/<id>/` bundles.
- Add evidence provenance format.
- Add promotion recommendation format.

### Phase 4 — Dry-run CLI

- `cgl-orient create`
- `cgl-orient list`
- `cgl-orient spawn-claw --dry-run`
- Write stub artifact bundles.

### Phase 5 — Real claw integration

- `cgl-claw spawn --orientation <id> --role <role>`
- Write meta/result/trace/evidence.
- Preserve existing merge/abandon behavior.

### Phase 6 — Bridge promotion queue

- Read artifact bundles.
- Surface candidates.
- Show asks/blockers/status.

### Phase 7 — Capability enforcement

- Enforce a small subset first:
  - role must exist
  - capability profile must exist
  - output contract required
  - no ambient secrets by default

### Phase 8 — Source packs and tools

- GitHub repo research source pack.
- Web research source pack.
- Local repo/code source pack.
- API-backed packs later.

### Phase 9 — Sandboxes/secrets/runtime adapters

- Optional containers.
- Credential broker integration.
- Runtime adapter seam for Codex/OpenCode/Gemini.

## 15. Non-goals

Studio should not become:

- a generic agent framework
- an autonomous swarm
- a workflow DAG engine
- an always-on monitoring system by default
- a multi-tenant SaaS product
- a model router as its primary identity
- a secret manager as its primary identity

It may integrate with tools in those categories, but Studio’s identity is lab governance and promotion.

## 16. Product positioning

Bad positioning:

```text
Studio: tmux + Claude Code multi-agent harness
```

Better positioning:

```text
Studio: a human-in-the-loop lab operating system for turning directed research, source acquisition, and agent execution into durable systems and knowledge.
```

Shortest version:

```text
Studio governs the promotion of agent work into durable lab state.
```

## 17. Acceptance criteria for v0.2 direction

A future v0.2 should be considered successful if:

- The current harness still runs.
- A user can create an orientation as a file.
- A user can spawn a role-based dry-run claw.
- Every claw leaves an artifact bundle.
- Evidence claims can preserve provenance.
- Promotion candidates can be listed.
- Docs clearly distinguish implemented behavior from target direction.
- No secrets or external actions are granted implicitly.

## 18. Open questions

- Should `.studio` live inside each lab or at the federation root with per-lab sections?
- Should orientations be TOML, YAML, Markdown frontmatter, or JSONL?
- Should evidence live under `.intel/evidence/` or `research/evidence/`?
- Should source packs be part of spine or systems?
- Should Bridge remain read-only forever, dispatching mutations to primitives?
- What is the smallest useful capability enforcement in v0.2?
- How much runtime adapter abstraction should exist before Claude-first behavior is stable?

## 19. Summary

Studio’s durable architecture is:

```text
Director orients labs.
Labs acquire evidence and build tools.
Supervisors coordinate.
Claws execute bounded work.
Artifacts preserve provenance.
Verification checks outputs.
The director promotes durable state.
Spine makes learning reusable.
Federation lets one director operate many labs.
```

That is the app.