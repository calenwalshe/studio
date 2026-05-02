# Judges

Two LLM judges that grade an Examiner session after it completes.

## judge_workflow_completion

Checks whether the Examiner executed the canonical steps of a workflow and
whether the expected filesystem artifacts are present.

**Inputs:**
- `transcript: list[dict]` — Examiner session transcript
- `workflow: dict` — loaded YAML for the workflow being executed
- `lab_root: Path` — working federation copy at `/tmp/examiner-fed-work`

**Return shape:**
```python
{
  "score": 0.0 to 1.0,                     # (steps_done + artifacts_present) / total
  "passed": bool,                           # score >= 0.75 and at least one artifact present
  "reasoning": str,                         # 2-4 sentences from the judge LLM
  "canonical_steps_executed": [bool, ...],  # one per workflow.canonical_steps
  "expected_artifacts_present": [bool, ...] # deterministic filesystem check, NOT LLM-inferred
}
```

The `expected_artifacts_present` list is always determined by actual filesystem
inspection, not by the judge LLM. Artifact patterns support `<lab>`, `<claw_id>`,
`<new-bundle-id>`, `<new-slug>`, and `<federation>` tokens that expand to all
matching paths under `lab_root`.

## judge_reasoning_quality

For each chat-type turn in the transcript, grades the agent's reply on three
dimensions: scope discipline, evidence grounding, and honest acknowledgement of
gaps.

**Inputs:**
- `transcript: list[dict]` — same shape as above
- `lab_root: Path` — used to render a federation snapshot as ground truth

**Return shape:**
```python
{
  "score": 0.0 to 1.0,   # mean of per_response scores
  "per_response": [
    {
      "turn": int,
      "score": 0.0 to 1.0,
      "scope_discipline": "ok|violated",
      "evidence_grounded": "ok|hallucinated|underspecified",
      "honest_about_gaps": bool,
      "issues": [str, ...]
    }
  ]
}
```

Per-response scoring: 1.0 if all dimensions pass and no major issues; 0.5 for a
minor issue; 0.0 for a scope violation or hallucinated claim.

## Examiner integration

Build A calls the judges at the end of each session:

```python
from tools.evals.judges import judge_workflow_completion, judge_reasoning_quality

workflow_judgment = await judge_workflow_completion(transcript, workflow, lab_root)
quality_judgment  = await judge_reasoning_quality(transcript, lab_root)
```

Both functions are `async` and run `claude -p` as a subprocess with
`ANTHROPIC_API_KEY` removed (forces subscription billing). Each call retries
once on JSON parse failure.
