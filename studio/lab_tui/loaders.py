"""loaders.py — typed data-layer for the Studio Cockpit TUI.

Covers:
  - ClawBundle      one artifact bundle under <lab>/.claws/<id>/
  - LabSummary      aggregated view of a single lab
  - discover_labs   find all labs under a federation root
  - load_lab_summary  build LabSummary for one lab root path

Reuses bin/_studio_orient.py for all .studio/*.toml loading.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: add bin/ to sys.path so _studio_orient is importable
# ---------------------------------------------------------------------------
HARNESS_BIN = Path(__file__).resolve().parents[2] / "bin"
sys.path.insert(0, str(HARNESS_BIN))

from _studio_orient import (  # noqa: E402
    StudioConfigError,
    load_studio_config,
    list_orientations,
    Orientation,
)


# ---------------------------------------------------------------------------
# ClawBundle
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClawBundle:
    bundle_id: str
    meta: dict                # parsed meta.json
    result_text: str          # contents of result.md, "" if missing
    claim_count: int          # count of lines in evidence.jsonl, 0 if missing
    trace_count: int          # count of lines in trace.jsonl, 0 if missing


def _count_jsonl_lines(path: Path) -> int:
    """Count non-empty lines in a .jsonl file. Returns 0 if file missing."""
    if not path.exists():
        return 0
    count = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                count += 1
    return count


def load_claw_bundles(lab_root: Path) -> list[ClawBundle]:
    """Load all .claws/<id>/ bundles in a lab. Returns empty list if .claws/ missing."""
    claws_dir = lab_root / ".claws"
    if not claws_dir.exists():
        return []

    bundles: list[ClawBundle] = []
    for bundle_path in sorted(claws_dir.iterdir()):
        if not bundle_path.is_dir():
            continue
        meta_file = bundle_path / "meta.json"
        if not meta_file.exists():
            continue
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        result_file = bundle_path / "result.md"
        result_text = result_file.read_text(encoding="utf-8") if result_file.exists() else ""

        claim_count = _count_jsonl_lines(bundle_path / "evidence.jsonl")
        trace_count = _count_jsonl_lines(bundle_path / "trace.jsonl")

        bundles.append(
            ClawBundle(
                bundle_id=bundle_path.name,
                meta=meta,
                result_text=result_text,
                claim_count=claim_count,
                trace_count=trace_count,
            )
        )
    return bundles


# ---------------------------------------------------------------------------
# Status derivation
# ---------------------------------------------------------------------------

# Promotion recommendations that require director review (not abandon/dry_run)
_REVIEW_RECS = frozenset({"keep_evidence", "promote", "partial_promote"})
# "abandon" and "dry_run" don't require director review
_NO_REVIEW_RECS = frozenset({"abandon", "dry_run"})


def _derive_status(
    bundles: list[ClawBundle],
    orientations: list[Orientation],
    cfg_error: str | None,
) -> tuple[str, str]:
    """Return (status, status_reason) given loaded data.

    Priority order (highest wins):
      error        — .studio/lab.toml missing or malformed
      needs_review — at least one bundle with promotion_recommendation
                     not in {abandon, dry_run}
      active       — bundles with status == "running" exist
                     (reserved; won't fire in v0 — no running claws)
      idle         — has bundles, none need review, none running
      stale        — has orientations but no bundles
      blocked      — reserved (won't fire in v0; documented here)
    """
    if cfg_error:
        return ("error", cfg_error)

    # needs_review: any bundle whose recommendation is not abandon/dry_run
    review_bundles = [
        b for b in bundles
        if b.meta.get("promotion_recommendation", "abandon") not in _NO_REVIEW_RECS
    ]
    if review_bundles:
        sample = review_bundles[0].meta.get("promotion_recommendation", "?")
        return (
            "needs_review",
            f"{len(review_bundles)} bundle(s) require director review "
            f"(e.g. '{sample}')",
        )

    # active — running bundles (v0: won't fire)
    running = [b for b in bundles if b.meta.get("status") == "running"]
    if running:
        return ("active", f"{len(running)} claw(s) currently running")

    # idle — has completed bundles but nothing needing review
    if bundles:
        return ("idle", f"{len(bundles)} bundle(s), none require review")

    # stale — orientations defined but no bundles
    if orientations:
        return ("stale", f"{len(orientations)} orientation(s) defined but no claws run yet")

    # blocked — reserved; conditions not defined in v0
    # (would fire when an orientation has a hard blocker flag)
    return ("idle", "no bundles and no orientations")


# ---------------------------------------------------------------------------
# LabSummary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LabSummary:
    lab_root: Path
    lab_id: str                      # from .studio/lab.toml id
    title: str                       # from .studio/lab.toml title
    kind: str                        # from .studio/lab.toml kind
    orientations: list[Orientation]  # from _studio_orient
    bundles: list[ClawBundle]
    promotion_candidates: int        # bundles where recommendation requires review
    status: str                      # active | idle | blocked | stale | needs_review | error
    status_reason: str               # one-line explanation


def load_lab_summary(lab_root: Path) -> LabSummary:
    """Build a complete summary for one lab. Tolerant of missing .studio/ —
    returns LabSummary with status='error' and status_reason explaining."""
    lab_toml = lab_root / ".studio" / "lab.toml"

    cfg_error: str | None = None
    lab_id = lab_root.name
    title = lab_root.name
    kind = "unknown"
    orientations: list[Orientation] = []

    try:
        cfg = load_studio_config(lab_root)
        lab_id = cfg.lab.get("id", lab_root.name)
        title = cfg.lab.get("title", lab_root.name)
        kind = cfg.lab.get("kind", "unknown")
        orientations = list_orientations(cfg)
    except StudioConfigError as exc:
        cfg_error = str(exc)
    except Exception as exc:
        cfg_error = f"unexpected error loading .studio/: {exc}"

    bundles = load_claw_bundles(lab_root)

    promotion_candidates = sum(
        1 for b in bundles
        if b.meta.get("promotion_recommendation", "abandon") not in _NO_REVIEW_RECS
    )

    status, status_reason = _derive_status(bundles, orientations, cfg_error)

    return LabSummary(
        lab_root=lab_root,
        lab_id=lab_id,
        title=title,
        kind=kind,
        orientations=orientations,
        bundles=bundles,
        promotion_candidates=promotion_candidates,
        status=status,
        status_reason=status_reason,
    )


# ---------------------------------------------------------------------------
# discover_labs
# ---------------------------------------------------------------------------

def discover_labs(federation_root: Path) -> list[LabSummary]:
    """Find all labs under a federation root.

    A 'lab' is any directory containing a .studio/lab.toml.

    v0 behaviour: treat the directory passed in ITSELF as a single lab if it
    has .studio/lab.toml. If not, walk one level of subdirectories looking for
    .studio/lab.toml. This keeps things simple while supporting both hello-lab
    (single lab at root) and future multi-lab federations.

    Returns empty list if no labs found.
    """
    if not federation_root.exists():
        return []

    # Check if the root itself is a lab
    if (federation_root / ".studio" / "lab.toml").exists():
        return [load_lab_summary(federation_root)]

    # Walk subdirectories (one level)
    summaries: list[LabSummary] = []
    try:
        for child in sorted(federation_root.iterdir()):
            if child.is_dir() and (child / ".studio" / "lab.toml").exists():
                summaries.append(load_lab_summary(child))
    except PermissionError:
        pass

    return summaries
