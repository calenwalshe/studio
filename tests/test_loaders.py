"""tests/test_loaders.py — pytest tests for studio/lab_tui/loaders.py

pytest is installed in studio/.venv. Run with:
    studio/.venv/bin/pytest tests/test_loaders.py -v

If pytest is missing:
    studio/.venv/bin/pip install pytest
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the studio package is importable
HARNESS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS_ROOT / "studio"))

import pytest

from lab_tui.loaders import (
    ClawBundle,
    LabSummary,
    discover_labs,
    load_claw_bundles,
    load_lab_summary,
)

HELLO_LAB = HARNESS_ROOT / "examples" / "hello-lab"


# ---------------------------------------------------------------------------
# discover_labs
# ---------------------------------------------------------------------------

def test_discover_labs_finds_one_lab():
    """discover_labs(examples/hello-lab) should return exactly 1 lab."""
    labs = discover_labs(HELLO_LAB)
    assert len(labs) == 1, f"Expected 1 lab, got {len(labs)}: {labs}"


def test_discover_labs_returns_lab_summaries():
    """All returned items should be LabSummary instances."""
    labs = discover_labs(HELLO_LAB)
    for lab in labs:
        assert isinstance(lab, LabSummary)


# ---------------------------------------------------------------------------
# hello-lab status
# ---------------------------------------------------------------------------

def test_hello_lab_status_is_needs_review():
    """hello-lab has one bundle with promotion_recommendation='keep_evidence',
    which is not 'abandon' or 'dry_run', so status should be 'needs_review'."""
    labs = discover_labs(HELLO_LAB)
    assert len(labs) == 1
    lab = labs[0]
    assert lab.status == "needs_review", (
        f"Expected 'needs_review', got '{lab.status}': {lab.status_reason}"
    )


def test_hello_lab_promotion_candidates_count():
    """hello-lab should have 1 promotion candidate (keep_evidence)."""
    labs = discover_labs(HELLO_LAB)
    lab = labs[0]
    assert lab.promotion_candidates == 1


def test_hello_lab_lab_id():
    """Lab ID should be 'hello-lab' as declared in .studio/lab.toml."""
    labs = discover_labs(HELLO_LAB)
    lab = labs[0]
    assert lab.lab_id == "hello-lab"


def test_hello_lab_has_orientations():
    """hello-lab should have at least one orientation loaded."""
    labs = discover_labs(HELLO_LAB)
    lab = labs[0]
    assert len(lab.orientations) >= 1


# ---------------------------------------------------------------------------
# load_claw_bundles
# ---------------------------------------------------------------------------

def test_load_claw_bundles_finds_fixture_bundle():
    """load_claw_bundles should find the one fixture bundle."""
    bundles = load_claw_bundles(HELLO_LAB)
    assert len(bundles) == 1, f"Expected 1 bundle, got {len(bundles)}"


def test_claw_bundle_has_correct_id():
    """Fixture bundle ID should match the directory name."""
    bundles = load_claw_bundles(HELLO_LAB)
    assert bundles[0].bundle_id == "20260501-150000-scout-hello-lab"


def test_claw_bundle_claim_count():
    """Fixture bundle has 3 claims in evidence.jsonl."""
    bundles = load_claw_bundles(HELLO_LAB)
    assert bundles[0].claim_count == 3


def test_claw_bundle_trace_count():
    """Fixture bundle has 9 trace events in trace.jsonl."""
    bundles = load_claw_bundles(HELLO_LAB)
    assert bundles[0].trace_count == 9


def test_claw_bundle_result_text_not_empty():
    """Fixture bundle result.md should not be empty."""
    bundles = load_claw_bundles(HELLO_LAB)
    assert bundles[0].result_text.strip() != ""


def test_claw_bundle_promotion_recommendation():
    """Fixture bundle should have promotion_recommendation='keep_evidence'."""
    bundles = load_claw_bundles(HELLO_LAB)
    assert bundles[0].meta.get("promotion_recommendation") == "keep_evidence"


def test_load_claw_bundles_missing_claws_dir(tmp_path):
    """load_claw_bundles on a dir without .claws/ should return empty list."""
    result = load_claw_bundles(tmp_path)
    assert result == []


# ---------------------------------------------------------------------------
# load_lab_summary — error case
# ---------------------------------------------------------------------------

def test_load_lab_summary_missing_studio_returns_error(tmp_path):
    """load_lab_summary on a dir without .studio/lab.toml should return
    status='error' without crashing."""
    summary = load_lab_summary(tmp_path)
    assert isinstance(summary, LabSummary)
    assert summary.status == "error", (
        f"Expected status='error', got '{summary.status}'"
    )
    assert summary.status_reason  # non-empty reason


def test_load_lab_summary_no_crash_on_empty_dir(tmp_path):
    """load_lab_summary must never raise — always returns a LabSummary."""
    result = load_lab_summary(tmp_path)
    assert isinstance(result, LabSummary)


# ---------------------------------------------------------------------------
# discover_labs — empty / missing root
# ---------------------------------------------------------------------------

def test_discover_labs_nonexistent_root(tmp_path):
    """discover_labs on a nonexistent path returns empty list."""
    result = discover_labs(tmp_path / "does_not_exist")
    assert result == []


def test_discover_labs_no_labs_in_dir(tmp_path):
    """discover_labs on a dir with no labs returns empty list."""
    (tmp_path / "not-a-lab").mkdir()
    result = discover_labs(tmp_path)
    assert result == []
