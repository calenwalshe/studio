# Studio Lab OS — Test Suite

## Running the tests

```
./tests/test_orient_cli.sh
```

Run from anywhere. The script sets `CGL_LAB_ROOT` to `examples/hello-lab` and
adds `bin/` to PATH automatically.

Requires: bash 4+, python3, jq.

## What is covered

- `cgl-orient validate` — exits 0, prints "ok:" for the hello-lab fixture
- `cgl-orient list` — exits 0, lists the hello-lab orientation ID
- `cgl-orient show <id>` — exits 0, prints orientation fields including "objective"
- `cgl-orient show <nonexistent>` — exits 1, stderr includes "not found"
- `cgl-claw spawn --orientation ... --role scout --dry-run` — exits 0, writes a
  valid artifact bundle (meta.json, trace.jsonl, result.md), meta has
  `"status": "dry_run"`, trace first line has `"event": "dry_run"`. Bundle is
  cleaned up at end of test run.
- `cgl-claw spawn --orientation ... --role builder --dry-run` — exits 1 when
  the role is not in the orientation's allowed roles list, stderr describes the
  mismatch.

## What is NOT covered

- Real claude execution — no `claude -p` or `claude` process is invoked. Arc B
  is dry-run only.
- Arc C features: real orientation-driven claw execution, capability gateway
  enforcement, promotion queue integration. These arrive in Arc C.
- Non-dry-run orientation spawn (the script intentionally exits 2 for that path).
- Multi-orientation fixtures — all tests run against `examples/hello-lab` only.
