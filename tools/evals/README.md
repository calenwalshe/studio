# Studio Eval Harness

A lightweight eval framework for the Studio TUI. Scenarios are YAML files that
define persona steps and a rubric of checkable assertions. The harness runs each
scenario through the existing capture driver, scores the results, and augments
the persona viewer with an Eval Score badge and detail panel.

## What is an eval scenario?

A scenario is a YAML file that specifies:

- **persona** — who is running the session (e.g. `director`)
- **lab_root** — federation root used as the cockpit's `CGL_LAB_ROOT`
- **timeout** — per-question timeout in seconds
- **steps** — an ordered list of mixed interactions: chat messages, keypresses, or direct actions
- **rubric** — a list of checkable assertions to score after the run

## Scenario YAML schema

```yaml
name: <slug>               # short identifier, used in run_id and reports
description: <string>      # human-readable description of the scenario
persona: director          # persona slug (currently always "director")
lab_root: <path>           # relative to studio-tui/ root
timeout: 120               # per-chat-step timeout in seconds
budget_blocks: 2           # optional hint for agent budget mode

steps:
  - chat: "<question text>"
  - keypress: { key: <key>, label: "<human label>" }
  - action: { type: <action_name>, <extra kwargs...> }

rubric:
  - id: <check_id>
    description: "<human description>"
    check: { type: <check_type>, <check params...> }
```

## Rubric check types

| Check type | Parameters | Description |
|---|---|---|
| `response_line_count` | `step`, `min?`, `max?` | Count lines in response at the given step index |
| `response_contains` | `step`, `text` | Response must contain the literal string |
| `response_not_contains` | `step`, `text` | Response must NOT contain the literal string |
| `response_mentions_any` | `step`, `options: [...]` | Response contains at least one option (case-insensitive) |
| `file_exists` | `path` | Path (with `{template}` vars) must exist on disk |
| `file_json_field` | `path`, `field`, `in: [...]` or `equals` | JSON field in file must match constraint |

Path templates support `{lab_root}`, `{first_lab}`, and `{promoted_claw_id}`. Full
template variable resolution is planned for Arc 3.

## Running a scenario

```bash
studio/.venv/bin/python tools/eval_harness.py tools/evals/scenarios/01-basic-triage.yaml
```

With a custom output directory:

```bash
studio/.venv/bin/python tools/eval_harness.py \
    tools/evals/scenarios/02-long-form.yaml \
    --output-dir tools/persona_runs
```

Exit code is 0 on overall PASS, 1 on FAIL. Results are written to
`tools/persona_runs/<run_id>/manifest.json` with an `eval` block and displayed
in the persona viewer with an `[EVAL: XX%]` badge.

## Arc 3

Arc 3 will add:
- Chat-tier scenarios that exercise the Chief of Staff / Lab Agent split
- Template variable population from action outcomes (`first_lab`, `promoted_claw_id`)
- `tmp_copy_of(...)` lab_root copying so action scenarios don't mutate fixtures
