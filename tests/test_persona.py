"""tests/test_persona.py — LLM persona integration test for Studio Cockpit.

This test calls `claude -p` via subprocess and is SLOW (~30-60s per run).
Gate behind the `slow` marker:

    # Skip slow tests:
    studio/.venv/bin/pytest -m "not slow"

    # Run only slow tests:
    studio/.venv/bin/pytest -m slow

    # Run all (including slow):
    studio/.venv/bin/pytest
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
from pathlib import Path

import pytest

HARNESS_ROOT = Path(__file__).resolve().parents[1]

# Ensure studio and tools are importable
for _p in (str(HARNESS_ROOT / "studio"), str(HARNESS_ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture(scope="session")
def claude_available():
    """Skip persona tests if the claude CLI is not on PATH."""
    if shutil.which("claude") is None:
        pytest.skip("claude CLI not found on PATH — skipping persona tests")


@pytest.mark.slow
def test_persona_finds_review_candidates(claude_available):
    """Persona should navigate the cockpit and find hello-lab as a review candidate.

    This test calls the real claude CLI and takes ~30-60 seconds.
    """
    os.environ["CGL_LAB_ROOT"] = str(HARNESS_ROOT / "examples" / "hello-lab")

    from persona_driver import run_persona
    from lab_tui.cockpit import CockpitApp

    result = asyncio.run(run_persona(
        goal="Find all labs that need review. Report each lab id and its promotion recommendation.",
        app_class=CockpitApp,
        max_steps=8,
    ))

    # The persona should accomplish the goal in a few steps
    assert result["steps"] <= 8, f"Persona used too many steps: {result['steps']}"

    findings = result["findings"]

    # The persona should find hello-lab in its findings
    found_labs = []
    for f in findings:
        if isinstance(f, dict):
            for v in f.values():
                if "hello-lab" in str(v):
                    found_labs.append(f)
                    break

    assert found_labs, (
        f"Persona failed to find hello-lab. "
        f"Verdict: {result['verdict']}. "
        f"Findings: {findings}"
    )
