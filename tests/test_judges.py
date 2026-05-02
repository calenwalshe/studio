"""tests/test_judges.py — fast smoke tests for judges.py and workflow YAMLs.

No LLM calls. The actual judge LLM paths are exercised by Build C when the
Examiner runs end-to-end.

Run with:
    studio/.venv/bin/pytest tests/test_judges.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Path setup — mirror how other test files pull in studio modules
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[1]
STUDIO_ROOT = REPO_ROOT / "studio"
TOOLS_ROOT = REPO_ROOT / "tools"

if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

WORKFLOWS_DIR = TOOLS_ROOT / "evals" / "workflows"
WORKFLOW_FILES = sorted(WORKFLOWS_DIR.glob("*.yaml"))

# ---------------------------------------------------------------------------
# Required fields contract
# ---------------------------------------------------------------------------

REQUIRED_TOP_LEVEL = {"id", "name", "intent", "canonical_steps", "expected_artifact"}


# ---------------------------------------------------------------------------
# test_load_workflow_yaml
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("yaml_path", WORKFLOW_FILES, ids=lambda p: p.stem)
def test_load_workflow_yaml(yaml_path: Path) -> None:
    """Each workflow YAML must parse cleanly."""
    data = yaml.safe_load(yaml_path.read_text())
    assert isinstance(data, dict), f"{yaml_path.name} did not parse to a dict"


# ---------------------------------------------------------------------------
# test_workflow_yaml_required_fields
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("yaml_path", WORKFLOW_FILES, ids=lambda p: p.stem)
def test_workflow_yaml_required_fields(yaml_path: Path) -> None:
    """Each workflow must have id, name, intent, canonical_steps, expected_artifact."""
    data = yaml.safe_load(yaml_path.read_text())
    missing = REQUIRED_TOP_LEVEL - set(data.keys())
    assert not missing, f"{yaml_path.name} missing fields: {missing}"

    # canonical_steps must be a non-empty list
    steps = data["canonical_steps"]
    assert isinstance(steps, list) and len(steps) >= 1, (
        f"{yaml_path.name}: canonical_steps must be a non-empty list"
    )

    # expected_artifact must be a non-empty list
    artifacts = data["expected_artifact"]
    assert isinstance(artifacts, list) and len(artifacts) >= 1, (
        f"{yaml_path.name}: expected_artifact must be a non-empty list"
    )

    # id must match filename prefix (e.g. 01-triage-and-promote.yaml -> id: triage-and-promote)
    stem = yaml_path.stem  # e.g. "01-triage-and-promote"
    expected_id = stem.split("-", 1)[1] if "-" in stem else stem
    assert data["id"] == expected_id, (
        f"{yaml_path.name}: id={data['id']!r} does not match filename-derived id={expected_id!r}"
    )


# ---------------------------------------------------------------------------
# test_six_workflows_exist
# ---------------------------------------------------------------------------

def test_six_workflows_exist() -> None:
    """Exactly 6 workflow YAMLs must be present."""
    assert len(WORKFLOW_FILES) == 6, (
        f"Expected 6 workflow YAMLs, found {len(WORKFLOW_FILES)}: {[f.name for f in WORKFLOW_FILES]}"
    )


# ---------------------------------------------------------------------------
# test_resolve_artifact_pattern_substitutes_lab
# ---------------------------------------------------------------------------

def test_resolve_artifact_pattern_substitutes_lab(tmp_path: Path) -> None:
    """Pattern expansion: <lab>/.claws/<claw_id>/decision.json finds real paths."""
    from evals.judges import _resolve_artifact_pattern

    # Build a minimal fake federation
    lab_a = tmp_path / "lab-alpha"
    lab_b = tmp_path / "lab-beta"
    claw_dir_a = lab_a / ".claws" / "20260501-scout-alpha"
    claw_dir_b = lab_b / ".claws" / "20260501-scout-beta"
    claw_dir_a.mkdir(parents=True)
    claw_dir_b.mkdir(parents=True)

    # Place one decision file in lab-alpha only
    (claw_dir_a / "decision.json").write_text('{"outcome": "merge"}')

    pattern = "<lab>/.claws/<claw_id>/decision.json"
    candidates = _resolve_artifact_pattern(pattern, tmp_path)

    # Should have expanded to at least 2 candidates (one per claw)
    assert len(candidates) >= 2, f"Expected >= 2 candidates, got {candidates}"

    # Exactly one should exist
    existing = [p for p in candidates if p.exists()]
    assert len(existing) == 1, f"Expected 1 existing path, got {existing}"
    assert existing[0].name == "decision.json"


def test_resolve_artifact_pattern_no_token(tmp_path: Path) -> None:
    """A pattern with no substitution tokens resolves to a single literal path."""
    from evals.judges import _resolve_artifact_pattern

    pattern = "agent-infra/.claws/.archive/20260430-080000-scout-agent-infra"
    candidates = _resolve_artifact_pattern(pattern, tmp_path)
    assert len(candidates) == 1
    assert candidates[0] == tmp_path / pattern


def test_resolve_artifact_pattern_federation_token(tmp_path: Path) -> None:
    """<federation>/<slug>/.studio/lab.toml resolves correctly."""
    from evals.judges import _resolve_artifact_pattern

    pattern = "<federation>/new-lab/.studio/lab.toml"
    candidates = _resolve_artifact_pattern(pattern, tmp_path)
    assert len(candidates) == 1
    assert candidates[0] == tmp_path / "new-lab/.studio/lab.toml"
