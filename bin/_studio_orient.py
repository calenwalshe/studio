from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STUDIO_TOML_FILES = [
    "lab.toml",
    "orientations.toml",
    "roles.toml",
    "capabilities.toml",
    "runtimes.toml",
    "promotion.toml",
]
OPTIONAL_TOML_FILES = ["sources.toml", "tools.toml"]


class StudioConfigError(Exception):
    pass


@dataclass(frozen=True)
class Orientation:
    id: str
    lab: str
    objective: str
    status: str
    stop_rule: str
    roles: tuple[str, ...]
    sources: tuple[str, ...]
    outputs: tuple[str, ...]
    constraints: dict[str, Any]


@dataclass(frozen=True)
class Role:
    name: str
    description: str
    default_runtime: str
    default_capability: str
    outputs: tuple[str, ...]


@dataclass(frozen=True)
class Capability:
    name: str
    filesystem: str
    network: str
    shell: str
    secrets: tuple[str, ...]
    tools: tuple[str, ...]
    promotion: str


@dataclass(frozen=True)
class Runtime:
    name: str
    command: str
    mode: str
    status: str


@dataclass(frozen=True)
class ExecutionEnvelope:
    orientation_id: str
    role: str
    lab_slug: str
    claw_id: str
    runtime: Runtime
    capability_profile: Capability
    source_scope: tuple[str, ...]
    worktree_path: str
    bundle_dir: str
    output_contract: tuple[str, ...]
    started_at: str


@dataclass(frozen=True)
class StudioConfig:
    lab: dict[str, Any]
    orientations: list[dict[str, Any]]
    roles: dict[str, Any]
    capabilities: dict[str, Any]
    runtimes: dict[str, Any]
    promotion: dict[str, Any]
    sources: dict[str, Any]


def _load_toml(path: Path, label: str) -> dict[str, Any]:
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        raise StudioConfigError(f"missing .studio/{label} in {path.parent.parent}")
    except tomllib.TOMLDecodeError as exc:
        raise StudioConfigError(f"malformed .studio/{label}: {exc}")


def load_studio_config(lab_root: Path) -> StudioConfig:
    studio = lab_root / ".studio"

    raw: dict[str, dict] = {}
    for name in STUDIO_TOML_FILES:
        raw[name] = _load_toml(studio / name, name)

    for name in OPTIONAL_TOML_FILES:
        p = studio / name
        if p.exists():
            try:
                with open(p, "rb") as fh:
                    raw[name] = tomllib.load(fh)
            except tomllib.TOMLDecodeError as exc:
                raise StudioConfigError(f"malformed .studio/{name}: {exc}")
        else:
            raw[name] = {}

    orientations_raw = raw["orientations.toml"].get("orientation", [])
    if not isinstance(orientations_raw, list):
        orientations_raw = [orientations_raw]

    return StudioConfig(
        lab=raw["lab.toml"],
        orientations=orientations_raw,
        roles=raw["roles.toml"].get("roles", {}),
        capabilities=raw["capabilities.toml"].get("capabilities", {}),
        runtimes=raw["runtimes.toml"].get("runtimes", {}),
        promotion=raw["promotion.toml"],
        sources=raw["sources.toml"].get("sources", {}),
    )


def list_orientations(cfg: StudioConfig) -> list[Orientation]:
    return [_orientation_from_dict(o) for o in cfg.orientations]


def _orientation_from_dict(raw: dict[str, Any]) -> Orientation:
    return Orientation(
        id=raw["id"],
        lab=raw["lab"],
        objective=raw["objective"],
        status=raw["status"],
        stop_rule=raw["stop_rule"],
        roles=tuple(raw.get("roles", [])),
        sources=tuple(raw.get("sources", [])),
        outputs=tuple(raw.get("outputs", [])),
        constraints=raw.get("constraints", {}),
    )


def get_orientation(cfg: StudioConfig, orientation_id: str) -> Orientation:
    for raw in cfg.orientations:
        if raw.get("id") == orientation_id:
            return _orientation_from_dict(raw)
    available = [o.get("id", "?") for o in cfg.orientations]
    raise StudioConfigError(
        f"orientation '{orientation_id}' not found in .studio/orientations.toml; "
        f"available: {available}"
    )


def validate_role(cfg: StudioConfig, role: str) -> Role:
    raw = cfg.roles.get(role)
    if raw is None:
        raise StudioConfigError(
            f"role '{role}' not found in .studio/roles.toml; "
            f"available: {list(cfg.roles.keys())}"
        )
    return Role(
        name=role,
        description=raw.get("description", ""),
        default_runtime=raw["default_runtime"],
        default_capability=raw["default_capability"],
        outputs=tuple(raw.get("outputs", [])),
    )


def resolve_capability(cfg: StudioConfig, role: Role) -> Capability:
    cap_name = role.default_capability
    raw = cfg.capabilities.get(cap_name)
    if raw is None:
        raise StudioConfigError(
            f"role '{role.name}' references capability '{cap_name}' which is not "
            f"defined in .studio/capabilities.toml"
        )
    return Capability(
        name=cap_name,
        filesystem=raw["filesystem"],
        network=raw["network"],
        shell=raw["shell"],
        secrets=tuple(raw.get("secrets", [])),
        tools=tuple(raw.get("tools", [])),
        promotion=raw["promotion"],
    )


def resolve_runtime(cfg: StudioConfig, role: Role) -> Runtime:
    rt_name = role.default_runtime
    raw = cfg.runtimes.get(rt_name)
    if raw is None:
        raise StudioConfigError(
            f"role '{role.name}' references runtime '{rt_name}' which is not "
            f"defined in .studio/runtimes.toml"
        )
    return Runtime(
        name=rt_name,
        command=raw["command"],
        mode=raw["mode"],
        status=raw["status"],
    )


def claw_id(role: str, lab_slug: str, *, ts: datetime | None = None) -> str:
    if ts is None:
        ts = datetime.now(tz=timezone.utc)
    ts_str = ts.strftime("%Y%m%d-%H%M%S")
    slug_safe = re.sub(r"[^a-z0-9-]", "", lab_slug.replace("/", "-").lower())
    return f"{ts_str}-{role}-{slug_safe}"


def construct_envelope(
    cfg: StudioConfig,
    orientation: Orientation,
    role_name: str,
    *,
    lab_root: Path,
) -> ExecutionEnvelope:
    role = validate_role(cfg, role_name)
    capability = resolve_capability(cfg, role)
    runtime = resolve_runtime(cfg, role)

    now = datetime.now(tz=timezone.utc)
    _claw_id = claw_id(role_name, orientation.lab, ts=now)

    lab_slug_safe = re.sub(r"[^a-z0-9-]", "", orientation.lab.replace("/", "-").lower())
    ts_str = now.strftime("%Y%m%d-%H%M%S")
    worktree_path = str(lab_root.parent / "trees" / f"claw-{lab_slug_safe}-{ts_str}")

    bundle_dir = str(lab_root / ".claws" / _claw_id)

    source_scope = tuple(
        s for s in orientation.sources if s in cfg.sources
    ) if cfg.sources else orientation.sources

    return ExecutionEnvelope(
        orientation_id=orientation.id,
        role=role_name,
        lab_slug=orientation.lab,
        claw_id=_claw_id,
        runtime=runtime,
        capability_profile=capability,
        source_scope=source_scope,
        worktree_path=worktree_path,
        bundle_dir=bundle_dir,
        output_contract=role.outputs,
        started_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _envelope_to_json_safe(envelope: ExecutionEnvelope) -> dict:
    return {
        "orientation_id": envelope.orientation_id,
        "role": envelope.role,
        "lab_slug": envelope.lab_slug,
        "claw_id": envelope.claw_id,
        "runtime": {
            "name": envelope.runtime.name,
            "command": envelope.runtime.command,
            "mode": envelope.runtime.mode,
            "status": envelope.runtime.status,
        },
        "capability_profile": {
            "name": envelope.capability_profile.name,
            "filesystem": envelope.capability_profile.filesystem,
            "network": envelope.capability_profile.network,
            "shell": envelope.capability_profile.shell,
            "secrets": list(envelope.capability_profile.secrets),
            "tools": list(envelope.capability_profile.tools),
            "promotion": envelope.capability_profile.promotion,
        },
        "source_scope": list(envelope.source_scope),
        "worktree_path": envelope.worktree_path,
        "bundle_dir": envelope.bundle_dir,
        "output_contract": list(envelope.output_contract),
        "started_at": envelope.started_at,
    }


def envelope_to_dict(envelope: ExecutionEnvelope) -> dict:
    return _envelope_to_json_safe(envelope)


def write_dry_run_bundle(
    envelope: ExecutionEnvelope,
    bundle_dir: Path,
) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    now_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    meta = {
        "id": envelope.claw_id,
        "orientation_id": envelope.orientation_id,
        "lab_slug": envelope.lab_slug,
        "role": envelope.role,
        "runtime": envelope.runtime.name,
        "capability_profile": envelope.capability_profile.name,
        "source_scope": list(envelope.source_scope),
        "status": "dry_run",
        "started_at": now_str,
        "ended_at": now_str,
        "promotion_recommendation": "abandon",
    }
    (bundle_dir / "meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )

    trace_event = {
        "ts": now_str,
        "event": "dry_run",
        "envelope": _envelope_to_json_safe(envelope),
    }
    (bundle_dir / "trace.jsonl").write_text(
        json.dumps(trace_event) + "\n", encoding="utf-8"
    )

    cap = envelope.capability_profile
    rt = envelope.runtime
    result_lines = [
        "# DRY RUN — would have spawned",
        "",
        f"**Claw ID:** {envelope.claw_id}",
        f"**Orientation:** {envelope.orientation_id}",
        f"**Lab:** {envelope.lab_slug}",
        f"**Role:** {envelope.role}",
        f"**Runtime:** {rt.name} (`{rt.command}`, mode={rt.mode})",
        f"**Capability profile:** {cap.name}",
        f"  - filesystem: {cap.filesystem}",
        f"  - network: {cap.network}",
        f"  - shell: {cap.shell}",
        f"  - tools: {', '.join(cap.tools) if cap.tools else '(none)'}",
        f"  - secrets: {', '.join(cap.secrets) if cap.secrets else '(none)'}",
        f"  - promotion: {cap.promotion}",
        f"**Source scope:** {', '.join(envelope.source_scope) if envelope.source_scope else '(none)'}",
        f"**Worktree path (not created):** {envelope.worktree_path}",
        f"**Bundle dir:** {envelope.bundle_dir}",
        f"**Output contract:** {', '.join(envelope.output_contract)}",
        f"**Started at:** {envelope.started_at}",
        "",
        "## Promotion recommendation",
        "",
        "abandon",
    ]
    (bundle_dir / "result.md").write_text("\n".join(result_lines) + "\n", encoding="utf-8")
