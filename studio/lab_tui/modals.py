"""modals.py — Director action modals for the Studio Cockpit.

Three ModalScreen classes:
  - ConfirmModal      generic Y/N confirmation
  - SpawnClawModal    form to spawn a dry-run claw (orientation + role dropdowns)
  - NewLabModal       form to create a new lab (slug, title, kind, objective)
  - ClawViewerModal   full-text viewer for a claw's result.md
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Tuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from lab_tui.loaders import LabSummary


# ---------------------------------------------------------------------------
# ConfirmModal
# ---------------------------------------------------------------------------

class ConfirmModal(ModalScreen[bool]):
    """Generic Y/N confirmation modal.

    Returns True on confirm (Y), False on cancel (N or Esc).
    """

    DEFAULT_CSS = """
    ConfirmModal {
        align: center middle;
    }

    ConfirmModal > Vertical {
        width: 60;
        height: auto;
        border: round #555577;
        background: #1a1a2e;
        padding: 1 2;
    }

    ConfirmModal #confirm-title {
        text-style: bold;
        color: #cdd6f4;
        margin-bottom: 1;
    }

    ConfirmModal #confirm-message {
        color: #a6adc8;
        margin-bottom: 1;
    }

    ConfirmModal #confirm-hint {
        color: #585b70;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("y", "confirm", "Confirm", show=False),
        Binding("n", "cancel", "Cancel", show=False),
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, title: str, message: str, on_confirm: Callable[[], None] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._message = message
        self._on_confirm = on_confirm

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._title, id="confirm-title")
            yield Static(self._message, id="confirm-message")
            yield Static("Y to confirm    N or Esc to cancel", id="confirm-hint")

    def action_confirm(self) -> None:
        if self._on_confirm is not None:
            self._on_confirm()
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


# ---------------------------------------------------------------------------
# SpawnClawModal
# ---------------------------------------------------------------------------

class SpawnClawModal(ModalScreen[Optional[Tuple[str, str]]]):
    """Form modal: choose orientation + role to spawn a dry-run claw.

    Returns (orientation_id, role) on spawn, or None on cancel.
    """

    DEFAULT_CSS = """
    SpawnClawModal {
        align: center middle;
    }

    SpawnClawModal > Vertical {
        width: 70;
        height: auto;
        border: round #555577;
        background: #1a1a2e;
        padding: 1 2;
    }

    SpawnClawModal #spawn-title {
        text-style: bold;
        color: #cdd6f4;
        margin-bottom: 1;
    }

    SpawnClawModal Label {
        color: #a6adc8;
        margin-top: 1;
    }

    SpawnClawModal Select {
        margin-bottom: 1;
    }

    SpawnClawModal #spawn-hint {
        color: #585b70;
        margin-top: 1;
    }

    SpawnClawModal Horizontal {
        height: auto;
        margin-top: 1;
    }

    SpawnClawModal Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, lab_summary: LabSummary, **kwargs) -> None:
        super().__init__(**kwargs)
        self._summary = lab_summary

    def compose(self) -> ComposeResult:
        orientations = self._summary.orientations
        orient_options = []
        for o in orientations:
            obj_short = o.objective[:40] + "..." if len(o.objective) > 40 else o.objective
            orient_options.append((f"{o.id} — {obj_short}", o.id))

        # Build role options from the first orientation's roles list, or a default set
        role_ids: list[str] = []
        if orientations and hasattr(orientations[0], "roles"):
            role_ids = list(orientations[0].roles)
        if not role_ids:
            role_ids = ["scout", "researcher", "builder", "reviewer", "operator", "curator"]

        role_options = [(r, r) for r in role_ids]

        with Vertical():
            yield Static(f"Spawn claw — {self._summary.lab_id}", id="spawn-title")
            yield Label("Orientation")
            if orient_options:
                yield Select(orient_options, id="spawn-orientation", allow_blank=False)
            else:
                yield Static("(no orientations defined)", id="spawn-no-orient")
            yield Label("Role")
            yield Select(role_options, id="spawn-role", allow_blank=False)
            yield Static("Tab to navigate    Enter to spawn    Esc to cancel", id="spawn-hint")
            with Horizontal():
                yield Button("Spawn", id="spawn-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return

        if event.button.id == "spawn-btn":
            self._do_spawn()

    def _do_spawn(self) -> None:
        # Get orientation
        try:
            orient_widget = self.query_one("#spawn-orientation", Select)
            orientation_id = str(orient_widget.value)
        except Exception:
            self.dismiss(None)
            return

        # Get role
        try:
            role_widget = self.query_one("#spawn-role", Select)
            role = str(role_widget.value)
        except Exception:
            self.dismiss(None)
            return

        if orientation_id and role:
            self.dismiss((orientation_id, role))
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# NewLabModal
# ---------------------------------------------------------------------------

class NewLabModal(ModalScreen[Optional[dict]]):
    """Form modal for creating a new lab.

    Returns dict with {slug, title, kind, objective} on create, or None on cancel.
    """

    DEFAULT_CSS = """
    NewLabModal {
        align: center middle;
    }

    NewLabModal > Vertical {
        width: 70;
        height: auto;
        border: round #555577;
        background: #1a1a2e;
        padding: 1 2;
    }

    NewLabModal #newlab-title {
        text-style: bold;
        color: #cdd6f4;
        margin-bottom: 1;
    }

    NewLabModal Label {
        color: #a6adc8;
        margin-top: 1;
    }

    NewLabModal Input {
        margin-bottom: 0;
    }

    NewLabModal #newlab-error {
        color: #f38ba8;
        margin-top: 1;
    }

    NewLabModal Horizontal {
        height: auto;
        margin-top: 1;
    }

    NewLabModal Button {
        margin-right: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    _KIND_OPTIONS = [
        ("investigation", "investigation"),
        ("surface", "surface"),
        ("systems", "systems"),
    ]

    def __init__(self, federation_root: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self._federation_root = federation_root
        self._error_msg = ""

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("Create new lab", id="newlab-title")
            yield Label("Slug (kebab-case, e.g. my-new-lab)")
            yield Input(placeholder="my-new-lab", id="newlab-slug")
            yield Label("Title")
            yield Input(placeholder="My New Lab", id="newlab-title-input")
            yield Label("Kind")
            yield Select(self._KIND_OPTIONS, id="newlab-kind", allow_blank=False)
            yield Label("Objective")
            yield Input(placeholder="What should this lab investigate?", id="newlab-objective")
            yield Static("", id="newlab-error")
            with Horizontal():
                yield Button("Create", id="create-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel-btn":
            self.dismiss(None)
            return
        if event.button.id == "create-btn":
            self._do_create()

    def _do_create(self) -> None:
        import re
        slug_widget = self.query_one("#newlab-slug", Input)
        title_widget = self.query_one("#newlab-title-input", Input)
        kind_widget = self.query_one("#newlab-kind", Select)
        objective_widget = self.query_one("#newlab-objective", Input)
        error_widget = self.query_one("#newlab-error", Static)

        slug = slug_widget.value.strip()
        title = title_widget.value.strip()
        objective = objective_widget.value.strip()

        try:
            kind = str(kind_widget.value)
        except Exception:
            kind = ""

        # Validate slug
        if not re.match(r"^[a-z][a-z0-9-]*$", slug):
            error_widget.update("Slug must be kebab-case starting with a letter (e.g. my-lab)")
            return

        # Validate collision
        if (self._federation_root / slug).exists():
            error_widget.update(f"Lab already exists: {slug}")
            return

        if not title:
            error_widget.update("Title is required")
            return

        if not objective:
            error_widget.update("Objective is required")
            return

        if kind not in ("investigation", "surface", "systems"):
            error_widget.update("Please select a kind")
            return

        self.dismiss({"slug": slug, "title": title, "kind": kind, "objective": objective})

    def action_cancel(self) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# ClawViewerModal
# ---------------------------------------------------------------------------

class ClawViewerModal(ModalScreen[None]):
    """Full-text viewer for a claw's result.md. Esc to close."""

    DEFAULT_CSS = """
    ClawViewerModal {
        align: center middle;
    }

    ClawViewerModal > Vertical {
        width: 90%;
        height: 80%;
        border: round #555577;
        background: #1a1a2e;
        padding: 1 2;
    }

    ClawViewerModal #viewer-title {
        text-style: bold;
        color: #cdd6f4;
        margin-bottom: 1;
    }

    ClawViewerModal #viewer-content {
        height: 1fr;
        color: #cdd6f4;
        overflow-y: auto;
    }

    ClawViewerModal #viewer-hint {
        color: #585b70;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "Close", show=False),
        Binding("q", "close", "Close", show=False),
    ]

    def __init__(self, claw_dir: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self._claw_dir = claw_dir
        result_file = claw_dir / "result.md"
        self._content = result_file.read_text(encoding="utf-8") if result_file.exists() else "(no result.md found)"

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Result — {self._claw_dir.name}", id="viewer-title")
            yield Static(self._content, id="viewer-content", markup=False)
            yield Static("Esc or q to close", id="viewer-hint")

    def action_close(self) -> None:
        self.dismiss(None)
