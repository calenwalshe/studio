#!/usr/bin/env bash
#
# install.sh — set up Studio on this machine.
#
# What this does:
#   1. Creates the Python venv at studio/.venv with textual installed.
#   2. Optionally prompts for a default CGL_LAB_ROOT and writes it to
#      ~/.config/cgl/config.toml.
#   3. Symlinks bin/cgl-* into a directory on your PATH (default: ~/.local/bin).
#
# What this does NOT do:
#   - Install tmux, git, jq, curl, claude — you need those already.
#   - Edit your shell rc. The script prints what to add; you copy.
#   - Touch any user lab. Studio is just a tool; your labs are your data.
#
# Usage:
#   ./install.sh                    interactive
#   ./install.sh --bin-dir ~/bin    pick a different symlink target
#   ./install.sh --no-config        skip the config-file step
#   ./install.sh --help

set -euo pipefail

HARNESS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$HOME/.local/bin"
WRITE_CONFIG=1
LAB_ROOT_DEFAULT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bin-dir)    BIN_DIR="$2"; shift 2 ;;
    --no-config)  WRITE_CONFIG=0; shift ;;
    --lab-root)   LAB_ROOT_DEFAULT="$2"; shift 2 ;;
    --help|-h)
      sed -n '3,/^set -euo/p' "$0" | grep '^#' | sed 's/^# \?//'
      exit 0
      ;;
    *)
      echo "unknown flag: $1" >&2
      exit 2
      ;;
  esac
done

# ── 1. Dependencies ─────────────────────────────────────────────────

missing=()
for cmd in python3 git tmux jq curl; do
  command -v "$cmd" >/dev/null || missing+=("$cmd")
done
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "error: missing required commands: ${missing[*]}" >&2
  echo "  install them first, then re-run install.sh" >&2
  exit 1
fi

if ! command -v claude >/dev/null; then
  echo "warning: 'claude' (Claude Code CLI) is not on PATH" >&2
  echo "  Studio's supervisor + claw primitives won't work without it." >&2
  echo "  See https://docs.claude.com/claude-code for install." >&2
  echo
fi

# ── 2. Python venv ──────────────────────────────────────────────────

VENV="$HARNESS/studio/.venv"
echo "→ creating venv at $VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet textual
echo "  textual installed"

# ── 3. Config file ──────────────────────────────────────────────────

if [[ "$WRITE_CONFIG" == "1" ]]; then
  CONFIG_DIR="$HOME/.config/cgl"
  CONFIG_FILE="$CONFIG_DIR/config.toml"
  mkdir -p "$CONFIG_DIR"

  if [[ -n "$LAB_ROOT_DEFAULT" ]]; then
    LAB_ROOT_PROMPT="$LAB_ROOT_DEFAULT"
  elif [[ -f "$CONFIG_FILE" ]]; then
    LAB_ROOT_PROMPT=$(grep -E '^lab_root\s*=' "$CONFIG_FILE" | sed -E 's/.*=\s*"([^"]*)"/\1/')
  else
    LAB_ROOT_PROMPT="$HOME/projects/my-lab"
  fi

  echo
  echo "→ default lab root (where your lab content lives)"
  echo "  example: $HARNESS/examples/hello-lab"
  read -r -p "  lab root [$LAB_ROOT_PROMPT]: " input
  LAB_ROOT="${input:-$LAB_ROOT_PROMPT}"
  if [[ ! -d "$LAB_ROOT" ]]; then
    echo "  warning: $LAB_ROOT does not exist (yet) — config saved anyway" >&2
  fi

  cat > "$CONFIG_FILE" <<EOF
# Studio config — read by cgl-* scripts when CGL_LAB_ROOT is unset.
lab_root = "$LAB_ROOT"
EOF
  echo "  wrote $CONFIG_FILE"
fi

# ── 4. Symlink primitives ───────────────────────────────────────────

mkdir -p "$BIN_DIR"
echo
echo "→ symlinking bin/cgl-* into $BIN_DIR"
for src in "$HARNESS/bin/"cgl-*; do
  name=$(basename "$src")
  target="$BIN_DIR/$name"
  if [[ -L "$target" ]] || [[ -f "$target" ]]; then
    rm "$target"
  fi
  ln -s "$src" "$target"
  echo "  $name"
done

# ── 5. Final notes ──────────────────────────────────────────────────

echo
echo "✓ Studio installed."
echo
echo "Next:"
echo "  1. Make sure $BIN_DIR is on your PATH. Add to your shell rc:"
echo "     export PATH=\"$BIN_DIR:\$PATH\""
echo
echo "  2. From any shell, set CGL_LAB_ROOT to your lab dir:"
echo "     export CGL_LAB_ROOT=\"$HOME/projects/my-lab\""
echo
echo "  3. Run: cgl-tmux"
echo
echo "  Multi-lab tip: don't export CGL_LAB_ROOT globally; set it per-shell"
echo "  to switch between labs without affecting other terminals."
