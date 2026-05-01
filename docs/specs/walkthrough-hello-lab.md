# Walkthrough: hello-lab

A guided tour of `examples/hello-lab/` that explains how each file maps to the
Studio lab OS spec. Read this alongside the spec at
`docs/specs/studio-lab-os-spec.md`.

---

## 1. The lab root and its kinds

```
examples/hello-lab/
├── surfaces/              public-facing outputs
├── research/
│   └── investigations/    research efforts with evidence and cycles
├── systems/               internal tools, infra, lab capabilities
├── runbooks/              spine: operational procedures
├── decisions/             spine: architecture decision records
├── .claude/
│   └── skills/            spine: invocable skill scripts
├── .studio/               control plane (file-backed config)
└── .claws/                artifact bundles from claw runs
```

The top-level directories correspond to the three lab kinds defined in spec §5.3:

- `surfaces/` — public-facing or user-facing output.
- `research/investigations/` — research effort with evidence, questions, and budget.
- `systems/` — internal tools, infrastructure, and lab capabilities.

`runbooks/`, `decisions/`, and `.claude/skills/` make up the **spine** (spec §5.8):
the lab's reusable operating memory. Spine is git-native — durable knowledge is
inspectable, diffable, and reviewable.

The `.studio/` and `.claws/` directories are new in this arc. The rest of the
directory shape is the v0 baseline described in spec §3.

---

## 2. The `.studio/` control plane

The control plane is file-backed. Studio prefers plain files over hidden runtime
state (spec §6). Each TOML file governs one dimension of how the lab operates.

### `lab.toml`

```toml
id = "hello-lab"
title = "Hello Lab"
kind = "investigation"
version = 1
```

Defines the lab's identity and kind. The `[paths]` section maps logical concepts
(surfaces, investigations, spine) to the directories above so that future tooling
can resolve them without hard-coding paths. Spec §7.1 defines the full schema.

### `orientations.toml`

```toml
[[orientation]]
id = "orient-hello-lab-studio-exploration"
lab = "investigation/studio-exploration"
objective = "Explore the Studio repo structure and document how the lab OS primitives fit together."
status = "draft"
stop_rule = "director_review_after_first_spec"
roles = ["scout", "researcher", "curator"]
sources = ["studio-current-repo"]
```

An orientation is the director's explicit intent for a lab (spec §5.4). It answers:
what is the lab pointed at, why does it matter, which sources are in scope, which
roles should run, and when should work stop for review. The `stop_rule` field is
the trigger for the director promotion gate — in this case, after the first spec
is produced.

The `[orientation.constraints]` block prevents unintended side-effects: no
untrusted code execution, no dependency installs, provenance required on every
claim.

This orientation is in `status = "draft"` — it has not been activated. It is a
declaration of intent.

### `roles.toml`

Defines the six claw roles and their output contracts (spec §5.6):

| Role | Purpose | Key outputs |
|------|---------|-------------|
| `scout` | Find and capture sources and signals | `evidence.jsonl`, `result.md` |
| `researcher` | Synthesize evidence into analysis | `result.md`, `evidence.jsonl` |
| `builder` | Build tools, systems, surfaces | `changes.patch`, `result.md`, `trace.jsonl` |
| `reviewer` | Verify, critique, and test | `review.md`, `trace.jsonl` |
| `operator` | Run approved workflows externally | `trace.jsonl`, `result.md` |
| `curator` | Graduate reusable knowledge to spine | `runbook_candidate.md`, `skill_candidate.md` |

Each role specifies a `default_runtime` and `default_capability`. These are
defaults — a claw spawn can override them if the orientation requires it.

### `capabilities.toml`

Defines what each capability profile permits (spec §7.4 and §9):

- `research_readonly` — filesystem read + artifact write, network on ask, no shell.
  Used by `scout` and `researcher`.
- `build_worktree` — worktree isolation, allowlisted shell, git and tests available.
  Used by `builder`.
- `operator_scoped` — restricted network, allowlisted shell, scoped secrets only.
  Used by `operator`.

The `promotion = "human"` field on every profile means no claw outcome enters
durable lab state without the director's explicit decision. This is the core rule
from spec §2: "The director promotes."

### `runtimes.toml`

Three runtime entries: `claude` (interactive), `claude_print` (`claude -p`,
one-shot), and `codex` (future). The `status` field on each entry distinguishes
what is implemented now from what is planned — a pattern the spec emphasizes
throughout (spec §7.5).

### `promotion.toml`

Lists the allowed promotion outcomes (spec §12):

- `abandon` — discard the work.
- `keep_evidence` — preserve the artifact bundle for the record, nothing promoted.
- `continue` — queue another claw on the same thread.
- `merge` — merge a worktree diff into the lab.
- `publish` — move output to a surface.
- `graduate_to_spine` — promote a runbook, skill, or decision into the lab's spine.

The `[checks.default]` block defines what a claw must produce before its output
can enter the promotion queue: a result, meta, trace, and explicit director
approval.

### `sources.toml`

Lists the sources in scope for this lab's orientations. Each entry names a
`source_pack` — the reusable acquisition bundle that knows how to acquire evidence
from that class of source (spec §5.9, §11). `github-repo-research` is the pack
name; it does not yet exist as a concrete directory, but the reference points at
where one would live.

---

## 3. The `.claws/<id>/` artifact bundle

The example bundle lives at:

```
.claws/20260501-150000-scout-hello-lab/
├── meta.json
├── trace.jsonl
├── evidence.jsonl
└── result.md
```

This is a **fixture** — hand-written to illustrate the artifact contract (spec §8).
The v0 harness does not yet emit these bundles automatically. They exist so that
readers can see the expected shape and so that future tooling has a concrete target.

### `meta.json` — what ran

```json
{
  "id": "20260501-150000-scout-hello-lab",
  "orientation_id": "orient-hello-lab-studio-exploration",
  "lab_slug": "investigation/studio-exploration",
  "role": "scout",
  "runtime": "claude_print",
  "capability_profile": "research_readonly",
  "source_scope": ["studio-current-repo"],
  "status": "finished",
  "started_at": "2026-05-01T15:00:00Z",
  "ended_at": "2026-05-01T15:12:00Z",
  "promotion_recommendation": "keep_evidence"
}
```

`meta.json` is the envelope. It records provenance: which orientation triggered
this claw, what role ran, which runtime and capability profile were used, and
what sources were in scope. The `promotion_recommendation` is the claw's own
suggestion — the director is not bound by it.

### `trace.jsonl` — what happened

Each line records a meaningful action the claw took during execution (spec §8.2):

```jsonl
{"ts":"2026-05-01T15:01:00Z","event":"source_opened","source":"studio-current-repo","path":"README.md"}
{"ts":"2026-05-01T15:05:00Z","event":"claim_extracted","claim_id":"claim-001"}
{"ts":"2026-05-01T15:11:00Z","event":"result_written","path":"result.md"}
```

The trace is the audit record. It lets the director (and future verification
claws) reconstruct what the claw did without re-running it.

### `evidence.jsonl` — what was found

Each line is a claim with provenance (spec §8.3):

```jsonl
{"id":"claim-001","claim":"Studio separates harness from lab data via CGL_LAB_ROOT.","source":"https://github.com/calenwalshe/studio","support":"README.md mental model section; install.sh reads CGL_LAB_ROOT.","confidence":"high"}
```

Provenance is mandatory in `research_readonly` capability profiles. Each claim
links back to the source location that supports it. A reviewer claw or the
director can open those sources directly to check.

### `result.md` — what to decide

The human-readable summary. It includes a narrative summary of what the claw
found, the evidence collected (with claim IDs that cross-reference `evidence.jsonl`),
and a promotion recommendation section that restates what `meta.json` records
in prose. This is the document the director reads when deciding what to promote.

---

## 4. The promotion gate

The example claw recommends `keep_evidence`. Here is what that means and how
the director responds.

`keep_evidence` means: the artifact bundle is worth preserving, but nothing is
ready to be promoted to durable lab state yet. The evidence in `evidence.jsonl`
may inform a future researcher claw or an investigation update, but no merge, no
publish, no spine graduation is implied.

The director's decision flow for this claw:

1. Read `result.md` — is the scout's summary useful?
2. Verify a sample of claims in `evidence.jsonl` — do the source citations hold?
3. Decide:
   - **abandon** — the work is not useful; discard the bundle.
   - **keep_evidence** — agree with the recommendation; archive the bundle.
   - **continue** — spawn a researcher claw to synthesize these findings.
   - Graduate specific items if any claim warrants immediate spine promotion.

The director is the only one who can advance an outcome. No automated path
bypasses the gate (see `promotion.toml`: `require_director_approval = true`).

---

## 5. What is not implemented yet

The files in `.studio/` and `.claws/` are contracts, not behavior. Specifically:

- `cgl-orient` — the CLI to create and list orientations — does not exist yet.
- `cgl-claw spawn --orientation <id> --role <role>` — the command to run a
  role-based claw and write an artifact bundle — does not exist yet.
- The capability gateway (spec §9) is not enforced. Capabilities are declared in
  `capabilities.toml` but nothing prevents a claw from acting outside its profile.
- The promotion queue in the Bridge (spec §12) is not implemented. Promotion
  decisions happen out-of-band today.
- Source packs (spec §11) are named in `sources.toml` but do not yet exist as
  concrete directories with connectors and schemas.

These are tracked in the spec's implementation roadmap (spec §14) under Arc B
(dry-run CLI) and Arc C (promotion queue and capability checks).

The v0 harness — `cgl-tmux`, `cgl-labs`, `cgl-supervisor`, `cgl-claw` — works
today and is unaffected by this arc. The new files are additive.
