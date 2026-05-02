"""Studio eval harness — runs YAML scenarios with rubrics, scores against
checkable assertions, publishes results to the persona viewer.

Usage:
    studio/.venv/bin/python tools/eval_harness.py tools/evals/scenarios/01-basic-triage.yaml

The harness re-uses tools/director_persona_capture.py's run_director_persona()
for the actual TUI driving.  It converts YAML scenario steps into the directive
format that function expects, then scores the captured responses against each
rubric item.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    rubric_id: str
    description: str
    passed: bool
    detail: str  # what was checked, actual vs expected


@dataclass
class EvalRunResult:
    scenario_name: str
    run_id: str
    persona: str
    started_at: str
    ended_at: str
    steps_executed: int
    rubric_results: list[CheckResult]
    overall_pass: bool
    score: float  # passed / total
    artifact_dir: Path


# ---------------------------------------------------------------------------
# Check registry
# ---------------------------------------------------------------------------

CHECK_IMPLEMENTATIONS: dict[str, Any] = {}


def register_check(name: str):
    def deco(fn):
        CHECK_IMPLEMENTATIONS[name] = fn
        return fn
    return deco


@register_check("response_line_count")
def check_response_line_count(check_spec: dict, run_state: dict) -> tuple[bool, str]:
    step_idx = check_spec["step"]
    response = run_state["responses"].get(step_idx, "")
    line_count = len(response.splitlines())
    if "max" in check_spec and line_count > check_spec["max"]:
        return False, f"line_count={line_count} > max={check_spec['max']}"
    if "min" in check_spec and line_count < check_spec["min"]:
        return False, f"line_count={line_count} < min={check_spec['min']}"
    return True, f"line_count={line_count} within bounds"


@register_check("response_contains")
def check_response_contains(check_spec: dict, run_state: dict) -> tuple[bool, str]:
    step_idx = check_spec["step"]
    response = run_state["responses"].get(step_idx, "")
    needle = check_spec["text"]
    if needle in response:
        return True, f"response contains {needle!r}"
    return False, f"response does NOT contain {needle!r}"


@register_check("response_not_contains")
def check_response_not_contains(check_spec: dict, run_state: dict) -> tuple[bool, str]:
    step_idx = check_spec["step"]
    response = run_state["responses"].get(step_idx, "")
    needle = check_spec["text"]
    if needle in response:
        return False, f"response unexpectedly contains {needle!r}"
    return True, f"response correctly omits {needle!r}"


@register_check("response_mentions_any")
def check_response_mentions_any(check_spec: dict, run_state: dict) -> tuple[bool, str]:
    step_idx = check_spec["step"]
    response = run_state["responses"].get(step_idx, "").lower()
    options = [o.lower() for o in check_spec["options"]]
    matched = [o for o in options if o in response]
    if matched:
        return True, f"matched: {matched}"
    return False, f"none of {options} appeared in response"


@register_check("file_exists")
def check_file_exists(check_spec: dict, run_state: dict) -> tuple[bool, str]:
    path_template = check_spec["path"]
    path_str = _resolve_template(path_template, run_state)
    p = Path(path_str)
    if p.exists():
        return True, f"exists: {p}"
    return False, f"missing: {p}"


@register_check("file_json_field")
def check_file_json_field(check_spec: dict, run_state: dict) -> tuple[bool, str]:
    path_str = _resolve_template(check_spec["path"], run_state)
    p = Path(path_str)
    if not p.exists():
        return False, f"missing file: {p}"
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        return False, f"failed to parse {p}: {e}"
    val = data.get(check_spec["field"])
    if "in" in check_spec:
        if val in check_spec["in"]:
            return True, f"{check_spec['field']}={val!r} in {check_spec['in']}"
        return False, f"{check_spec['field']}={val!r} not in {check_spec['in']}"
    if "equals" in check_spec:
        if val == check_spec["equals"]:
            return True, f"{check_spec['field']}={val!r} == expected"
        return False, f"{check_spec['field']}={val!r} != {check_spec['equals']!r}"
    return False, "no comparator (in / equals) in check"


# ---------------------------------------------------------------------------
# Template resolution
# ---------------------------------------------------------------------------


def _resolve_template(template: str, run_state: dict) -> str:
    """Resolve {var} placeholders from run_state['template_vars'].

    v0 supports: lab_root, first_lab, promoted_claw_id.
    Arc 3 will flesh out context resolution for action-driven scenarios.
    """
    vars_ = run_state.get("template_vars", {})
    try:
        return template.format(**vars_)
    except KeyError as e:
        # Return the template as-is so the check fails with a clear message.
        return template


# ---------------------------------------------------------------------------
# Scenario loading
# ---------------------------------------------------------------------------


def load_scenario(yaml_path) -> dict:
    """Load and return a scenario dict from a YAML file."""
    return yaml.safe_load(Path(yaml_path).read_text())


# ---------------------------------------------------------------------------
# Step conversion helpers
# ---------------------------------------------------------------------------


def _scenario_steps_to_directives(steps: list[dict]) -> list[dict]:
    """Convert scenario YAML step entries to the directive format that
    director_persona_capture.run_director_persona() expects."""
    directives: list[dict] = []
    for step in steps:
        if "chat" in step:
            directives.append({"type": "chat", "text": step["chat"]})
        elif "keypress" in step:
            kp = step["keypress"]
            directives.append({
                "type": "keypress",
                "key": kp["key"],
                "label": kp.get("label", ""),
            })
        elif "expand_lab" in step:
            el = step["expand_lab"]
            directives.append({
                "type": "expand_lab",
                "lab_id": el if isinstance(el, str) else el.get("lab_id", ""),
                "label": el.get("label", "") if isinstance(el, dict) else f"expand {el}",
            })
        elif "action" in step:
            # Map scenario action spec to capture driver action spec.
            # The scenario uses "type" for the action name; the capture driver
            # uses "name".  Other keys pass through unchanged.
            action_spec = dict(step["action"])
            action_name = action_spec.pop("type", "unknown")
            directives.append({
                "type": "action",
                "name": action_name,
                "label": action_spec.pop("label", action_name),
                **action_spec,
            })
        else:
            raise ValueError(f"unknown step shape: {step}")
    return directives


# ---------------------------------------------------------------------------
# Core run function
# ---------------------------------------------------------------------------


async def run_scenario(scenario: dict, output_root: Path) -> EvalRunResult:
    """Run a single scenario: execute steps, capture artifacts, score rubric.

    Delegates all TUI driving to director_persona_capture.run_director_persona().
    After the run, scores each rubric item against the captured run_state and
    augments the manifest with an 'eval' block for the viewer.
    """
    scenario_name = scenario["name"]
    persona_slug = f"eval-{scenario_name}"

    # Resolve lab_root relative to the harness root (studio-tui/)
    harness_root = Path(__file__).resolve().parents[1]
    lab_root_raw = scenario["lab_root"]
    # Strip tmp_copy_of(...) wrapper if present — Arc 3 will handle copying.
    # For now just extract the inner path and use it directly.
    tmp_copy_match = re.match(r"tmp_copy_of\((.+)\)", lab_root_raw)
    if tmp_copy_match:
        lab_root_raw = tmp_copy_match.group(1)
    lab_root = (harness_root / lab_root_raw).resolve()

    directives = _scenario_steps_to_directives(scenario.get("steps", []))

    # Import capture driver — add tools/ to path so it can find its siblings.
    tools_dir = Path(__file__).resolve().parent
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))

    # Set CGL_LAB_ROOT before the cockpit module is imported inside the driver.
    os.environ["CGL_LAB_ROOT"] = str(lab_root)

    from director_persona_capture import run_director_persona  # noqa: E402

    persona_result = await run_director_persona(
        persona_slug=persona_slug,
        directives=directives,
        scenario=scenario.get("description", ""),
        federation_root=lab_root,
        output_dir=output_root,
        verbose=False,
        question_timeout=scenario.get("timeout", 120),
    )

    run_id = persona_result["run_id"]
    artifact_dir = Path(persona_result["run_dir"])

    # Build response index: chat step index (among ALL steps) -> agent response text
    responses: dict[int, str] = {}
    for i, exch in enumerate(persona_result.get("exchanges", [])):
        if exch.get("step_type") == "chat":
            responses[i] = exch.get("agent_response", "")

    # Template vars for path resolution in rubric checks.
    # Arc 3 will populate first_lab / promoted_claw_id from action outcomes.
    template_vars: dict[str, str] = {
        "lab_root": str(lab_root),
        "first_lab": persona_result.get("first_lab", ""),
        "promoted_claw_id": persona_result.get("promoted_claw_id", ""),
    }

    run_state = {"responses": responses, "template_vars": template_vars}

    # Score rubric
    check_results: list[CheckResult] = []
    for rubric_item in scenario.get("rubric", []):
        check_spec = rubric_item["check"]
        check_type = check_spec["type"]
        impl = CHECK_IMPLEMENTATIONS.get(check_type)
        if impl is None:
            check_results.append(CheckResult(
                rubric_item["id"],
                rubric_item["description"],
                False,
                f"unknown check type: {check_type}",
            ))
            continue
        try:
            passed, detail = impl(check_spec, run_state)
        except Exception as e:
            passed, detail = False, f"check raised: {e}"
        check_results.append(CheckResult(
            rubric_item["id"],
            rubric_item["description"],
            passed,
            detail,
        ))

    overall_pass = all(r.passed for r in check_results)
    score = sum(1 for r in check_results if r.passed) / max(len(check_results), 1)

    result = EvalRunResult(
        scenario_name=scenario_name,
        run_id=run_id,
        persona=scenario.get("persona", "director"),
        started_at=persona_result.get("started_at", ""),
        ended_at=persona_result.get("ended_at", ""),
        steps_executed=len(persona_result.get("exchanges", [])),
        rubric_results=check_results,
        overall_pass=overall_pass,
        score=score,
        artifact_dir=artifact_dir,
    )

    # Augment the manifest with eval data so the viewer can render it.
    manifest_path = artifact_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    else:
        manifest = {}
    manifest["eval"] = {
        "scenario_name": scenario_name,
        "rubric_results": [
            {
                "id": r.rubric_id,
                "description": r.description,
                "passed": r.passed,
                "detail": r.detail,
            }
            for r in check_results
        ],
        "overall_pass": overall_pass,
        "score": score,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return result


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def print_eval_summary(result: EvalRunResult) -> None:
    """Pretty-print the eval result to stdout."""
    passed_count = sum(1 for r in result.rubric_results if r.passed)
    total = len(result.rubric_results)
    print(f"\n=== Eval: {result.scenario_name} ===")
    print(f"Run:     {result.run_id}")
    print(f"Score:   {int(result.score * 100)}% ({passed_count}/{total})")
    print(f"Overall: {'PASS' if result.overall_pass else 'FAIL'}")
    print()
    for r in result.rubric_results:
        marker = "[PASS]" if r.passed else "[FAIL]"
        print(f"  {marker} {r.rubric_id}")
        print(f"         {r.description}")
        print(f"         {r.detail}")
        print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


async def _async_main(scenario_path: Path, output_dir: Path) -> bool:
    scenario = load_scenario(scenario_path)
    result = await run_scenario(scenario, output_dir)
    print_eval_summary(result)
    return result.overall_pass


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Studio eval harness — run a YAML scenario and score its rubric."
    )
    parser.add_argument("scenario_path", type=Path, help="Path to scenario YAML file.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "persona_runs",
        help="Directory under which to create the run folder.",
    )
    args = parser.parse_args()

    passed = asyncio.run(_async_main(args.scenario_path, args.output_dir))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
