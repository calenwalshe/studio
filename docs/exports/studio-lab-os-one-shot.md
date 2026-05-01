# Studio Lab OS — One-Shot Public Export

> Created from ChatGPT as a public Markdown export.

Studio is a human-in-the-loop lab operating system for director-oriented intelligence work.

The director orients a lab toward a source, question, system, market, dataset, repo, workflow, or build goal. Studio then coordinates supervisors and bounded claws to acquire evidence, build tools, synthesize findings, verify outputs, and promote durable work into systems, surfaces, investigations, runbooks, skills, and decisions.

## Core loop

```text
Director orients
  ↓
Lab acquires evidence
  ↓
Supervisor coordinates
  ↓
Role-based claws execute bounded work
  ↓
Artifacts preserve provenance
  ↓
Verification checks outputs
  ↓
Director promotes durable state
  ↓
Spine makes learning reusable
```

## Core rule

```text
Agents may act in bounded contexts.
Studio records, routes, and summarizes.
The director promotes.
```

## Target primitives

- **Director** — the human in the loop.
- **Federation** — cross-lab control and status view.
- **Lab** — bounded domain of work and governance.
- **Orientation** — what the lab is pointed at right now.
- **Supervisor** — persistent coordinator for a lab.
- **Claw** — bounded execution worker.
- **Capability Gateway** — decides what a claw may do.
- **Execution Envelope** — runtime, sandbox, tools, secrets, and audit trace.
- **Artifact Bundle** — logs, results, traces, evidence, diffs, screenshots.
- **Promotion Gate** — human decision point.
- **Spine** — reusable skills, runbooks, ADRs, and source packs.

## Positioning

Studio is not just a tmux + Claude Code session manager. It is a governance layer for turning directed research, acquisition, and agent execution into durable lab state.
