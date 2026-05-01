# Studio Lab OS — Test Suite

## Running the tests

```bash
# Fast tests only (default — no claude calls):
studio/.venv/bin/pytest -m "not slow" -v

# All tests including slow persona test:
studio/.venv/bin/pytest -v

# Shell-based CLI tests:
./tests/test_orient_cli.sh
```

Run from the project root. The shell script sets `CGL_LAB_ROOT` to `examples/hello-lab`
and adds `bin/` to PATH automatically.

Requires: bash 4+, python3, jq, pytest 8+.

---

## Test files

### `test_loaders.py`
Unit tests for `studio/lab_tui/loaders.py`.
Covers: `discover_labs`, `load_lab_summary`, `load_claw_bundles`, status derivation,
and error handling for missing `.studio/lab.toml`.

### `test_cockpit_snapshot.py`
Visual regression tests using `pytest-textual-snapshot`.
Captures SVG screenshots of the Studio Cockpit and compares to saved baselines.

Two tests:
- `test_cockpit_federation_home` — cockpit at rest with hello-lab loaded
- `test_cockpit_after_enter` — cockpit after pressing `enter` (notification visible)

Baselines live in `tests/__snapshots__/test_cockpit_snapshot/`.

**Regenerate baselines** (after intentional UI changes):
```bash
CGL_LAB_ROOT=examples/hello-lab studio/.venv/bin/pytest tests/test_cockpit_snapshot.py --snapshot-update
```

Note: The snapshot tests use a `StableCockpitApp` subclass with `show_clock=False`.
This prevents the live clock in the header from changing the SVG between runs
and causing false failures.

### `test_persona.py`
LLM persona integration test. Calls `claude -p` via subprocess (~30-60s per run).
Marked `@pytest.mark.slow` — excluded by default.

**Run the persona test:**
```bash
studio/.venv/bin/pytest tests/test_persona.py -v -m slow
```

**Skip slow tests** (CI default):
```bash
studio/.venv/bin/pytest -m "not slow"
```

The test verifies that the persona finds `hello-lab` in its findings within 8 steps.
Requires `claude` CLI on PATH.

### `test_orient_cli.sh`
Shell-based tests for the `cgl-orient` and `cgl-claw` CLI tools.

---

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
- `discover_labs`, `load_lab_summary`, `load_claw_bundles` — data layer
- Studio Cockpit visual layout — SVG snapshot regression
- Persona navigation — LLM-driven cockpit interaction

## What is NOT covered

- Real claude execution in loaders — no `claude -p` or `claude` process is invoked
  in the unit tests. Arc B is dry-run only.
- Arc C features: real orientation-driven claw execution, capability gateway
  enforcement, promotion queue integration. These arrive in Arc C.
- Non-dry-run orientation spawn (the shell script intentionally exits 2 for that path).
- Multi-orientation fixtures — all tests run against `examples/hello-lab` only.
