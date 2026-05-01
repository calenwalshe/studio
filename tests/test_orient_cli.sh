#!/usr/bin/env bash
# tests/test_orient_cli.sh — CLI integration tests for cgl-orient and cgl-claw
# orientation-driven spawn (Arc B).
#
# Run from any directory:
#   ./tests/test_orient_cli.sh
#
# Requirements: CGL_LAB_ROOT is NOT set by the caller — the test sets it
# to examples/hello-lab so it operates against the bundled fixture.
# Requires: bash 4+, python3, jq

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Point at the hello-lab fixture
export CGL_LAB_ROOT="$REPO_ROOT/examples/hello-lab"

# Ensure harness bin is on PATH
export PATH="$REPO_ROOT/bin:$PATH"

PASS_COUNT=0
FAIL_COUNT=0

pass() {
  echo "PASS: $1"
  PASS_COUNT=$((PASS_COUNT + 1))
}

fail() {
  echo "FAIL: $1" >&2
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

assert_exit_0() {
  local label="$1"
  shift
  if "$@" > /tmp/assert_stdout 2>/tmp/assert_stderr; then
    return 0
  else
    echo "  command: $*" >&2
    echo "  stdout:  $(cat /tmp/assert_stdout)" >&2
    echo "  stderr:  $(cat /tmp/assert_stderr)" >&2
    fail "$label (non-zero exit)"
    return 1
  fi
}

assert_exit_nonzero() {
  local label="$1"
  local expected_rc="${2:-}"
  shift 2
  local actual_rc=0
  "$@" > /tmp/assert_stdout 2>/tmp/assert_stderr || actual_rc=$?
  if [[ "$actual_rc" -eq 0 ]]; then
    echo "  command: $*" >&2
    fail "$label (expected non-zero exit, got 0)"
    return 1
  fi
  if [[ -n "$expected_rc" && "$actual_rc" != "$expected_rc" ]]; then
    echo "  command: $*" >&2
    echo "  expected exit $expected_rc, got $actual_rc" >&2
    fail "$label (wrong exit code)"
    return 1
  fi
  return 0
}

assert_stdout_contains() {
  local label="$1"
  local pattern="$2"
  if grep -q "$pattern" /tmp/assert_stdout; then
    return 0
  else
    echo "  pattern '$pattern' not found in stdout" >&2
    echo "  stdout: $(cat /tmp/assert_stdout)" >&2
    fail "$label (stdout missing '$pattern')"
    return 1
  fi
}

assert_stderr_contains() {
  local label="$1"
  local pattern="$2"
  if grep -qi "$pattern" /tmp/assert_stderr; then
    return 0
  else
    echo "  pattern '$pattern' not found in stderr" >&2
    echo "  stderr: $(cat /tmp/assert_stderr)" >&2
    fail "$label (stderr missing '$pattern')"
    return 1
  fi
}

# ── Test 1: cgl-orient validate ──────────────────────────────────────────────

if assert_exit_0 "cgl-orient validate: exit 0" cgl-orient validate; then
  if assert_stdout_contains "cgl-orient validate: ok: in stdout" "ok:"; then
    pass "cgl-orient validate"
  fi
fi

# ── Test 2: cgl-orient list ──────────────────────────────────────────────────

if assert_exit_0 "cgl-orient list: exit 0" cgl-orient list; then
  if assert_stdout_contains \
      "cgl-orient list: orientation id in output" \
      "orient-hello-lab-studio-exploration"; then
    pass "cgl-orient list"
  fi
fi

# ── Test 3: cgl-orient show (known id) ───────────────────────────────────────

if assert_exit_0 \
    "cgl-orient show (known id): exit 0" \
    cgl-orient show orient-hello-lab-studio-exploration; then
  if assert_stdout_contains \
      "cgl-orient show: objective in output" \
      "objective"; then
    pass "cgl-orient show (known id)"
  fi
fi

# ── Test 4: cgl-orient show (nonexistent id) ─────────────────────────────────

assert_exit_nonzero "cgl-orient show (nonexistent): non-zero exit" "1" \
  cgl-orient show nonexistent-id || true

# Capture again to inspect stderr
cgl-orient show nonexistent-id > /tmp/assert_stdout 2>/tmp/assert_stderr || true
if assert_stderr_contains \
    "cgl-orient show (nonexistent): 'not found' in stderr" \
    "not found"; then
  pass "cgl-orient show (nonexistent id)"
fi

# ── Test 5: cgl-claw spawn --orientation --role scout --dry-run ──────────────

DRY_BUNDLE_DIR=""

cgl-claw spawn \
  --orientation orient-hello-lab-studio-exploration \
  --role scout \
  --dry-run \
  > /tmp/assert_stdout 2>/tmp/assert_stderr
EXIT_CODE=$?

if [[ "$EXIT_CODE" -ne 0 ]]; then
  echo "  stdout: $(cat /tmp/assert_stdout)" >&2
  echo "  stderr: $(cat /tmp/assert_stderr)" >&2
  fail "cgl-claw spawn --dry-run (scout): exit 0"
else
  # Find the new bundle dir (any dir under .claws that isn't the fixture)
  NEW_BUNDLE=""
  for d in "$CGL_LAB_ROOT/.claws"/*/; do
    bn="$(basename "$d")"
    if [[ "$bn" != "20260501-150000-scout-hello-lab" ]]; then
      NEW_BUNDLE="$d"
      break
    fi
  done

  if [[ -z "$NEW_BUNDLE" ]]; then
    fail "cgl-claw spawn --dry-run (scout): new bundle dir created"
  else
    DRY_BUNDLE_DIR="$NEW_BUNDLE"
    BUNDLE_OK=1

    for f in meta.json trace.jsonl result.md; do
      if [[ ! -f "$DRY_BUNDLE_DIR/$f" ]]; then
        fail "cgl-claw spawn --dry-run (scout): $f exists in bundle"
        BUNDLE_OK=0
      fi
    done

    if [[ "$BUNDLE_OK" -eq 1 ]]; then
      # Validate meta.json
      META_STATUS="$(python3 -c "import json,sys; d=json.load(open('$DRY_BUNDLE_DIR/meta.json')); print(d.get('status',''))")"
      if [[ "$META_STATUS" != "dry_run" ]]; then
        fail "cgl-claw spawn --dry-run (scout): meta.json status==dry_run (got '$META_STATUS')"
        BUNDLE_OK=0
      fi

      # Validate trace.jsonl first line event
      FIRST_EVENT="$(python3 -c "import json,sys; d=json.loads(open('$DRY_BUNDLE_DIR/trace.jsonl').readline()); print(d.get('event',''))")"
      if [[ "$FIRST_EVENT" != "dry_run" ]]; then
        fail "cgl-claw spawn --dry-run (scout): trace.jsonl first event==dry_run (got '$FIRST_EVENT')"
        BUNDLE_OK=0
      fi
    fi

    if [[ "$BUNDLE_OK" -eq 1 ]]; then
      pass "cgl-claw spawn --dry-run (scout)"
    fi
  fi
fi

# ── Test 6: cgl-claw spawn with disallowed role (builder) ────────────────────

BUILDER_EXIT=0
cgl-claw spawn \
  --orientation orient-hello-lab-studio-exploration \
  --role builder \
  --dry-run \
  > /tmp/assert_stdout 2>/tmp/assert_stderr || BUILDER_EXIT=$?

if [[ "$BUILDER_EXIT" -eq 0 ]]; then
  fail "cgl-claw spawn --dry-run (builder): expected exit 1, got 0"
elif ! grep -qi "builder" /tmp/assert_stderr && ! grep -qi "role" /tmp/assert_stderr; then
  echo "  stderr: $(cat /tmp/assert_stderr)" >&2
  fail "cgl-claw spawn --dry-run (builder): stderr mentions role mismatch"
else
  pass "cgl-claw spawn --dry-run (builder not in orientation)"
fi

# ── Cleanup ───────────────────────────────────────────────────────────────────

if [[ -n "$DRY_BUNDLE_DIR" && -d "$DRY_BUNDLE_DIR" ]]; then
  rm -rf "$DRY_BUNDLE_DIR"
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
if [[ "$FAIL_COUNT" -eq 0 ]]; then
  echo "ALL TESTS PASSED ($PASS_COUNT passed)"
  exit 0
else
  echo "FAILURES: $FAIL_COUNT failed, $PASS_COUNT passed" >&2
  exit 1
fi
