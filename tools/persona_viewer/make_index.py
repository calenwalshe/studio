"""make_index.py — scan tools/persona_runs/*/manifest.json and write runs.json.

Run after any persona_capture.py run, or on demand:
    studio/.venv/bin/python tools/persona_viewer/make_index.py

Writes tools/persona_viewer/runs.json — the index consumed by index.html.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

VIEWER_DIR = Path(__file__).resolve().parent
RUNS_DIR = VIEWER_DIR.parent / "persona_runs"
RUNS_JSON = VIEWER_DIR / "runs.json"


def main() -> None:
    if not RUNS_DIR.exists():
        print(f"No runs directory found at {RUNS_DIR}", file=sys.stderr)
        RUNS_JSON.write_text("[]", encoding="utf-8")
        return

    entries: list[dict] = []

    for manifest_path in sorted(RUNS_DIR.glob("*/manifest.json"), reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Warning: could not read {manifest_path}: {exc}", file=sys.stderr)
            continue

        run_id = manifest.get("run_id", manifest_path.parent.name)

        # Build relative PNG paths for the viewer (relative to runs.json location)
        steps_summary = []
        for step in manifest.get("steps", []):
            png_abs = Path(step.get("png_path", ""))
            try:
                png_rel = png_abs.relative_to(VIEWER_DIR)
            except ValueError:
                # Fall back to a path relative to the viewer using the run_id
                png_filename = png_abs.name
                png_rel = Path("..") / "persona_runs" / run_id / png_filename

            svg_abs = Path(step.get("svg_path", ""))
            try:
                svg_rel = svg_abs.relative_to(VIEWER_DIR)
            except ValueError:
                svg_filename = svg_abs.name
                svg_rel = Path("..") / "persona_runs" / run_id / svg_filename

            steps_summary.append({
                "step_num": step.get("step_num"),
                "png_path": str(png_rel).replace("\\", "/"),
                "svg_path": str(svg_rel).replace("\\", "/"),
                "decision": step.get("decision", {}),
                "screen_text": step.get("screen_text", ""),
            })

        # Duration
        started_at = manifest.get("started_at", "")
        ended_at = manifest.get("ended_at", "")

        # Compute manifest path relative to viewer dir, falling back to absolute
        try:
            manifest_rel = manifest_path.relative_to(VIEWER_DIR).as_posix()
        except ValueError:
            manifest_rel = str(manifest_path)

        entries.append({
            "run_id": run_id,
            "persona_slug": manifest.get("persona_slug", "unknown"),
            "goal": manifest.get("goal", ""),
            "started_at": started_at,
            "ended_at": ended_at,
            "final_verdict": manifest.get("final_verdict", ""),
            "findings": manifest.get("findings", []),
            "step_count": len(steps_summary),
            "steps": steps_summary,
            "manifest_path": manifest_rel,
        })

    RUNS_JSON.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"Wrote {len(entries)} run(s) to {RUNS_JSON}")


if __name__ == "__main__":
    main()
