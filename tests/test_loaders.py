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


def test_discover_labs_walks_subdirs(tmp_path):
    """discover_labs on a federation root with 2 lab subdirs returns 2 LabSummary objects."""
    for lab_name in ("alpha-lab", "beta-lab"):
        studio_dir = tmp_path / lab_name / ".studio"
        studio_dir.mkdir(parents=True)
        (studio_dir / "lab.toml").write_text(
            f'id = "{lab_name}"\ntitle = "{lab_name.capitalize()}"\nkind = "investigation"\nversion = 1\n\n'
            '[director]\nmode = "single-human"\n\n'
            '[paths]\nsurfaces = "surfaces"\nsystems = "systems"\n'
            'investigations = "research/investigations"\nspine_skills = ".claude/skills"\n'
            'runbooks = "runbooks"\ndecisions = "decisions"\nintel = "intel"\nclaws = ".claws"\n',
            encoding="utf-8",
        )
    result = discover_labs(tmp_path)
    assert len(result) == 2, f"Expected 2 labs, got {len(result)}"
    assert all(isinstance(r, LabSummary) for r in result)
    ids = {r.lab_id for r in result}
    assert ids == {"alpha-lab", "beta-lab"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LAB_TOML_TEMPLATE = (
    'id = "{lab_id}"\ntitle = "{lab_id}"\nkind = "investigation"\nversion = 1\n\n'
    '[director]\nmode = "single-human"\n\n'
    '[paths]\nsurfaces = "surfaces"\nsystems = "systems"\n'
    'investigations = "research/investigations"\nspine_skills = ".claude/skills"\n'
    'runbooks = "runbooks"\ndecisions = "decisions"\nintel = "intel"\nclaws = ".claws"\n'
)

_META_TEMPLATE = (
    '{{"id": "{bundle_id}", "orientation_id": "orient-test", "lab_slug": "test-lab", '
    '"role": "scout", "runtime": "claude_print", "capability_profile": "research_readonly", '
    '"source_scope": [], "status": "finished", "started_at": "2026-05-01T15:00:00Z", '
    '"ended_at": "2026-05-01T15:01:00Z", "promotion_recommendation": "{rec}"}}'
)


def _make_lab(root: Path, lab_id: str = "test-lab") -> Path:
    """Create a valid lab directory by copying hello-lab's .studio/ and overriding lab.toml."""
    import shutil

    lab = root / lab_id
    # Copy full .studio/ from hello-lab so all required TOML files are present
    shutil.copytree(HELLO_LAB / ".studio", lab / ".studio")
    # Override lab.toml with the requested lab_id
    (lab / ".studio" / "lab.toml").write_text(
        _LAB_TOML_TEMPLATE.format(lab_id=lab_id), encoding="utf-8"
    )
    return lab


def _make_bundle(lab: Path, bundle_id: str, rec: str = "keep_evidence") -> Path:
    """Create a minimal claw bundle directory."""
    bundle = lab / ".claws" / bundle_id
    bundle.mkdir(parents=True)
    (bundle / "meta.json").write_text(
        _META_TEMPLATE.format(bundle_id=bundle_id, rec=rec), encoding="utf-8"
    )
    return bundle


# ---------------------------------------------------------------------------
# New tests: decision.json support
# ---------------------------------------------------------------------------

def test_claw_bundle_with_decision_json(tmp_path):
    """ClawBundle.decision is set when decision.json exists."""
    import json

    lab = _make_lab(tmp_path)
    bundle_path = _make_bundle(lab, "20260501-000000-scout-test", rec="keep_evidence")
    decision_data = {
        "outcome": "promote",
        "decided_at": "2026-05-01T16:00:00Z",
        "decided_by": "director",
    }
    (bundle_path / "decision.json").write_text(
        json.dumps(decision_data), encoding="utf-8"
    )

    bundles = load_claw_bundles(lab)
    assert len(bundles) == 1
    b = bundles[0]
    assert b.decision == decision_data
    assert b.is_decided is True
    assert b.effective_outcome == "promote"


def test_claw_bundle_without_decision_json(tmp_path):
    """ClawBundle.decision is None when no decision.json present."""
    lab = _make_lab(tmp_path)
    _make_bundle(lab, "20260501-000000-scout-test", rec="keep_evidence")

    bundles = load_claw_bundles(lab)
    assert len(bundles) == 1
    b = bundles[0]
    assert b.decision is None
    assert b.is_decided is False
    assert b.effective_outcome == "keep_evidence"


def test_load_claw_bundles_skips_archive(tmp_path):
    """Bundles under .claws/.archive/ are not loaded."""
    lab = _make_lab(tmp_path)
    _make_bundle(lab, "20260501-000000-scout-keep", rec="keep_evidence")
    # Put a bundle inside .archive/
    archived = lab / ".claws" / ".archive" / "20260501-000000-scout-archived"
    archived.mkdir(parents=True)
    import json as _json
    (archived / "meta.json").write_text(
        _META_TEMPLATE.format(bundle_id="20260501-000000-scout-archived", rec="promote"),
        encoding="utf-8",
    )

    bundles = load_claw_bundles(lab)
    assert len(bundles) == 1, f"Expected 1 bundle, got {len(bundles)}: {[b.bundle_id for b in bundles]}"
    assert bundles[0].bundle_id == "20260501-000000-scout-keep"


def test_discover_labs_skips_archive(tmp_path):
    """discover_labs does not treat .archive/<id> dirs as labs."""
    # Two real labs
    for name in ("alpha-lab", "beta-lab"):
        _make_lab(tmp_path, name)
    # An .archive dir that contains a valid lab structure (should be skipped)
    archive_lab = tmp_path / ".archive" / "old-lab"
    studio = archive_lab / ".studio"
    studio.mkdir(parents=True)
    (studio / "lab.toml").write_text(
        _LAB_TOML_TEMPLATE.format(lab_id="old-lab"), encoding="utf-8"
    )

    result = discover_labs(tmp_path)
    assert len(result) == 2, f"Expected 2 labs, got {len(result)}: {[r.lab_id for r in result]}"
    ids = {r.lab_id for r in result}
    assert ids == {"alpha-lab", "beta-lab"}


def test_lab_summary_decided_vs_awaiting_counts(tmp_path):
    """decided_count and awaiting_count computed correctly; status=needs_review when awaiting > 0."""
    import json as _json

    lab = _make_lab(tmp_path)
    # Bundle 1: decided (has decision.json)
    b1 = _make_bundle(lab, "20260501-000000-scout-decided", rec="keep_evidence")
    (_b1_decision := b1 / "decision.json").write_text(
        _json.dumps({"outcome": "promote", "decided_at": "2026-05-01T16:00:00Z", "decided_by": "director"}),
        encoding="utf-8",
    )
    # Bundle 2: awaiting (rec=keep_evidence, no decision)
    _make_bundle(lab, "20260501-000001-scout-awaiting", rec="keep_evidence")
    # Bundle 3: resolved without decision (rec=abandon)
    _make_bundle(lab, "20260501-000002-scout-abandon", rec="abandon")

    summary = load_lab_summary(lab)
    assert summary.decided_count == 1, f"decided_count={summary.decided_count}"
    assert summary.awaiting_count == 1, f"awaiting_count={summary.awaiting_count}"
    assert summary.status == "needs_review", f"status={summary.status}"


def test_lab_status_idle_when_all_decided(tmp_path):
    """Status is idle (not needs_review) when all bundles have a decision."""
    import json as _json

    lab = _make_lab(tmp_path)
    for i, rec in enumerate(("keep_evidence", "promote")):
        b = _make_bundle(lab, f"2026050{i}-000000-scout-bundle{i}", rec=rec)
        (b / "decision.json").write_text(
            _json.dumps({"outcome": rec, "decided_at": "2026-05-01T16:00:00Z", "decided_by": "director"}),
            encoding="utf-8",
        )

    summary = load_lab_summary(lab)
    assert summary.decided_count == 2
    assert summary.awaiting_count == 0
    assert summary.status == "idle", f"Expected idle, got '{summary.status}': {summary.status_reason}"
