"""make_index.py — scan tools/persona_runs/*/manifest.json and write runs.json.

Handles two manifest formats:
  - Classic persona runs: have a "steps" array with decision/screen_text.
  - Director persona runs: have an "exchanges" array with human_message/agent_response.

Run after any persona capture run, or on demand:
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


def _rel_path(abs_path_str: str, run_id: str, filename: str) -> str:
    """Return a path relative to the viewer dir, for use in HTML src= attrs."""
    if not abs_path_str:
        return ""
    abs_path = Path(abs_path_str)
    try:
        rel = abs_path.relative_to(VIEWER_DIR)
        return str(rel).replace("\\", "/")
    except ValueError:
        # Not relative to viewer dir — build from run_id + filename
        if filename:
            return f"../persona_runs/{run_id}/{filename}"
        return str(abs_path)


def _resolve_exchange_path(exchange: dict, run_id: str, key: str) -> str:
    """For director runs: the manifest stores only filenames (not absolute paths)."""
    val = exchange.get(key, "")
    if not val:
        return ""
    # If it looks like just a filename (no slashes), prepend the run rel-path
    if "/" not in val and "\\" not in val:
        return f"../persona_runs/{run_id}/{val}"
    # Otherwise treat as absolute and try to relativise
    return _rel_path(val, run_id, Path(val).name)


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
        started_at = manifest.get("started_at", "")
        ended_at = manifest.get("ended_at", "")

        try:
            manifest_rel = manifest_path.relative_to(VIEWER_DIR).as_posix()
        except ValueError:
            manifest_rel = str(manifest_path)

        # ------------------------------------------------------------------ #
        # Classic run: has "steps"                                             #
        # ------------------------------------------------------------------ #
        if "steps" in manifest:
            steps_summary = []
            for step in manifest.get("steps", []):
                png_rel = _rel_path(
                    step.get("png_path", ""),
                    run_id,
                    Path(step.get("png_path", "")).name,
                )
                svg_rel = _rel_path(
                    step.get("svg_path", ""),
                    run_id,
                    Path(step.get("svg_path", "")).name,
                )
                steps_summary.append({
                    "step_num": step.get("step_num"),
                    "png_path": png_rel,
                    "svg_path": svg_rel,
                    "decision": step.get("decision", {}),
                    "screen_text": step.get("screen_text", ""),
                })

            entries.append({
                "run_id": run_id,
                "run_type": "classic",
                "persona_slug": manifest.get("persona_slug", "unknown"),
                "goal": manifest.get("goal", ""),
                "scenario": "",
                "started_at": started_at,
                "ended_at": ended_at,
                "final_verdict": manifest.get("final_verdict", ""),
                "findings": manifest.get("findings", []),
                "step_count": len(steps_summary),
                "steps": steps_summary,
                "exchanges": [],
                "exchange_count": 0,
                "manifest_path": manifest_rel,
            })

        # ------------------------------------------------------------------ #
        # Director run: has "exchanges"                                        #
        # ------------------------------------------------------------------ #
        elif "exchanges" in manifest:
            exchanges_summary = []
            for ex in manifest.get("exchanges", []):
                exchanges_summary.append({
                    "exchange_num": ex.get("exchange_num"),
                    "before_svg": _resolve_exchange_path(ex, run_id, "before_svg"),
                    "before_png": _resolve_exchange_path(ex, run_id, "before_png"),
                    "human_message": ex.get("human_message", ""),
                    "agent_response": ex.get("agent_response", ""),
                    "agent_response_ms": ex.get("agent_response_ms", 0),
                    "after_svg": _resolve_exchange_path(ex, run_id, "after_svg"),
                    "after_png": _resolve_exchange_path(ex, run_id, "after_png"),
                })

            entries.append({
                "run_id": run_id,
                "run_type": "director",
                "persona_slug": manifest.get("persona_slug", "unknown"),
                "goal": "",
                "scenario": manifest.get("scenario", ""),
                "started_at": started_at,
                "ended_at": ended_at,
                "final_verdict": "",
                "findings": [],
                "step_count": 0,
                "steps": [],
                "exchanges": exchanges_summary,
                "exchange_count": len(exchanges_summary),
                "manifest_path": manifest_rel,
            })

        else:
            print(f"Warning: manifest {manifest_path} has neither 'steps' nor 'exchanges'", file=sys.stderr)

    RUNS_JSON.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"Wrote {len(entries)} run(s) to {RUNS_JSON}")


if __name__ == "__main__":
    main()
