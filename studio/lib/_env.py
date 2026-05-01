"""_env.py — single source of truth for harness env resolution (Python side).

Read by state_reader, focus_core, bridge/app, lab_tui/app. Keeps the env-var
semantics in one place; matches bin/_studio_env.sh for shell scripts.

Required env:
    CGL_LAB_ROOT          absolute path to the lab dir the harness operates on

Derived:
    LAB_ROOT              Path object for the lab dir
    LAB_BASENAME          basename(CGL_LAB_ROOT) or CGL_PROFILE override
    STATE_DIR             ~/.local/state/studio/<basename>/  (XDG-aware)
    TMUX_SESSION          "cgl-<basename>"
    TITLE                 user-visible federation title
    PUBLIC_HOST           optional; for surface URL probes (e.g. cairnlabs.org)
    DEPLOY_PATH           optional; for static deploy sync
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _require_lab_root() -> Path:
    raw = os.environ.get("CGL_LAB_ROOT")
    if not raw:
        sys.stderr.write(
            "error: CGL_LAB_ROOT is not set\n"
            "  set it to your lab directory, e.g.:\n"
            "    export CGL_LAB_ROOT=\"$HOME/projects/my-lab\"\n"
        )
        sys.exit(1)
    p = Path(raw)
    if not p.is_dir():
        sys.stderr.write(f"error: CGL_LAB_ROOT={raw} is not a directory\n")
        sys.exit(1)
    return p


LAB_ROOT: Path = _require_lab_root()
LAB_BASENAME: str = os.environ.get("CGL_PROFILE") or LAB_ROOT.name
STATE_DIR: Path = Path(
    os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))
) / "studio" / LAB_BASENAME
TMUX_SESSION: str = f"cgl-{LAB_BASENAME}"
TITLE: str = os.environ.get("CGL_TITLE", LAB_BASENAME)
PUBLIC_HOST: str | None = os.environ.get("CGL_PUBLIC_HOST")
DEPLOY_PATH: str | None = os.environ.get("CGL_DEPLOY_PATH")

STATE_DIR.mkdir(parents=True, exist_ok=True)
