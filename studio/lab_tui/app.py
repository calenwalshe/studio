"""Lab TUI — per-lab dashboard.

Layout (per studio/tui-architecture.mmd):
    ┌─ header: lab title · kind · rot · cumulative$ ────────────┐
    │ ┌─ Lab card ────────────────────────────────────────────┐ │
    │ │ slug, kind, status, last touched, path, description   │ │
    │ └───────────────────────────────────────────────────────┘ │
    │ ┌─ Recent ledger (this lab) ─────────────────────────────┐ │
    │ │ ts  skill  model  $0.0123                              │ │
    │ └────────────────────────────────────────────────────────┘ │
    │ ┌─ Contracts ──────────┐ ┌─ Artifacts ────────────────────┐│
    │ │ v1: question         │ │ ls of lab.path (top entries)   ││
    │ └──────────────────────┘ └────────────────────────────────┘│
    └─ b back · ! shell · k claude · g git log · r refresh · q ─┘
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

LAB_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LAB_ROOT / "studio"))

from textual.app import App, ComposeResult  # noqa: E402
from textual.binding import Binding  # noqa: E402
from textual.containers import Horizontal, Vertical  # noqa: E402
from textual.widgets import DataTable, Footer, Header, Static  # noqa: E402

from lib import state_reader as sr  # noqa: E402


ROT_STYLE = {"green": "green", "yellow": "yellow", "red": "red"}


class LabCard(Static):
    def __init__(self, slug: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.slug = slug

    def on_mount(self) -> None:
        self.border_title = "Lab"
        self.refresh_data()

    def refresh_data(self) -> None:
        lab = sr.get_lab(self.slug)
        if lab is None:
            self.update(f"[red]no lab '{self.slug}'[/red]")
            return
        rot = ROT_STYLE.get(lab.rot_color, "white")
        days = lab.days_since_touch
        days_str = f"{days}d ago" if days is not None else "never"
        path_str = str(lab.path) if lab.path else "[dim](no path)[/dim]"
        desc = lab.description or "[dim](no description)[/dim]"
        self.update(
            f"[bold]{lab.slug}[/bold]  [dim]·[/dim]  "
            f"{lab.kind}  [dim]·[/dim]  "
            f"[{rot}]●[/{rot}] {lab.status}  [dim]·[/dim]  "
            f"touched {days_str}\n"
            f"[dim]{path_str}[/dim]\n\n"
            f"{desc}"
        )


class LedgerPane(DataTable):
    def __init__(self, slug: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.slug = slug

    def on_mount(self) -> None:
        self.border_title = "Recent ledger"
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("when", "skill", "model", "$")
        self.refresh_data()

    def refresh_data(self) -> None:
        self.clear()
        rows = sr.lab_ledger(self.slug, limit=15)
        for r in rows:
            self.add_row(
                r.timestamp.strftime("%m-%d %H:%M"),
                r.skill,
                r.model,
                f"{r.cost_usd:.4f}",
            )


class ContractsPane(Static):
    def __init__(self, slug: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.slug = slug

    def on_mount(self) -> None:
        self.border_title = "Contracts"
        self.refresh_data()

    def refresh_data(self) -> None:
        contracts = sr.list_contracts(self.slug)
        if not contracts:
            self.update("[dim](no contracts)[/dim]")
            return
        lines = []
        for c in contracts:
            lines.append(
                f"[bold]v{c.version}[/bold]  ${c.budget_dollars:.0f} · "
                f"{c.cycle_cap}c\n  [dim]{c.question[:80]}[/dim]"
            )
        self.update("\n\n".join(lines))


class ArtifactsPane(Static):
    def __init__(self, slug: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.slug = slug

    def on_mount(self) -> None:
        self.border_title = "Artifacts"
        self.refresh_data()

    def refresh_data(self) -> None:
        lab = sr.get_lab(self.slug)
        if not lab or not lab.path or not lab.path.exists():
            self.update("[dim](no artifact root)[/dim]")
            return
        try:
            entries = sorted(lab.path.iterdir(), key=lambda p: p.name)[:18]
        except PermissionError:
            self.update("[red]permission denied[/red]")
            return
        lines = []
        for e in entries:
            marker = "[blue]/[/blue]" if e.is_dir() else " "
            lines.append(f"{marker} {e.name}")
        self.update("\n".join(lines))


class LabApp(App):
    CSS = """
    Screen { background: #1c1917; }

    #card { height: 6; }
    #ledger { height: 1fr; }
    #row-bot { height: 40%; }

    LabCard, LedgerPane, ContractsPane, ArtifactsPane {
        border: round #c5b08a;
        padding: 1 2;
        background: #292524;
        color: #e7e5e4;
    }
    ContractsPane { width: 50%; }
    ArtifactsPane { width: 50%; }
    """

    BINDINGS = [
        Binding("b,escape", "back", "Back to bridge"),
        Binding("r", "refresh", "Refresh"),
        Binding("exclamation_mark", "shell", "Shell"),
        Binding("k", "claude", "Claude"),
        Binding("g", "git_log", "Git log"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, slug: str) -> None:
        super().__init__()
        self.slug = slug
        self.lab = sr.get_lab(slug)
        self.title = f"cairn-gate-labs · lab/{slug}"

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Vertical():
            yield LabCard(self.slug, id="card")
            yield LedgerPane(self.slug, id="ledger")
            with Horizontal(id="row-bot"):
                yield ContractsPane(self.slug, id="contracts")
                yield ArtifactsPane(self.slug, id="artifacts")
        yield Footer()

    def on_mount(self) -> None:
        if self.lab is None:
            self.notify(f"unknown lab: {self.slug}", severity="error")
            self.set_timer(2.0, self.exit)
            return
        rows = sr.lab_ledger(self.slug, limit=200)
        total = sum(r.cost_usd for r in rows)
        self.sub_title = f"{len(rows)} events · ${total:.2f} cumulative"

    def action_back(self) -> None:
        self.exit()

    def action_refresh(self) -> None:
        for sel in ("#card", "#ledger", "#contracts", "#artifacts"):
            try:
                self.query_one(sel).refresh_data()
            except Exception:
                pass
        self.notify("refreshed", timeout=1.5)

    def _lab_cwd(self) -> str:
        if self.lab and self.lab.path and self.lab.path.exists():
            return str(self.lab.path)
        return str(sr.LAB_ROOT)

    def action_shell(self) -> None:
        cwd = self._lab_cwd()
        with self.suspend():
            print(f"\n[lab/{self.slug} shell — type 'exit' to return to TUI]\n")
            shell = os.environ.get("SHELL", "/bin/bash")
            subprocess.run([shell], cwd=cwd)

    def action_claude(self) -> None:
        cwd = self._lab_cwd()
        with self.suspend():
            print(f"\n[lab/{self.slug} claude session — exit Claude to return]\n")
            subprocess.run(["claude"], cwd=cwd)

    def action_git_log(self) -> None:
        cwd = self._lab_cwd()
        with self.suspend():
            subprocess.run(
                ["git", "log", "--oneline", "-30"],
                cwd=cwd,
            )
            input("\n[enter to return]")


def main() -> None:
    p = argparse.ArgumentParser(description="Lab TUI")
    p.add_argument("slug", help="Lab slug (see cgl-bridge for the list)")
    args = p.parse_args()
    LabApp(args.slug).run()


if __name__ == "__main__":
    main()
