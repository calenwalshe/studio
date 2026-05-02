"""tests/test_examiner.py — unit tests for the Examiner persona.

Run with:
    studio/.venv/bin/pytest tests/test_examiner.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure tools/ is importable
HARNESS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS_ROOT))
sys.path.insert(0, str(HARNESS_ROOT / "studio"))

from tools.evals.examiner.examiner import (
    EXAMINER_IDENTITY,
    ExaminerState,
    _default_state,
    _finding_counter,
    _init_finding_counter,
    _state_from_dict,
    _state_to_dict,
    load_state,
    load_workflows,
    next_finding_id,
    pick_next_workflow,
)


# ---------------------------------------------------------------------------
# test_load_state_initializes_when_missing
# ---------------------------------------------------------------------------


def test_load_state_initializes_when_missing(tmp_path, monkeypatch):
    """Given empty STATE_DIR, load_state returns sensible defaults."""
    import tools.evals.examiner.examiner as examiner_mod

    # Patch the STATE_FILE to a non-existent path inside tmp_path
    monkeypatch.setattr(examiner_mod, "STATE_FILE", tmp_path / "state.json")
    # Also patch WORKFLOWS_DIR to a non-existent dir so no workflows are loaded
    monkeypatch.setattr(examiner_mod, "WORKFLOWS_DIR", tmp_path / "workflows")

    state = load_state()

    assert isinstance(state, ExaminerState)
    assert state.session_count == 0
    assert state.workflows_covered == []
    assert isinstance(state.workflows_remaining, list)
    assert isinstance(state.features_exercised, dict)
    assert isinstance(state.open_issues, list)
    assert state.started_at  # non-empty ISO string


# ---------------------------------------------------------------------------
# test_pick_next_workflow_prefers_uncovered
# ---------------------------------------------------------------------------


def test_pick_next_workflow_prefers_uncovered():
    """Given 1 covered + 2 uncovered, picks uncovered (first remaining)."""
    workflows = [
        {"id": "wf-alpha", "name": "Alpha"},
        {"id": "wf-beta", "name": "Beta"},
        {"id": "wf-gamma", "name": "Gamma"},
    ]
    state = ExaminerState(
        started_at="2026-01-01T00:00:00Z",
        session_count=1,
        workflows_covered=["wf-alpha"],
        workflows_remaining=["wf-beta", "wf-gamma"],
        features_exercised={},
        open_issues=[],
        next_session_priority=None,
    )

    chosen = pick_next_workflow(state, workflows)
    assert chosen["id"] == "wf-beta"


def test_pick_next_workflow_falls_back_to_covered():
    """When nothing remains, round-robins through covered."""
    workflows = [
        {"id": "wf-alpha", "name": "Alpha"},
        {"id": "wf-beta", "name": "Beta"},
    ]
    state = ExaminerState(
        started_at="2026-01-01T00:00:00Z",
        session_count=2,
        workflows_covered=["wf-alpha", "wf-beta"],
        workflows_remaining=[],
        features_exercised={},
        open_issues=[],
        next_session_priority=None,
    )

    chosen = pick_next_workflow(state, workflows)
    assert chosen["id"] == "wf-alpha"


def test_pick_next_workflow_honors_priority():
    """next_session_priority overrides remaining order."""
    workflows = [
        {"id": "wf-alpha", "name": "Alpha"},
        {"id": "wf-beta", "name": "Beta"},
        {"id": "wf-gamma", "name": "Gamma"},
    ]
    state = ExaminerState(
        started_at="2026-01-01T00:00:00Z",
        session_count=1,
        workflows_covered=[],
        workflows_remaining=["wf-alpha", "wf-beta", "wf-gamma"],
        features_exercised={},
        open_issues=[],
        next_session_priority="wf-gamma",
    )

    chosen = pick_next_workflow(state, workflows)
    assert chosen["id"] == "wf-gamma"


# ---------------------------------------------------------------------------
# test_findings_get_sequential_ids
# ---------------------------------------------------------------------------


def test_findings_get_sequential_ids(tmp_path, monkeypatch):
    """Append two findings; ids are F-001 and F-002."""
    import tools.evals.examiner.examiner as examiner_mod

    # Patch FINDINGS_FILE to a fresh temp file
    monkeypatch.setattr(examiner_mod, "FINDINGS_FILE", tmp_path / "findings.jsonl")

    # Re-run init to reset counter from (empty) findings file
    _init_finding_counter()

    id1 = next_finding_id()
    id2 = next_finding_id()

    assert id1 == "F-001"
    assert id2 == "F-002"


def test_findings_ids_continue_from_existing(tmp_path, monkeypatch):
    """Finding IDs pick up from the highest existing ID in findings.jsonl."""
    import tools.evals.examiner.examiner as examiner_mod

    findings_file = tmp_path / "findings.jsonl"
    existing = [
        {"id": "F-001", "summary": "first"},
        {"id": "F-002", "summary": "second"},
        {"id": "F-005", "summary": "fifth"},
    ]
    findings_file.write_text(
        "\n".join(json.dumps(f) for f in existing) + "\n", encoding="utf-8"
    )

    monkeypatch.setattr(examiner_mod, "FINDINGS_FILE", findings_file)
    _init_finding_counter()

    next_id = next_finding_id()
    assert next_id == "F-006"


# ---------------------------------------------------------------------------
# Smoke tests — state round-trip
# ---------------------------------------------------------------------------


def test_state_roundtrip():
    """State survives serialization/deserialization."""
    original = ExaminerState(
        started_at="2026-05-01T00:00:00Z",
        session_count=7,
        workflows_covered=["wf-a", "wf-b"],
        workflows_remaining=["wf-c"],
        features_exercised={"chief_chat": 3, "lab_expansion": 1},
        open_issues=["F-001"],
        next_session_priority="wf-c",
    )
    d = _state_to_dict(original)
    restored = _state_from_dict(d)

    assert restored.session_count == 7
    assert restored.workflows_covered == ["wf-a", "wf-b"]
    assert restored.workflows_remaining == ["wf-c"]
    assert restored.features_exercised["chief_chat"] == 3
    assert restored.open_issues == ["F-001"]
    assert restored.next_session_priority == "wf-c"


def test_examiner_identity_is_non_empty():
    """EXAMINER_IDENTITY is a non-trivial string."""
    assert len(EXAMINER_IDENTITY) > 200
    assert "Examiner" in EXAMINER_IDENTITY
    assert "evaluator" in EXAMINER_IDENTITY.lower() or "tester" in EXAMINER_IDENTITY.lower()
