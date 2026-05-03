"""tests/test_actions.py — pure unit tests for studio/lab_tui/actions.py

Run with:
    studio/.venv/bin/pytest tests/test_actions.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure the studio package is importable
HARNESS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARNESS_ROOT / "studio"))

from lab_tui.actions import (
    VALID_PROMOTION_OUTCOMES,
    DirectorActionResult,
    apply_decision,
    archive_claw,
    archive_lab,
    create_lab,
    spawn_dry_run_claw,
)

HELLO_LAB = HARNESS_ROOT / "examples" / "hello-lab"
FEDERATION_DEMO = HARNESS_ROOT / "examples" / "federation-demo"


# ---------------------------------------------------------------------------
# apply_decision
# ---------------------------------------------------------------------------

def test_apply_decision_writes_file(tmp_path):
    """apply_decision writes a decision.json with the correct outcome."""
    claw_dir = tmp_path / ".claws" / "20260501-test-scout"
    claw_dir.mkdir(parents=True)

    result = apply_decision(claw_dir, "keep_evidence")

    assert result.success is True
    decision_file = claw_dir / "decision.json"
    assert decision_file.exists()
    data = json.loads(decision_file.read_text())
    assert data["outcome"] == "keep_evidence"
    assert "decided_at" in data
    assert data["decided_by"] == "director"
    assert result.artifact_path == decision_file


def test_apply_decision_all_valid_outcomes(tmp_path):
    """apply_decision accepts every VALID_PROMOTION_OUTCOMES value."""
    for outcome in VALID_PROMOTION_OUTCOMES:
        claw_dir = tmp_path / f"claw-{outcome}"
        claw_dir.mkdir()
        res = apply_decision(claw_dir, outcome)
        assert res.success is True, f"Expected success for outcome={outcome}: {res.message}"


def test_apply_decision_invalid_outcome(tmp_path):
    """apply_decision returns success=False for an unknown outcome."""
    claw_dir = tmp_path / "claw-bad"
    claw_dir.mkdir()
    result = apply_decision(claw_dir, "not_a_real_outcome")
    assert result.success is False
    assert "invalid outcome" in result.message


def test_apply_decision_nonexistent_dir(tmp_path):
    """apply_decision returns success=False if the claw directory doesn't exist."""
    claw_dir = tmp_path / "does-not-exist"
    result = apply_decision(claw_dir, "keep_evidence")
    assert result.success is False
    assert "not found" in result.message


def test_apply_decision_idempotent(tmp_path):
    """apply_decision can overwrite an existing decision.json."""
    claw_dir = tmp_path / "claw-overwrite"
    claw_dir.mkdir()
    apply_decision(claw_dir, "keep_evidence")
    result = apply_decision(claw_dir, "abandon")
    assert result.success is True
    data = json.loads((claw_dir / "decision.json").read_text())
    assert data["outcome"] == "abandon"


# ---------------------------------------------------------------------------
# archive_claw
# ---------------------------------------------------------------------------

def test_archive_claw_moves_to_archive(tmp_path):
    """archive_claw moves the bundle to .claws/.archive/<id>/."""
    lab_root = tmp_path / "my-lab"
    claws_dir = lab_root / ".claws"
    bundle_dir = claws_dir / "20260501-test-bundle"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "meta.json").write_text('{"role": "scout"}')

    result = archive_claw(bundle_dir)

    assert result.success is True
    assert not bundle_dir.exists()
    archive_dir = claws_dir / ".archive" / "20260501-test-bundle"
    assert archive_dir.exists()
    assert result.artifact_path == archive_dir


def test_archive_claw_nonexistent_dir(tmp_path):
    """archive_claw returns success=False if the bundle dir doesn't exist."""
    result = archive_claw(tmp_path / "ghost-bundle")
    assert result.success is False


def test_archive_claw_collision_resolved(tmp_path):
    """archive_claw resolves collisions with a timestamp suffix."""
    lab_root = tmp_path / "my-lab"
    claws_dir = lab_root / ".claws"
    bundle_dir = claws_dir / "20260501-test-bundle"
    bundle_dir.mkdir(parents=True)

    # Pre-create the target in .archive
    archive_root = claws_dir / ".archive"
    archive_root.mkdir(parents=True)
    (archive_root / "20260501-test-bundle").mkdir()

    result = archive_claw(bundle_dir)
    assert result.success is True
    # The new target should have a suffix
    assert result.artifact_path is not None
    assert result.artifact_path.name.startswith("20260501-test-bundle-")


# ---------------------------------------------------------------------------
# create_lab
# ---------------------------------------------------------------------------

def _make_sibling_lab(federation_root: Path, slug: str) -> Path:
    """Helper: create a minimal lab that can serve as a template."""
    studio_dir = federation_root / slug / ".studio"
    studio_dir.mkdir(parents=True)
    (studio_dir / "lab.toml").write_text(
        f'id = "{slug}"\ntitle = "{slug}"\nkind = "investigation"\nversion = 1\n\n'
        '[director]\nmode = "single-human"\n\n'
        '[paths]\nsurfaces = "surfaces"\nsystems = "systems"\n'
        'investigations = "research/investigations"\nspine_skills = ".claude/skills"\n'
        'runbooks = "runbooks"\ndecisions = "decisions"\nintel = "intel"\nclaws = ".claws"\n'
    )
    return federation_root / slug


def test_create_lab_writes_full_shape(tmp_path):
    """create_lab writes lab.toml, orientations.toml, and required subdirs."""
    # Provide a sibling template
    _make_sibling_lab(tmp_path, "template-lab")

    result = create_lab(tmp_path, "new-lab", "investigation", "New Lab", "Explore something new")

    assert result.success is True
    new_lab = tmp_path / "new-lab"
    assert new_lab.is_dir()
    assert (new_lab / ".studio" / "lab.toml").exists()
    assert (new_lab / ".studio" / "orientations.toml").exists()

    lab_toml = (new_lab / ".studio" / "lab.toml").read_text()
    assert 'id = "new-lab"' in lab_toml
    assert 'title = "New Lab"' in lab_toml
    assert 'kind = "investigation"' in lab_toml

    orient_toml = (new_lab / ".studio" / "orientations.toml").read_text()
    assert "Explore something new" in orient_toml

    # Check required subdirectory shape (at least 6)
    subdirs = [p for p in new_lab.rglob("*") if p.is_dir()]
    assert len(subdirs) >= 6, f"Expected at least 6 subdirs, got {len(subdirs)}"


def test_create_lab_from_hello_lab_template(tmp_path):
    """create_lab falls back to examples/hello-lab when no sibling template exists."""
    result = create_lab(tmp_path, "solo-lab", "surface", "Solo Lab", "A standalone lab")
    assert result.success is True, result.message
    assert (tmp_path / "solo-lab" / ".studio" / "lab.toml").exists()


def test_create_lab_rejects_invalid_slug(tmp_path):
    """create_lab rejects slugs with uppercase, spaces, or leading dashes."""
    bad_slugs = ["MyLab", "-bad", "has space", "123leading", ""]
    for slug in bad_slugs:
        result = create_lab(tmp_path, slug, "investigation", "T", "T")
        assert result.success is False, f"Expected failure for slug={slug!r}"
        assert "invalid slug" in result.message or "kebab" in result.message


def test_create_lab_rejects_invalid_kind(tmp_path):
    """create_lab rejects kind values not in {investigation, surface, systems}."""
    result = create_lab(tmp_path, "my-lab", "experimental", "T", "T")
    assert result.success is False
    assert "invalid kind" in result.message


def test_create_lab_rejects_collision(tmp_path):
    """Second create_lab with same slug returns success=False."""
    _make_sibling_lab(tmp_path, "template-lab")
    create_lab(tmp_path, "alpha-lab", "investigation", "Alpha", "First")
    result = create_lab(tmp_path, "alpha-lab", "investigation", "Alpha Again", "Second")
    assert result.success is False
    assert "already exists" in result.message


# ---------------------------------------------------------------------------
# archive_lab
# ---------------------------------------------------------------------------

def test_archive_lab_moves_to_archive(tmp_path):
    """archive_lab moves the lab dir to federation_root/.archive/<slug>-<ts>/."""
    lab_dir = tmp_path / "my-lab"
    lab_dir.mkdir()
    (lab_dir / "README.md").write_text("hi")

    result = archive_lab(tmp_path, "my-lab")

    assert result.success is True
    assert not lab_dir.exists()
    archive_root = tmp_path / ".archive"
    assert archive_root.is_dir()
    archived_dirs = list(archive_root.iterdir())
    assert len(archived_dirs) == 1
    assert archived_dirs[0].name.startswith("my-lab-")


def test_archive_lab_nonexistent_slug(tmp_path):
    """archive_lab returns success=False if the lab doesn't exist."""
    result = archive_lab(tmp_path, "ghost-lab")
    assert result.success is False
    assert "not found" in result.message


# ---------------------------------------------------------------------------
# spawn_dry_run_claw — integration (against real hello-lab)
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_spawn_dry_run_claw_against_hello_lab(tmp_path):
    """Shells out to real cgl-claw against examples/hello-lab (dry-run).

    Marked slow because it invokes a subprocess. Runs in <5s on a normal machine.
    """
    import shutil
    # Work in a copy of hello-lab to avoid polluting the fixture
    lab_copy = tmp_path / "hello-lab"
    shutil.copytree(str(HELLO_LAB), str(lab_copy))

    result = spawn_dry_run_claw(
        lab_root=lab_copy,
        orientation_id="orient-hello-lab-studio-exploration",
        role="scout",
        harness_root=HARNESS_ROOT,
    )

    assert result.success is True, f"spawn failed: {result.message}"
    assert result.artifact_path is not None
    assert result.artifact_path.is_dir()
    # The bundle dir should have a meta.json
    assert (result.artifact_path / "meta.json").exists()
