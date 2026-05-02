# Examiner — Studio TUI Test Pilot

The Examiner is a long-running, stateful test persona that methodically exercises every Studio cockpit feature across many sessions.

Unlike a one-shot scenario persona, the Examiner:
- Persists state in `state.json` across sessions
- Picks workflows from `tools/evals/workflows/` based on coverage gaps
- Maintains a findings ledger in `findings.jsonl`
- Has a reactive loop — reads cockpit screen each turn, asks an LLM to decide the next action
- Logs surprises as findings as it goes
- Rebuilds `coverage.md` after each session

## Running a Session

Tell me: "Run the Examiner for up to 20 turns" or "Run the Examiner on the triage-and-promote workflow".

Underlying command:
```
studio/.venv/bin/python tools/evals/examiner/examiner.py [--max-turns N] [--workflow WORKFLOW_ID]
```

- `--max-turns` defaults to 30
- `--workflow` forces a specific workflow id; otherwise the Examiner picks the next uncovered one

The session uses a fresh copy of `examples/federation-demo/` at `/tmp/examiner-fed-work` — the committed fixture is never mutated.

## File Layout

```
tools/evals/examiner/
  examiner.py          # main module
  state.json           # persisted cross-session state (auto-created)
  findings.jsonl       # one JSON object per line, sequential F-NNN ids
  coverage.md          # rebuilt each session from state.json
  sessions/
    <session-id>/
      manifest.json    # full transcript + judgments + findings for this session
      turn-NNN-before.png / turn-NNN-after.png
```

### state.json shape

```json
{
  "started_at": "ISO timestamp",
  "session_count": 3,
  "workflows_covered": ["triage-and-promote"],
  "workflows_remaining": ["lab-chat-deep-dive"],
  "features_exercised": {"chief_chat": 7, "lab_expansion": 4},
  "open_issues": ["F-001", "F-003"],
  "next_session_priority": null
}
```

### findings.jsonl shape

```
{"id": "F-001", "severity": "medium", "kind": "bug", "summary": "...", "evidence": "...", "session": "...", "workflow": "...", "turn": 4}
```

## Judge Integration

At the end of each session, the Examiner calls:

- `judge_workflow_completion(transcript, workflow, lab_root)` — did the workflow intent get fulfilled?
- `judge_reasoning_quality(transcript, lab_root)` — per-turn quality scores

These are provided by Build B (`tools/evals/judges.py`). If unavailable, the Examiner records a placeholder and continues.

## Build C

A separate agent (Build C) runs many sessions in sequence and publishes the results. The Examiner itself only runs one session per invocation.
