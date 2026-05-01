#!/usr/bin/env bash
# migrate-cgl.sh — one-shot setup to make CGL consume the studio harness.
#
# What this does:
#   1. Adds ~/projects/studio/bin/ to PATH (in front of ~/bin so studio's
#      versions win).
#   2. Sets CGL_LAB_ROOT to the CGL lab.
#   3. Sets CGL_PROFILE=cairn-gate-labs to disambiguate state.
#   4. Optionally git rm's CGL's lab/studio/{bridge,lab_tui,lib}/ so the
#      harness lives in only one place.
#
# Run it manually once. Then add the export lines below to your shell rc.

set -euo pipefail

STUDIO=$HOME/projects/studio
CGL_LAB=$HOME/projects/cairn-gate-labs/lab

if [[ ! -d "$STUDIO" ]]; then
  echo "error: studio not found at $STUDIO" >&2
  exit 1
fi
if [[ ! -d "$CGL_LAB" ]]; then
  echo "error: CGL lab not found at $CGL_LAB" >&2
  exit 1
fi

# Tell the user what to add to shell rc
echo "Add these lines to your shell rc (~/.bashrc, ~/.zshrc, etc.):"
echo
echo "  export PATH=\"\$HOME/projects/studio/bin:\$PATH\""
echo "  export CGL_LAB_ROOT=\"\$HOME/projects/cairn-gate-labs/lab\""
echo "  export CGL_PROFILE=\"cairn-gate-labs\""
echo
echo "Then 'source' your rc, or open a fresh shell."
echo
echo "Once that works, you can delete the embedded studio source from CGL:"
echo
echo "  cd \$CGL_LAB_ROOT"
echo "  git rm -r studio/bridge studio/lab_tui studio/lib"
echo "  git commit -m 'studio: extract harness to ~/projects/studio'"
echo
echo "(SPEC.md, BUILD_PLAN.md, README.md in CGL's studio/ stay — they're"
echo "lab-specific reflection on what was built.)"
