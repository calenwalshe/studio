"""Director actions — file-backed mutations on lab state.

All functions are pure: take paths + parameters, write files, return a
DirectorActionResult dataclass. Reusable from anywhere (tests, modals,
future REST surface). No Textual imports.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json, shutil, subprocess, os, re
from typing import Optional


@dataclass(frozen=True)
class DirectorActionResult:
    success: bool
    message: str           # human-readable for the modal
    artifact_path: Optional[Path] = None  # the file/dir that was written or moved


VALID_PROMOTION_OUTCOMES = (
    "abandon", "keep_evidence", "continue", "merge", "publish", "graduate_to_spine"
)


def apply_decision(claw_dir: Path, outcome: str, decided_by: str = "director") -> DirectorActionResult:
    """Write a decision.json next to the claw bundle.

    Does NOT mutate the bundle itself. Decision is its own auditable artifact.
    Idempotent — overwrites existing decision.json (allows director to revise).
    """
    if outcome not in VALID_PROMOTION_OUTCOMES:
        return DirectorActionResult(False, f"invalid outcome: {outcome}. valid: {VALID_PROMOTION_OUTCOMES}")
    if not claw_dir.is_dir():
        return DirectorActionResult(False, f"claw bundle not found: {claw_dir}")
    decision = {
        "outcome": outcome,
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "decided_by": decided_by,
    }
    path = claw_dir / "decision.json"
    path.write_text(json.dumps(decision, indent=2))
    return DirectorActionResult(True, f"decision recorded: {outcome}", path)


def archive_claw(claw_dir: Path) -> DirectorActionResult:
    """Soft-delete: move bundle to .archive/<id>/.

    Recoverable — director can mv it back.
    """
    if not claw_dir.is_dir():
        return DirectorActionResult(False, f"claw bundle not found: {claw_dir}")
    lab_root = claw_dir.parent.parent  # claw_dir is <lab>/.claws/<id>/
    archive_root = lab_root / ".claws" / ".archive"
    archive_root.mkdir(parents=True, exist_ok=True)
    target = archive_root / claw_dir.name
    if target.exists():
        # already archived; collision-resolve with timestamp suffix
        target = archive_root / f"{claw_dir.name}-{int(datetime.now().timestamp())}"
    shutil.move(str(claw_dir), str(target))
    return DirectorActionResult(True, f"archived to {target.relative_to(lab_root)}", target)


def spawn_dry_run_claw(lab_root: Path, orientation_id: str, role: str, harness_root: Optional[Path] = None) -> DirectorActionResult:
    """Shell out to bin/cgl-claw spawn --orientation X --role Y --dry-run.

    harness_root defaults to the parent of the lab_tui module (the studio repo root).
    Returns the path to the new bundle directory on success.
    """
    if harness_root is None:
        # cockpit.py lives in studio/lab_tui/cockpit.py; harness root is 2 levels up from this file
        harness_root = Path(__file__).resolve().parents[2]
    cmd = [
        str(harness_root / "bin" / "cgl-claw"),
        "spawn",
        "--orientation", orientation_id,
        "--role", role,
        "--dry-run",
    ]
    env = os.environ.copy()
    env["CGL_LAB_ROOT"] = str(lab_root)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
    except subprocess.TimeoutExpired:
        return DirectorActionResult(False, "spawn timed out after 30s")
    if proc.returncode != 0:
        return DirectorActionResult(False, f"spawn failed: {proc.stderr.strip()[:200]}")
    # The dry-run writes a bundle dir at <lab_root>/.claws/<new-id>/. Find the newest.
    claws_dir = lab_root / ".claws"
    if not claws_dir.exists():
        return DirectorActionResult(True, "spawn ok (no bundle dir found)")
    # newest bundle by mtime, excluding .archive
    bundles = [p for p in claws_dir.iterdir() if p.is_dir() and not p.name.startswith(".")]
    if not bundles:
        return DirectorActionResult(True, "spawn ok (no bundle dir found)")
    newest = max(bundles, key=lambda p: p.stat().st_mtime)
    return DirectorActionResult(True, f"dry-run claw spawned: {newest.name}", newest)


_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*$")


def create_lab(federation_root: Path, slug: str, kind: str, title: str, objective: str) -> DirectorActionResult:
    """Create a new lab directory under federation_root with minimal .studio/ shape.

    slug must be kebab-case. kind in {investigation, surface, systems}.
    Writes lab.toml + orientations.toml + roles/capabilities/runtimes/promotion/sources.toml
    by copying from a template lab (use the first existing sibling lab as the template,
    or fall back to hello-lab in examples/).
    """
    if not _SLUG_RE.match(slug):
        return DirectorActionResult(False, f"invalid slug: {slug!r}. must be kebab-case starting with a letter.")
    if kind not in ("investigation", "surface", "systems"):
        return DirectorActionResult(False, f"invalid kind: {kind!r}. must be investigation/surface/systems.")
    new_lab = federation_root / slug
    if new_lab.exists():
        return DirectorActionResult(False, f"lab already exists: {slug}")

    # find a sibling lab to template from
    siblings = [p for p in federation_root.iterdir() if p.is_dir() and not p.name.startswith(".") and (p / ".studio" / "lab.toml").exists()]
    if not siblings:
        # fall back to examples/hello-lab
        examples_hello = Path(__file__).resolve().parents[2] / "examples" / "hello-lab"
        if not (examples_hello / ".studio" / "lab.toml").exists():
            return DirectorActionResult(False, "no template lab found")
        template = examples_hello
    else:
        template = siblings[0]

    new_lab.mkdir()
    (new_lab / ".studio").mkdir()
    # copy roles/capabilities/runtimes/promotion as-is from template
    for fname in ("roles.toml", "capabilities.toml", "runtimes.toml", "promotion.toml"):
        src = template / ".studio" / fname
        if src.exists():
            shutil.copy(src, new_lab / ".studio" / fname)

    # write a custom lab.toml
    lab_toml = f'''id = "{slug}"
title = "{title}"
kind = "{kind}"
version = 1

[director]
mode = "single-human"

[paths]
surfaces = "surfaces"
systems = "systems"
investigations = "research/investigations"
spine_skills = ".claude/skills"
runbooks = "runbooks"
decisions = "decisions"
intel = "intel"
claws = ".claws"
'''
    (new_lab / ".studio" / "lab.toml").write_text(lab_toml)

    # write a starter orientation
    orient_id = f"orient-{slug}-initial"
    orient_toml = f'''[[orientation]]
id = "{orient_id}"
lab = "{kind}/{slug}"
objective = "{objective}"
status = "draft"
stop_rule = "director_review_after_first_spec"
roles = ["scout"]
sources = []
outputs = ["evidence_bundle"]

[orientation.constraints]
run_untrusted_code = false
install_dependencies = false
require_provenance = true
implementation_allowed = false
'''
    (new_lab / ".studio" / "orientations.toml").write_text(orient_toml)

    # empty sources.toml
    (new_lab / ".studio" / "sources.toml").write_text("")

    # subdirectory shape
    for sub in ("surfaces", "research/investigations", "systems", "runbooks", "decisions", "intel", ".claude/skills"):
        (new_lab / sub).mkdir(parents=True)
        (new_lab / sub / ".gitkeep").touch()

    return DirectorActionResult(True, f"lab created: {slug}", new_lab)


def archive_lab(federation_root: Path, slug: str) -> DirectorActionResult:
    """Soft-delete: move lab dir to federation_root/.archive/<slug>-<ts>/.

    Recoverable.
    """
    lab = federation_root / slug
    if not lab.is_dir():
        return DirectorActionResult(False, f"lab not found: {slug}")
    archive_root = federation_root / ".archive"
    archive_root.mkdir(exist_ok=True)
    ts = int(datetime.now().timestamp())
    target = archive_root / f"{slug}-{ts}"
    shutil.move(str(lab), str(target))
    return DirectorActionResult(True, f"lab archived: {target.relative_to(federation_root)}", target)
