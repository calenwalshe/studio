"""tests/test_cockpit_snapshot.py — visual regression tests for the Studio Cockpit.

Uses pytest-textual-snapshot (snap_compare fixture from syrupy + Textual).

Generate baselines:
    CGL_LAB_ROOT=examples/hello-lab studio/.venv/bin/pytest tests/test_cockpit_snapshot.py --snapshot-update

Verify baselines match:
    CGL_LAB_ROOT=examples/hello-lab studio/.venv/bin/pytest tests/test_cockpit_snapshot.py -v

Note: We subclass CockpitApp with show_clock=False so the SVG baseline is
stable across runs (the live clock in the header would change every second
and break the comparison).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input

# Ensure the studio package directory is on sys.path so lab_tui is importable
HARNESS_ROOT = Path(__file__).resolve().parents[1]
_STUDIO_PATH = str(HARNESS_ROOT / "studio")
if _STUDIO_PATH not in sys.path:
    sys.path.insert(0, _STUDIO_PATH)

HELLO_LAB = HARNESS_ROOT / "examples" / "hello-lab"

# Set env before importing cockpit (module-level _resolve_federation_root runs on import)
os.environ["CGL_LAB_ROOT"] = str(HELLO_LAB)

from lab_tui.cockpit import (  # noqa: E402
    CockpitApp,
    DirectorChat,
    LabHeaderStrip,
    LabList,
)


class StableCockpitApp(CockpitApp):
    """CockpitApp variant with show_clock=False for deterministic SVG snapshots."""

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal(id="main-body"):
            with Vertical(id="lab-panel"):
                yield LabHeaderStrip([], HELLO_LAB, id="lab-header-strip")
                yield LabList([], id="lab-list")
            yield DirectorChat(HELLO_LAB, id="chat-pane")
        yield Footer()


def test_cockpit_federation_home(snap_compare):
    """Snapshot of the cockpit at rest with hello-lab loaded."""
    assert snap_compare(StableCockpitApp(), terminal_size=(120, 40))


def test_cockpit_after_enter(snap_compare):
    """Snapshot after pressing enter — accordion row should expand."""
    async def press_enter(pilot):
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    assert snap_compare(StableCockpitApp(), terminal_size=(120, 40), run_before=press_enter)
