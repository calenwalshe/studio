"""state_reader — the typed data-read model for the studio TUIs.

ONE module that knows where everything lives in the lab and produces
typed views. The TUIs read from this and never touch raw filesystem
paths directly.

Per studio/SPEC.md and the B-shape decision (TUI as workshop):
- The bridge TUI uses studio-wide views (labs(), queue(), ledger(),
  spine(), last_words()).
- The lab TUI uses lab-scoped views (lab(slug), active_claws(slug),
  contracts(slug), artifacts(slug)).

Read-only. Never mutates lab state. The TUIs invoke separate primitives
(cgl-delegate, cgl-publish, etc.) for any mutation.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ──────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────

LAB_ROOT = Path(os.environ.get(
    "CGL_LAB_ROOT",
    "/home/agent/projects/cairn-gate-labs/lab",
))
WRAPPER_ROOT = LAB_ROOT.parent  # cairn-gate-labs/
TREES_ROOT = WRAPPER_ROOT / "trees"

INTEL_DIR = LAB_ROOT / "intel"
SURFACES_DIR = LAB_ROOT / "surfaces"
FUNCTIONS_DIR = LAB_ROOT / "functions"
RESEARCH_DIR = LAB_ROOT / "research"
INVESTIGATIONS_DIR = RESEARCH_DIR / "investigations"
DECISIONS_DIR = LAB_ROOT / "decisions"
RUNBOOKS_DIR = LAB_ROOT / "runbooks"
WEB_DIAGRAMS_DIR = LAB_ROOT / "web" / "cairnlabs.org" / "diagrams"

PUBLISH_LOG = INTEL_DIR / "publish-log.jsonl"
STATE_JSON = INTEL_DIR / "state.json"


# ──────────────────────────────────────────────────────────────────────
# Typed views
# ──────────────────────────────────────────────────────────────────────

@dataclass
class Lab:
    """A lab is a unit of long-lived work. Today this maps to:
    - A surface under surfaces/ (e.g. studio, advisory)
    - A research investigation under research/investigations/
    - A worktree under trees/ (federation arm)

    Each lab has a kind that says where its real state lives.
    """
    slug: str
    kind: str  # "surface" | "investigation" | "worktree"
    title: str
    status: str  # "active" | "dormant" | "cycling" | "finalized" | "stuck" | "unknown"
    description: str = ""
    last_touched: Optional[datetime] = None
    days_since_touch: Optional[int] = None
    rot_color: str = "green"  # green | yellow | red — derived from days_since_touch
    path: Optional[Path] = None  # primary on-disk location
    has_active_claws: bool = False
    cumulative_dollars: float = 0.0


@dataclass
class LedgerRow:
    """One row from the ledger — a claw spawn or significant op event."""
    timestamp: datetime
    lab: str           # lab slug or "studio" for cross-lab
    skill: str         # claw name / op name
    model: str         # which model ran
    cost_usd: float
    tokens_in: int = 0
    tokens_out: int = 0
    latency_seconds: float = 0.0
    artifact_path: Optional[str] = None
    cycle: Optional[int] = None
    phase: Optional[str] = None
    type: str = "claw"  # claw | publish | other


@dataclass
class BellclawItem:
    """One queued item from the passive listener (when Bellclaw exists).

    For now: a placeholder. The bridge TUI shows this view with an
    explanatory empty state until Bellclaw is built.
    """
    timestamp: datetime
    source: str  # gmail | gcal | drive | telegram | cron | ...
    kind: str
    summary: str
    payload_path: Optional[str] = None
    lab_hint: Optional[str] = None


@dataclass
class SpineAsset:
    """Something pulled from the spine — a claw def, play, capability, runbook."""
    name: str
    kind: str  # claw | play | capability | runbook | skill
    version: str
    path: Path
    last_validated: Optional[str] = None
    status: str = "stable"


@dataclass
class Contract:
    """A frozen contract for an investigation/lab."""
    lab_slug: str
    version: int
    question: str
    quality_bar: str
    cycle_cap: int
    budget_dollars: float
    path: Path


@dataclass
class StudioSnapshot:
    """The bridge TUI's primary data view. One call returns everything
    needed to render the bridge."""
    generated_at: datetime
    labs: list[Lab]
    queue: list[BellclawItem]
    recent_ledger: list[LedgerRow]
    spine: list[SpineAsset]
    cumulative_dollars_all_time: float
    cumulative_dollars_today: float


@dataclass
class LabSnapshot:
    """The lab TUI's primary data view."""
    generated_at: datetime
    lab: Lab
    contracts: list[Contract]
    recent_ledger: list[LedgerRow]
    active_claws: list[LedgerRow]  # claws with status=running (placeholder for now)
    artifacts_root: Path
    plays_available: list[SpineAsset]
    claws_available: list[SpineAsset]


# ──────────────────────────────────────────────────────────────────────
# I/O helpers
# ──────────────────────────────────────────────────────────────────────

def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open() as f:
        return json.load(f)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Handle both Z-suffixed and offset-suffixed ISO timestamps
        s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except (ValueError, TypeError):
        return None


def _rot_color(days: Optional[int]) -> str:
    if days is None:
        return "gray"
    if days < 3:
        return "green"
    if days < 14:
        return "yellow"
    return "red"


def _git_last_commit_dt(repo_path: Path) -> Optional[datetime]:
    """Last commit ISO timestamp at repo path. None if not a git repo."""
    import subprocess
    if not (repo_path / ".git").exists() and not repo_path.joinpath(".git").is_file():
        # might be a worktree — .git is a file in worktrees
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%cI"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return _parse_dt(result.stdout.strip())
        except Exception:
            return None
        return None
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return _parse_dt(result.stdout.strip())
    except Exception:
        pass
    return None


# ──────────────────────────────────────────────────────────────────────
# Lab discovery
# ──────────────────────────────────────────────────────────────────────

def list_surfaces() -> list[Lab]:
    """Surfaces under surfaces/<name>/README.md. Each is a lab kind=surface."""
    out = []
    if not SURFACES_DIR.exists():
        return out
    for surface_dir in sorted(SURFACES_DIR.iterdir()):
        if not surface_dir.is_dir():
            continue
        readme = surface_dir / "README.md"
        if not readme.exists():
            continue
        # Read status from frontmatter
        status = "unknown"
        title = surface_dir.name.title()
        description = ""
        try:
            content = readme.read_text()
            for line in content.splitlines()[:50]:
                line_lower = line.strip().lower()
                if line_lower.startswith("status:"):
                    status = line.split(":", 1)[1].strip()
                elif line_lower.startswith("name:"):
                    title = line.split(":", 1)[1].strip()
        except Exception:
            pass

        last_touched = _git_last_commit_dt(LAB_ROOT)  # whole-repo proxy for now
        days = None
        if last_touched:
            days = (_now_utc() - last_touched).days

        out.append(Lab(
            slug=f"surface/{surface_dir.name}",
            kind="surface",
            title=title,
            status=status,
            description=description,
            last_touched=last_touched,
            days_since_touch=days,
            rot_color=_rot_color(days),
            path=surface_dir,
        ))
    return out


def list_investigations() -> list[Lab]:
    """Research investigations under research/investigations/<slug>/."""
    out = []
    if not INVESTIGATIONS_DIR.exists():
        return out
    for inv_dir in sorted(INVESTIGATIONS_DIR.iterdir()):
        if not inv_dir.is_dir():
            continue
        if inv_dir.name.startswith("."):
            continue
        state_path = inv_dir / "state.json"
        contract_path = inv_dir / "CONTRACT.yaml"
        status = "unknown"
        cumulative = 0.0
        last_touched = None
        title = inv_dir.name
        description = ""

        if state_path.exists():
            state = _read_json(state_path)
            status = state.get("status", "unknown")
            cumulative = float(state.get("cumulative_dollars", 0.0))
            last_touched = _parse_dt(state.get("updated_at"))

        if contract_path.exists():
            try:
                # Lazy yaml import — only if available
                import yaml
                with contract_path.open() as f:
                    contract = yaml.safe_load(f)
                question = (contract.get("question") or "").strip()
                if question:
                    description = question[:200]
                title = contract.get("title") or inv_dir.name
            except Exception:
                pass

        days = None
        if last_touched:
            days = (_now_utc() - last_touched).days

        out.append(Lab(
            slug=f"investigation/{inv_dir.name}",
            kind="investigation",
            title=title,
            status=status,
            description=description,
            last_touched=last_touched,
            days_since_touch=days,
            rot_color=_rot_color(days),
            path=inv_dir,
            cumulative_dollars=cumulative,
        ))
    return out


def list_worktree_arms() -> list[Lab]:
    """Federation arm worktrees under cairn-gate-labs/trees/<slug>/."""
    out = []
    if not TREES_ROOT.exists():
        return out
    for tree_dir in sorted(TREES_ROOT.iterdir()):
        if not tree_dir.is_dir():
            continue
        last_touched = _git_last_commit_dt(tree_dir)
        days = None
        if last_touched:
            days = (_now_utc() - last_touched).days

        # Try to read STATUS.md for a one-line "right now"
        status_md = next((p for p in tree_dir.rglob("STATUS.md")), None)
        description = ""
        if status_md:
            try:
                lines = status_md.read_text().splitlines()
                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("-") and not line.startswith("**"):
                        description = line[:200]
                        break
            except Exception:
                pass

        out.append(Lab(
            slug=f"arm/{tree_dir.name}",
            kind="worktree",
            title=tree_dir.name,
            status="active" if days is not None and days < 7 else "dormant",
            description=description,
            last_touched=last_touched,
            days_since_touch=days,
            rot_color=_rot_color(days),
            path=tree_dir,
        ))
    return out


def list_systems() -> list[Lab]:
    """Systems labs under systems/<name>/README.md. Internal infra/tools labs."""
    out = []
    systems_dir = LAB_ROOT / "systems"
    if not systems_dir.exists():
        return out
    for d in sorted(systems_dir.iterdir()):
        if not d.is_dir():
            continue
        readme = d / "README.md"
        if not readme.exists():
            continue
        status = "unknown"
        title = d.name.title()
        description = ""
        try:
            content = readme.read_text()
            for line in content.splitlines()[:50]:
                line_lower = line.strip().lower()
                if line_lower.startswith("status:"):
                    status = line.split(":", 1)[1].strip()
                elif line_lower.startswith("name:"):
                    title = line.split(":", 1)[1].strip()
        except Exception:
            pass
        last_touched = _git_last_commit_dt(LAB_ROOT)
        days = (_now_utc() - last_touched).days if last_touched else None
        out.append(Lab(
            slug=f"systems/{d.name}",
            kind="systems",
            title=title,
            status=status,
            description=description,
            last_touched=last_touched,
            days_since_touch=days,
            rot_color=_rot_color(days),
            path=d,
        ))
    return out


def list_functions() -> list[Lab]:
    """Functions under functions/<name>/README.md. Each is kind=function.

    Per ADR-0013, functions are organs that operate on other entities'
    outputs (retros, audits, post-mortems, etc.). Same Lab dataclass for
    tooling consistency, but kind='function' distinguishes them from
    labs at the data layer.
    """
    out = []
    if not FUNCTIONS_DIR.exists():
        return out
    for fn_dir in sorted(FUNCTIONS_DIR.iterdir()):
        if not fn_dir.is_dir():
            continue
        if fn_dir.name.startswith("."):
            continue
        readme = fn_dir / "README.md"
        if not readme.exists():
            continue
        status = "unknown"
        title = fn_dir.name.title()
        description = ""
        try:
            content = readme.read_text()
            for line in content.splitlines()[:50]:
                line_lower = line.strip().lower()
                if line_lower.startswith("status:"):
                    status = line.split(":", 1)[1].strip()
                elif line_lower.startswith("name:"):
                    title = line.split(":", 1)[1].strip()
        except Exception:
            pass
        last_touched = _git_last_commit_dt(LAB_ROOT)
        days = None
        if last_touched:
            days = (_now_utc() - last_touched).days
        out.append(Lab(
            slug=f"function/{fn_dir.name}",
            kind="function",
            title=title,
            status=status,
            description=description,
            last_touched=last_touched,
            days_since_touch=days,
            rot_color=_rot_color(days),
            path=fn_dir,
        ))
    return out


def list_labs() -> list[Lab]:
    """All labs (surfaces + investigations + systems). Arms are NOT labs;
    they are branches of work belonging to a lab. See list_arms_for(slug).

    NOTE: functions are NOT labs (per ADR-0013). For the unified entity
    list (labs + functions), use list_entities()."""
    return list_surfaces() + list_systems() + list_investigations()


def list_entities() -> list[Lab]:
    """All CGL entities — labs + functions, unified.

    Per ADR-0013, functions live alongside labs but are a distinct kind.
    Tooling that wants the full inventory uses this; tooling that
    distinguishes labs from functions uses list_labs() / list_functions().
    """
    return list_labs() + list_functions()


def list_arms_for(slug: str) -> list[dict]:
    """Return arms (worktrees) belonging to a lab.

    Convention: an arm of lab <slug> lives at trees/<arm-name>/ on branch
    arm/<slug-encoded>/<arm-name>, where slug-encoded is slug.replace('/','-').

    Returns list of dicts: {name, path, branch, last_touched, days, rot}.
    """
    if not TREES_ROOT.exists():
        return []
    encoded = slug.replace("/", "-")
    out = []
    for tree_dir in sorted(TREES_ROOT.iterdir()):
        if not tree_dir.is_dir():
            continue
        # Read the worktree's branch
        try:
            import subprocess
            r = subprocess.run(
                ["git", "-C", str(tree_dir), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True,
            )
            branch = r.stdout.strip()
        except Exception:
            continue
        # Match either arm/<encoded>/<name> OR — for legacy compatibility —
        # any branch that contains the slug somewhere (looser fallback).
        prefix = f"arm/{encoded}/"
        if not branch.startswith(prefix):
            continue
        last_touched = _git_last_commit_dt(tree_dir)
        days = (_now_utc() - last_touched).days if last_touched else None
        out.append({
            "name": branch[len(prefix):],
            "path": str(tree_dir),
            "branch": branch,
            "last_touched": last_touched.isoformat() if last_touched else None,
            "days": days,
            "rot": _rot_color(days),
        })
    return out


def legacy_orphan_worktrees() -> list[dict]:
    """Worktrees that don't fit the arm/<lab-slug>/<name> convention.

    Useful during migration — tells the director "these worktrees aren't
    yet attached to a parent lab."
    """
    if not TREES_ROOT.exists():
        return []
    out = []
    for tree_dir in sorted(TREES_ROOT.iterdir()):
        if not tree_dir.is_dir():
            continue
        try:
            import subprocess
            r = subprocess.run(
                ["git", "-C", str(tree_dir), "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True,
            )
            branch = r.stdout.strip()
        except Exception:
            continue
        if branch.startswith("arm/") or branch.startswith("claw/"):
            # Either properly attached or an ephemeral claw — skip
            continue
        out.append({"name": tree_dir.name, "branch": branch, "path": str(tree_dir)})
    return out


def get_lab(slug: str) -> Optional[Lab]:
    """Look up a single entity (lab OR function) by slug.

    Despite the name, this resolves any CGL entity — labs (surface/,
    investigation/, system/) AND functions (function/) per ADR-0013.
    Kept the name 'get_lab' for backward compatibility; consumers can
    treat the result the same regardless of kind.
    """
    for entity in list_entities():
        if entity.slug == slug:
            return entity
    return None


# ──────────────────────────────────────────────────────────────────────
# Ledger
# ──────────────────────────────────────────────────────────────────────

def studio_ledger(limit: int = 50) -> list[LedgerRow]:
    """Ledger rows across all labs. Today: stitched from per-investigation
    costs.jsonl + intel/publish-log.jsonl.

    v0.next: a single studio/ledger.jsonl as the primitive ledger.
    """
    rows: list[LedgerRow] = []

    # Per-investigation costs.jsonl
    if INVESTIGATIONS_DIR.exists():
        for inv_dir in INVESTIGATIONS_DIR.iterdir():
            costs_path = inv_dir / "costs.jsonl"
            if not costs_path.exists():
                continue
            for c in _read_jsonl(costs_path):
                ts = _parse_dt(c.get("timestamp"))
                if not ts:
                    continue
                rows.append(LedgerRow(
                    timestamp=ts,
                    lab=f"investigation/{inv_dir.name}",
                    skill=c.get("skill", "?"),
                    model=c.get("model", "?"),
                    cost_usd=float(c.get("dollars", 0.0)),
                    tokens_in=int(c.get("tokens_in", 0)),
                    tokens_out=int(c.get("tokens_out", 0)),
                    latency_seconds=float(c.get("latency_seconds", 0.0)),
                    cycle=c.get("cycle"),
                    phase=c.get("phase"),
                    type="claw",
                ))

    # Publish log → publishes
    for p in _read_jsonl(PUBLISH_LOG):
        ts = _parse_dt(p.get("published_at"))
        if not ts:
            continue
        rows.append(LedgerRow(
            timestamp=ts,
            lab=f"investigation/{p['slug']}" if p.get("slug") else "studio",
            skill="cgl-publish",
            model="-",
            cost_usd=0.0,
            artifact_path=p.get("doc_url"),
            type="publish",
        ))

    rows.sort(key=lambda r: r.timestamp, reverse=True)
    return rows[:limit]


def lab_ledger(lab_slug: str, limit: int = 30) -> list[LedgerRow]:
    """Ledger rows for one lab."""
    return [r for r in studio_ledger(limit=10000) if r.lab == lab_slug][:limit]


def cumulative_dollars(rows: Optional[list[LedgerRow]] = None) -> float:
    """Sum cost across rows (defaults to whole studio)."""
    rs = rows if rows is not None else studio_ledger(limit=10000)
    return sum(r.cost_usd for r in rs)


def cumulative_dollars_today(rows: Optional[list[LedgerRow]] = None) -> float:
    """Sum cost for rows from today (UTC)."""
    today = _now_utc().date()
    rs = rows if rows is not None else studio_ledger(limit=10000)
    return sum(r.cost_usd for r in rs if r.timestamp.date() == today)


# ──────────────────────────────────────────────────────────────────────
# Bellclaw queue (placeholder)
# ──────────────────────────────────────────────────────────────────────

def bellclaw_queue() -> list[BellclawItem]:
    """Read bellclaw queue. Empty until Bellclaw is built."""
    queue_path = LAB_ROOT / "studio" / "bellclaw" / "queue.jsonl"
    if not queue_path.exists():
        return []
    out = []
    for item in _read_jsonl(queue_path):
        ts = _parse_dt(item.get("timestamp"))
        if not ts:
            continue
        out.append(BellclawItem(
            timestamp=ts,
            source=item.get("source", "?"),
            kind=item.get("kind", "?"),
            summary=item.get("summary", ""),
            payload_path=item.get("payload_path"),
            lab_hint=item.get("lab_hint"),
        ))
    out.sort(key=lambda x: x.timestamp, reverse=True)
    return out


# ──────────────────────────────────────────────────────────────────────
# Spine assets
# ──────────────────────────────────────────────────────────────────────

def list_spine() -> list[SpineAsset]:
    """Spine assets — for now: skills under .claude/skills/director/, plus
    runbooks/. Pulls metadata where available.
    """
    out = []
    skills_dir = LAB_ROOT / ".claude" / "skills" / "director"
    if skills_dir.exists():
        for f in sorted(skills_dir.iterdir()):
            if f.is_file() and not f.name.startswith("."):
                out.append(SpineAsset(
                    name=f.name,
                    kind="capability",
                    version="git",
                    path=f,
                    status="stable",
                ))
            elif f.is_dir() and (f / "SKILL.md").exists():
                out.append(SpineAsset(
                    name=f.name,
                    kind="skill",
                    version="git",
                    path=f / "SKILL.md",
                    status="stable",
                ))

    if RUNBOOKS_DIR.exists():
        for f in sorted(RUNBOOKS_DIR.glob("*.md")):
            out.append(SpineAsset(
                name=f.stem,
                kind="runbook",
                version="git",
                path=f,
                status="stable",
            ))

    return out


# ──────────────────────────────────────────────────────────────────────
# Contracts (per investigation)
# ──────────────────────────────────────────────────────────────────────

def list_contracts(lab_slug: str) -> list[Contract]:
    """Contracts in a lab. Today only investigations have contracts."""
    out = []
    if not lab_slug.startswith("investigation/"):
        return out
    inv_name = lab_slug.split("/", 1)[1]
    inv_dir = INVESTIGATIONS_DIR / inv_name
    if not inv_dir.exists():
        return out
    for contract_path in sorted(inv_dir.glob("CONTRACT*.yaml")):
        try:
            import yaml
            with contract_path.open() as f:
                c = yaml.safe_load(f)
            out.append(Contract(
                lab_slug=lab_slug,
                version=int(c.get("version", 1)),
                question=(c.get("question") or "").strip(),
                quality_bar=c.get("quality_bar", "?"),
                cycle_cap=int(c.get("cycle_cap", 1)),
                budget_dollars=float(c.get("budget_dollars", 0.0)),
                path=contract_path,
            ))
        except Exception:
            continue
    return out


# ──────────────────────────────────────────────────────────────────────
# Snapshots (the high-level views the TUIs use)
# ──────────────────────────────────────────────────────────────────────

def studio_snapshot() -> StudioSnapshot:
    """The bridge TUI calls this once on attach."""
    rows = studio_ledger(limit=200)
    return StudioSnapshot(
        generated_at=_now_utc(),
        labs=list_labs(),
        queue=bellclaw_queue(),
        recent_ledger=rows[:20],
        spine=list_spine(),
        cumulative_dollars_all_time=cumulative_dollars(rows),
        cumulative_dollars_today=cumulative_dollars_today(rows),
    )


def lab_snapshot(lab_slug: str) -> Optional[LabSnapshot]:
    """The lab TUI calls this on entering a lab."""
    lab = get_lab(lab_slug)
    if lab is None:
        return None
    rows = lab_ledger(lab_slug, limit=30)
    contracts = list_contracts(lab_slug)
    artifacts_root = lab.path or LAB_ROOT
    return LabSnapshot(
        generated_at=_now_utc(),
        lab=lab,
        contracts=contracts,
        recent_ledger=rows,
        active_claws=[],  # placeholder — needs real "is this skill running NOW" detection
        artifacts_root=artifacts_root,
        plays_available=[],  # placeholder until plays exist as data
        claws_available=[],  # placeholder until claws exist declaratively
    )


# ──────────────────────────────────────────────────────────────────────
# CLI for smoke-testing
# ──────────────────────────────────────────────────────────────────────

def _to_serializable(obj):
    """Recursive converter so dataclasses + datetimes + paths print as JSON."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_serializable(getattr(obj, k)) for k in obj.__dataclass_fields__}
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, list):
        return [_to_serializable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    return obj


def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="state_reader smoke-test CLI")
    parser.add_argument(
        "view",
        choices=[
            "labs", "studio", "ledger", "queue", "spine",
            "lab", "lab-ledger", "contracts",
        ],
        help="Which view to print.",
    )
    parser.add_argument("--slug", help="Lab slug (for lab/lab-ledger/contracts views)")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    if args.view == "labs":
        out = [_to_serializable(l) for l in list_labs()]
    elif args.view == "studio":
        out = _to_serializable(studio_snapshot())
    elif args.view == "ledger":
        out = [_to_serializable(r) for r in studio_ledger(limit=args.limit)]
    elif args.view == "queue":
        out = [_to_serializable(b) for b in bellclaw_queue()]
    elif args.view == "spine":
        out = [_to_serializable(s) for s in list_spine()]
    elif args.view == "lab":
        if not args.slug:
            print("error: --slug required", file=__import__("sys").stderr)
            return
        snap = lab_snapshot(args.slug)
        out = _to_serializable(snap) if snap else None
    elif args.view == "lab-ledger":
        if not args.slug:
            print("error: --slug required", file=__import__("sys").stderr)
            return
        out = [_to_serializable(r) for r in lab_ledger(args.slug, limit=args.limit)]
    elif args.view == "contracts":
        if not args.slug:
            print("error: --slug required", file=__import__("sys").stderr)
            return
        out = [_to_serializable(c) for c in list_contracts(args.slug)]
    else:
        out = None

    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    _cli()
