"""cockpit.py — Studio Cockpit: federation home screen.

Run via:
    CGL_LAB_ROOT=examples/hello-lab bin/cgl-cockpit

Or directly:
    studio/.venv/bin/python studio/lab_tui/cockpit.py examples/hello-lab

Reads federation root from CGL_LAB_ROOT env var (matching harness convention).
Falls back to argv[1] if env not set. Errors clearly if neither is provided.

Layout:
    Header  — "Studio Cockpit — <federation_root_basename>"
    Body    — DataTable (left 70%) | Director Queue (right 30%)
    Footer  — keybinding hints: q quit, r refresh, enter details
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Static

# ---------------------------------------------------------------------------
# Resolve federation root before any TUI import side-effects
# ---------------------------------------------------------------------------

def _resolve_federation_root() -> Path:
    """Return federation root from CGL_LAB_ROOT env or argv[1]."""
    env_val = os.environ.get("CGL_LAB_ROOT", "").strip()
    if env_val:
        return Path(env_val).expanduser().resolve()
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).expanduser().resolve()
    print(
        "error: federation root not set.\n"
        "  Set CGL_LAB_ROOT=<path> or pass the path as the first argument.\n"
        "  Example: CGL_LAB_ROOT=examples/hello-lab bin/cgl-cockpit",
        file=sys.stderr,
    )
    sys.exit(1)


FEDERATION_ROOT = _resolve_federation_root()

# ---------------------------------------------------------------------------
# Import loaders (must come after sys.path is set via _studio_orient bootstrap
# inside loaders.py)
# ---------------------------------------------------------------------------

_HARNESS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_HARNESS_ROOT / "studio"))

from lab_tui.loaders import LabSummary, discover_labs  # noqa: E402


# ---------------------------------------------------------------------------
# Status symbol table
# ---------------------------------------------------------------------------

STATUS_SYMBOL = {
    "active":       "●",
    "idle":         "◐",
    "needs_review": "!",
    "stale":        "○",
    "error":        "×",
    "blocked":      "#",  # reserved
}


def _symbol(status: str) -> str:
    return STATUS_SYMBOL.get(status, "?")


def _orientation_summary(summary: LabSummary) -> str:
    if not summary.orientations:
        return "(no orientation)"
    obj = summary.orientations[0].objective
    return obj[:50] + "..." if len(obj) > 50 else obj


# ---------------------------------------------------------------------------
# Director Queue pane
# ---------------------------------------------------------------------------

class DirectorQueuePane(Static):
    """Right-side informational pane listing promotion candidates."""

    DEFAULT_CSS = """
    DirectorQueuePane {
        width: 1fr;
        border: round #888888;
        padding: 1 2;
        background: #1e1e2e;
        color: #cdd6f4;
        height: 100%;
    }
    """

    def __init__(self, summaries: list[LabSummary], **kwargs) -> None:
        super().__init__(**kwargs)
        self._summaries = summaries

    def on_mount(self) -> None:
        self.border_title = "Director Queue"
        self._render_queue()

    def _render_queue(self) -> None:
        lines: list[str] = []
        _NO_REVIEW = frozenset({"abandon", "dry_run"})
        for lab in self._summaries:
            for bundle in lab.bundles:
                rec = bundle.meta.get("promotion_recommendation", "abandon")
                if rec not in _NO_REVIEW:
                    lines.append(
                        f"{lab.lab_id}: {bundle.bundle_id}: {rec}"
                    )
        if lines:
            self.update("\n".join(lines))
        else:
            self.update("[dim](no bundles pending review)[/dim]")

    def refresh_queue(self, summaries: list[LabSummary]) -> None:
        self._summaries = summaries
        self._render_queue()


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

class CockpitApp(App):
    """Studio Cockpit — federation home screen."""

    CSS = """
    Screen { background: #1a1a2e; }

    #main-body {
        height: 1fr;
    }

    #lab-table {
        width: 3fr;
        border: round #888888;
        background: #16213e;
        color: #e2e2e2;
        height: 100%;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "show_details", "Details"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._federation_root = FEDERATION_ROOT
        self._summaries: list[LabSummary] = []

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-body"):
            yield DataTable(id="lab-table", cursor_type="row", zebra_stripes=True)
            yield DirectorQueuePane([], id="queue-pane")
        yield Footer()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self.title = f"Studio Cockpit — {self._federation_root.name}"
        self._build_table()
        self._load_data()

    def _build_table(self) -> None:
        table: DataTable = self.query_one("#lab-table", DataTable)
        table.add_columns(
            "St",        # status symbol
            "Lab ID",
            "Kind",
            "Orientation (current)",
            "Claws",
            "Promo",
        )

    def _load_data(self) -> None:
        self._summaries = discover_labs(self._federation_root)
        self._populate_table()
        queue: DirectorQueuePane = self.query_one("#queue-pane", DirectorQueuePane)
        queue.refresh_queue(self._summaries)

        count = len(self._summaries)
        self.sub_title = (
            f"{count} lab{'s' if count != 1 else ''} — "
            f"{self._federation_root}"
        )

    def _populate_table(self) -> None:
        table: DataTable = self.query_one("#lab-table", DataTable)
        table.clear()
        for lab in self._summaries:
            table.add_row(
                _symbol(lab.status),
                lab.lab_id,
                lab.kind,
                _orientation_summary(lab),
                str(len(lab.bundles)),
                str(lab.promotion_candidates),
            )

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        self._load_data()
        self.notify("Refreshed", timeout=1.5)

    def action_show_details(self) -> None:
        table: DataTable = self.query_one("#lab-table", DataTable)
        if table.cursor_row is not None and self._summaries:
            idx = table.cursor_row
            if 0 <= idx < len(self._summaries):
                lab = self._summaries[idx]
                self.log(
                    f"Lab detail — id={lab.lab_id} status={lab.status} "
                    f"reason={lab.status_reason} "
                    f"bundles={len(lab.bundles)} "
                    f"promo_candidates={lab.promotion_candidates}"
                )
                self.notify(
                    f"{lab.lab_id}: {lab.status_reason}",
                    title=lab.title,
                    timeout=4,
                )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    CockpitApp().run()


if __name__ == "__main__":
    main()
