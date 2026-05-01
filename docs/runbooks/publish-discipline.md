# Runbook — Publish discipline

A small set of rules for any "publish" action the harness or its labs do.

## Rules

1. **Publish is a deliberate action.** Never auto-publish from a Bridge tick
   or a claw exit. A human (or a deliberate command) makes the call.

2. **Log every publish to `<lab>/intel/publish-log.jsonl`.** Each line has:
   `{ts, slug, action, target, sha, dollars}`.

3. **Static surfaces deploy via two-write pattern:** write to the lab's
   `web/<host>/<surface>/`, then sync to the served path. Both writes go
   into the publish log.

4. **Sync is idempotent.** Re-running a sync produces no change unless
   the source actually changed. Don't trigger downstream churn on no-op.

5. **Failures are loud.** A failed publish writes a failure line to the
   publish log AND surfaces in the Bridge. No silent skips.

6. **Rollback is by reverting commits + republishing.** No "deploy a
   previous version" mechanism. The git history is the deploy history.

## When this matters

- Surface labs whose output lives on a webserver
- Investigation labs whose final report goes to a public location
- Any time a primitive copies lab content outside `$CGL_LAB_ROOT`

## Convention check

If your harness operations don't write to `intel/publish-log.jsonl`,
they don't count as a publish. The audit trail IS the publish log.
