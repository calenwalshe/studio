#!/usr/bin/env python3
"""
_studio_orient_spawn.py — orientation-driven dry-run spawn for cgl-claw.

Called by `cgl-claw spawn --orientation <id> --role <role> [--dry-run]`.
Delegates to _studio_orient for config loading, validation, and bundle writing.

Arc B.3: Only --dry-run is supported. Real claw execution arrives in Arc C.
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _studio_orient import (
    StudioConfigError,
    construct_envelope,
    envelope_to_dict,
    get_orientation,
    load_studio_config,
    validate_role,
    write_dry_run_bundle,
)


def main() -> int:
    # Resolve CGL_LAB_ROOT from environment (mirrors _studio_env.sh convention)
    lab_root_str = os.environ.get("CGL_LAB_ROOT", "")
    if not lab_root_str:
        print("error: CGL_LAB_ROOT is not set", file=sys.stderr)
        print("  set it to your lab directory, e.g.:", file=sys.stderr)
        print('    export CGL_LAB_ROOT="$HOME/projects/my-lab"', file=sys.stderr)
        print("  or run install.sh to write a config file.", file=sys.stderr)
        return 1

    lab_root = Path(lab_root_str)
    if not lab_root.is_dir():
        print(f"error: CGL_LAB_ROOT={lab_root_str} is not a directory", file=sys.stderr)
        return 1

    parser = argparse.ArgumentParser(
        prog="cgl-claw spawn",
        description="Orientation-driven dry-run claw spawn (Arc B).",
        add_help=True,
    )
    parser.add_argument(
        "--orientation",
        required=True,
        metavar="<id>",
        help="Orientation ID from .studio/orientations.toml",
    )
    parser.add_argument(
        "--role",
        required=True,
        metavar="<role>",
        help="Claw role (scout, researcher, builder, reviewer, operator, curator)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Write a stub artifact bundle without executing claude",
    )

    args = parser.parse_args()

    if not args.dry_run:
        print(
            "error: --dry-run is required for orientation-mode spawn "
            "(real claw integration is Arc C)",
            file=sys.stderr,
        )
        return 2

    try:
        config = load_studio_config(lab_root)
        orientation = get_orientation(config, args.orientation)
        validate_role(config, args.role)
    except StudioConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    # Verify the role is permitted by this orientation
    allowed_roles = list(orientation.roles) if hasattr(orientation, "roles") else []
    if args.role not in allowed_roles:
        print(
            f"error: role '{args.role}' is not in orientation '{args.orientation}' "
            f"(allowed: {', '.join(allowed_roles)})",
            file=sys.stderr,
        )
        return 1

    try:
        envelope = construct_envelope(config, orientation, args.role, lab_root=lab_root)
    except StudioConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    bundle_dir = Path(envelope.bundle_dir)

    write_dry_run_bundle(envelope, bundle_dir)

    # Print envelope JSON to stdout
    print(json.dumps(envelope_to_dict(envelope), indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
