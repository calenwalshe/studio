# Artifact Bundle Contract — `.claws/<id>/`

> Arc A.2 — Artifact bundle specification.
> Status: Draft. Implements §8 of the Studio Lab OS spec.

## Overview

Every claw execution must leave a self-contained artifact bundle at `.claws/<id>/`. The bundle is the authoritative record of what the claw did, what it found, and what the director should do next. Bundles are append-only; a claw writes them once and does not modify them after finishing.

---

## Directory Layout

```text
.claws/<id>/
  meta.json          # machine-readable run metadata and outcome
  result.md          # human-readable summary and promotion recommendation
  trace.jsonl        # append-only action log (one JSON object per line)
  evidence.jsonl     # extracted claims with provenance (one claim per line)
  changes.patch      # unified diff of file changes (builder/reviewer claws only)
  screenshots/       # optional captured images (builder/reviewer claws only)
```

Scout and researcher claws typically omit `changes.patch` and `screenshots/`. Builder and reviewer claws produce all files.

---

## `<id>` Format

```
YYYYMMDD-HHMMSS-<role>-<lab-slug-safe>
```

| Component | Description |
|---|---|
| `YYYYMMDD` | UTC date of run start |
| `HHMMSS` | UTC time of run start (24-hour) |
| `<role>` | One of: `scout`, `researcher`, `builder`, `reviewer`, `operator`, `curator` |
| `<lab-slug-safe>` | Lab slug with `/` replaced by `-` and any non-`[a-z0-9-]` characters removed |

Example: `20260501-150000-scout-hello-lab`

---

## `meta.json` — Field Reference

`meta.json` is a single JSON object. All fields are required unless marked optional.

| Field | Type | Description |
|---|---|---|
| `id` | string | Artifact bundle ID. Must match the directory name. |
| `orientation_id` | string | ID of the orientation that spawned this claw (matches `orientations.toml`). |
| `lab_slug` | string | Lab path/slug identifying the lab (e.g. `investigation/agent-infra`). |
| `role` | string | Claw role. One of: `scout`, `researcher`, `builder`, `reviewer`, `operator`, `curator`. |
| `runtime` | string | Runtime adapter used. One of: `claude`, `claude_print`, `codex`. |
| `capability_profile` | string | Capability profile name as defined in `capabilities.toml`. |
| `source_scope` | array of string | List of source keys in scope for this run (from `sources.toml`). May be empty `[]`. |
| `status` | string | Terminal status of the run. One of: `finished`, `error`, `abandoned`. |
| `started_at` | string | RFC3339 UTC timestamp when the claw started. |
| `ended_at` | string | RFC3339 UTC timestamp when the claw finished. |
| `promotion_recommendation` | string | The claw's recommendation for the director. One of: `abandon`, `keep_evidence`, `continue`, `merge`, `publish`, `graduate_to_spine`. |

### Example `meta.json`

```json
{
  "id": "20260501-150000-scout-hello-lab",
  "orientation_id": "orient-hello-lab-studio-exploration",
  "lab_slug": "hello-lab",
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

---

## `trace.jsonl` — Trace Event Schema

Each line of `trace.jsonl` is a JSON object recording one meaningful action taken by the claw. Lines are append-only in chronological order.

### Required fields on every event

| Field | Type | Description |
|---|---|---|
| `ts` | string | RFC3339 UTC timestamp of the event. |
| `event` | string | Event type (see below). |

### Event types and their additional fields

#### `source_opened`

Emitted when the claw opens or fetches a source for reading.

| Field | Type | Description |
|---|---|---|
| `source` | string | Source key (from `sources.toml`) or URL. |
| `path` | string | File path or URL path within the source. |

```json
{"ts":"2026-05-01T15:01:00Z","event":"source_opened","source":"studio-current-repo","path":"docs/specs/studio-lab-os-spec.md"}
```

#### `claim_extracted`

Emitted when the claw extracts a claim to write to `evidence.jsonl`.

| Field | Type | Description |
|---|---|---|
| `claim_id` | string | The `id` value of the claim in `evidence.jsonl`. |
| `source` | string | Source key or URL the claim was drawn from. |

```json
{"ts":"2026-05-01T15:05:00Z","event":"claim_extracted","claim_id":"claim-001","source":"studio-current-repo"}
```

#### `tool_called`

Emitted when the claw invokes a tool (shell, API, MCP, etc.).

| Field | Type | Description |
|---|---|---|
| `tool` | string | Tool name (e.g. `web.fetch`, `shell`, `github.fetch`). |
| `input` | object | Key inputs passed to the tool. May be omitted or redacted for sensitive tools. |
| `outcome` | string | One of: `ok`, `error`, `skipped`. |

```json
{"ts":"2026-05-01T15:06:00Z","event":"tool_called","tool":"web.fetch","input":{"url":"https://github.com/bradAGI/awesome-cli-coding-agents"},"outcome":"ok"}
```

#### `file_modified`

Emitted when the claw writes or modifies a file (builder/reviewer claws).

| Field | Type | Description |
|---|---|---|
| `path` | string | File path relative to the worktree root. |
| `operation` | string | One of: `created`, `modified`, `deleted`. |

```json
{"ts":"2026-05-01T15:09:00Z","event":"file_modified","path":"systems/etl-pipeline/main.py","operation":"created"}
```

#### `error`

Emitted when a recoverable or non-recoverable error occurs.

| Field | Type | Description |
|---|---|---|
| `message` | string | Human-readable error description. |
| `recoverable` | boolean | Whether the claw continued after the error. |
| `tool` | string (optional) | Tool that caused the error, if applicable. |

```json
{"ts":"2026-05-01T15:10:00Z","event":"error","message":"Rate limit hit on web.fetch","recoverable":true,"tool":"web.fetch"}
```

#### `finished`

Always the last event. Summarises the run.

| Field | Type | Description |
|---|---|---|
| `status` | string | Final run status: `finished`, `error`, or `abandoned`. |
| `claims_count` | integer | Number of claims written to `evidence.jsonl`. |
| `promotion_recommendation` | string | Same value as `meta.json` `promotion_recommendation`. |

```json
{"ts":"2026-05-01T15:12:00Z","event":"finished","status":"finished","claims_count":3,"promotion_recommendation":"keep_evidence"}
```

---

## `evidence.jsonl` — Evidence Claim Schema

Each line is a JSON object representing one extracted claim with full provenance.

### Required fields

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique claim identifier within this bundle (e.g. `claim-001`, `claim-002`). |
| `claim` | string | Precise, falsifiable statement of what was found. |
| `source` | string | URL or source key where the evidence was found. |
| `support` | string | Verbatim quote or paraphrase of the supporting evidence with enough context to verify. |
| `confidence` | string | One of: `low`, `medium`, `high`. |

### Confidence guidance

| Value | Meaning |
|---|---|
| `low` | Circumstantial, inferred, or single ambiguous signal. |
| `medium` | Multiple corroborating signals or a clear but non-definitive source. |
| `high` | Directly stated by the source with no ambiguity; multiple independent confirmations. |

### Example `evidence.jsonl`

```json
{"id":"claim-001","claim":"Studio v0 uses tmux sessions as the supervisor primitive.","source":"https://github.com/calenwalshe/studio","support":"bin/cgl-supervisor shows tmux new-session calls; docs/concepts.md states 'Supervisor — persistent Claude session for a lab'.","confidence":"high"}
{"id":"claim-002","claim":"Claws are intended to run in ephemeral git worktrees.","source":"https://github.com/calenwalshe/studio","support":"ADR 0003 (docs/adrs/0003-claws-in-ephemeral-worktrees.md) records this decision.","confidence":"high"}
{"id":"claim-003","claim":"The promotion gate currently has no automated enforcement.","source":"https://github.com/calenwalshe/studio","support":"promotion.toml requires director approval but there is no corresponding CLI command or check script in bin/.","confidence":"medium"}
```

---

## `result.md` — Template

`result.md` is the human-readable summary of the claw run. It is the primary artifact a director reads when deciding what to promote.

```markdown
# Result — <id>

**Role:** <role>
**Orientation:** <orientation_id>
**Lab:** <lab_slug>
**Status:** <status>
**Run:** <started_at> → <ended_at>

---

## Summary

<1–3 paragraphs describing what the claw did and what it found. Write for a
director who has not read any other files in this bundle.>

---

## Evidence collected

<Summarise the claims in evidence.jsonl. Reference claim IDs where helpful.
Separate strong evidence from weak.>

---

## Recommendations

<What the director should do next. Be specific. List concrete follow-on claws,
decisions, or promotions if warranted.>

---

## Promotion recommendation

<One of: abandon | keep_evidence | continue | merge | publish | graduate_to_spine>
```

### Promotion recommendations — valid values and meaning

Claws emit *recommendations*. The director makes the *decision*.

| Value | Meaning |
|---|---|
| `abandon` | Work is not useful; no evidence worth keeping. Director should discard the bundle. |
| `keep_evidence` | The run found useful evidence but no action is needed now. Evidence should flow to `.intel/`. |
| `continue` | More work is needed on the same orientation. Suggest spawning another claw of the same or different role. |
| `merge` | A builder claw produced code changes ready for the director to review and merge. |
| `publish` | A surface or document is ready to publish externally. |
| `graduate_to_spine` | A pattern, runbook, or skill is mature enough to promote into spine. |

These values correspond to the outcomes defined in `promotion.toml` (`§7.6`). The spec §12 lists the same set as director-level *outcomes*; the distinction is that the claw recommends and the director decides.

---

## `changes.patch` (builder/reviewer claws only)

A unified diff (`git diff`) of all file changes made during the claw run, relative to the worktree base branch. Omitted by scout, researcher, operator, and curator claws.

## `screenshots/` (builder/reviewer claws only)

Directory of PNG or JPEG screenshots captured during the run. Each file should be named `<sequence>-<description>.png` (e.g. `01-initial-state.png`, `02-after-build.png`). Omitted when no visual verification was performed.

---

## Spec cross-references

| Section | Topic |
|---|---|
| §6 | File-backed control plane — full lab directory layout |
| §7.6 | `promotion.toml` — allowed outcomes and candidate types |
| §8.1 | `meta.json` example |
| §8.2 | `trace.jsonl` examples |
| §8.3 | `evidence.jsonl` example |
| §8.4 | `result.md` template |
| §12 | Promotion queue — candidate types and outcomes |
