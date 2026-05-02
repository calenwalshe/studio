# federation-demo

This is the multi-lab teaching fixture for Studio. It demonstrates the cockpit
at the scale it was designed for: a federation of 5 labs with varied statuses,
giving the director something interesting to triage.

## Labs

| Lab               | Kind          | Status       | Demonstrates                                              |
|-------------------|---------------|--------------|-----------------------------------------------------------|
| hello-lab         | investigation | needs_review | Single scout claw with keep_evidence recommendation       |
| surface-snake     | surface       | idle         | Finished builder claw (abandon rec), no director action needed |
| agent-infra       | investigation | needs_review | 3 claws: scout (keep_evidence) + researcher (merge) + abandoned scout |
| distribution-engine | systems     | stale        | Orientation defined, no claws spawned yet                 |
| cgl-publish       | systems       | needs_review | Builder claw with merge recommendation + changes.patch    |

## Status key

- `!` needs_review — one or more bundles require director decision
- `O` idle — claws finished, nothing pending review
- `o` stale — orientation exists but no claws have run
- `x` error — lab configuration is broken

## How to launch

From the studio-tui repo root:

```
CGL_LAB_ROOT=$(pwd)/examples/federation-demo bin/cgl-cockpit
```

Or with an explicit python invocation:

```
CGL_LAB_ROOT=$(pwd)/examples/federation-demo studio/.venv/bin/python studio/lab_tui/cockpit.py
```

## What each lab demonstrates

**hello-lab** — The baseline single-lab fixture. One scout claw with a
keep_evidence recommendation. The director needs to decide whether to promote
the evidence to .intel/.

**surface-snake** — A finished builder claw that produced a working snake game
surface. The recommendation is abandon: the build work is complete, the board
renders, and no director action is needed. The evidence is documented inline in
result.md. Status is idle because there are completed bundles but none require
director review. The next step (CDN deploy) depends on cgl-publish.

**agent-infra** — Three claws spanning two days of investigation: an initial
scout pass (keep_evidence), a researcher synthesis (merge-ready), and an
abandoned false-start (abandon). The lab shows needs_review because two of the
three bundles have non-abandon recommendations. The abandoned bundle is excluded
from the promotion count.

**distribution-engine** — An orientation has been written but no claw has been
spawned yet. The director has not yet kicked off the investigation. Status is
stale. This is the "work waiting on director" signal.

**cgl-publish** — A builder claw that implemented bin/cgl-publish and is ready
to merge. Includes a changes.patch artifact with the actual bash script diff.
The director needs to review and approve the merge.
