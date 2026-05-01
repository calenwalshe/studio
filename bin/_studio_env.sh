#!/usr/bin/env bash
# Sourced by every cgl-* shell script. Single source of truth for env.
#
# Required:
#   CGL_LAB_ROOT          path to the lab the harness operates on
#
# Derived (do not set):
#   CGL_LAB_BASENAME      basename of CGL_LAB_ROOT (or CGL_PROFILE if set)
#   CGL_STATE_DIR         per-lab state: ~/.local/state/studio/<basename>/
#   CGL_TMUX_SESSION      tmux session name: cgl-<basename>
#   CGL_TITLE             user-visible federation title (default: <basename>)
#
# Optional:
#   CGL_PROFILE           override the basename (when basenames clash)
#   CGL_TITLE             override the federation title
#   CGL_PUBLIC_HOST       e.g. cairnlabs.org — for surface URL probes
#   CGL_DEPLOY_PATH       e.g. /srv/static/example.com — for static deploy sync

# Refuse to proceed without a lab root
if [[ -z "${CGL_LAB_ROOT:-}" ]]; then
  echo "error: CGL_LAB_ROOT is not set" >&2
  echo "  set it to your lab directory, e.g.:" >&2
  echo "    export CGL_LAB_ROOT=\"\$HOME/projects/my-lab\"" >&2
  exit 1
fi
if [[ ! -d "$CGL_LAB_ROOT" ]]; then
  echo "error: CGL_LAB_ROOT=$CGL_LAB_ROOT is not a directory" >&2
  exit 1
fi

CGL_LAB_BASENAME="${CGL_PROFILE:-$(basename "$CGL_LAB_ROOT")}"
CGL_STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/studio/$CGL_LAB_BASENAME"
CGL_TMUX_SESSION="cgl-$CGL_LAB_BASENAME"
CGL_TITLE="${CGL_TITLE:-$CGL_LAB_BASENAME}"

mkdir -p "$CGL_STATE_DIR"

export CGL_LAB_ROOT CGL_LAB_BASENAME CGL_STATE_DIR CGL_TMUX_SESSION CGL_TITLE
