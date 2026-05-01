"""Bridge TUI — top-level director console.

Layout (per studio/tui-architecture.mmd):
    ┌─ header (cumulative spend today / all-time) ──────────────┐
    │ ┌─ Labs ───────────┐ ┌─ Bellclaw queue ──────────────────┐ │
    │ │ 1  studio  green │ │ (placeholder until bellclaw built)│ │
    │ │ 2  advisory  yel │ │                                   │ │
    │ │ ...              │ │                                   │ │
    │ └──────────────────┘ └───────────────────────────────────┘ │
    │ ┌─ Recent ledger ─────────────────────────────────────────┐ │
    │ │ ts  lab  skill  model  $0.0123                          │ │
    │ └─────────────────────────────────────────────────────────┘ │
    │ ┌─ Spine ─────────────────────────────────────────────────┐ │
    │ │ claws/  plays/  capabilities/  voice/                   │ │
    │ └─────────────────────────────────────────────────────────┘ │
    └─ footer: 1-9 enter lab · q queue · l ledger · r refresh ─┘

Read-only. Mutations go through bin/cgl-* primitives, not the TUI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# State paths — resolved via lib._env (which honours $CGL_LAB_ROOT, $CGL_PROFILE)
# Imported below after the sys.path is set up.
PANES_FILE: Path
SUPERVISORS_FILE: Path


def relative_time(ts: str | None) -> str:
    """Convert ISO 8601 timestamp to short relative form like '4m', '2h', '3d'."""
    if not ts:
        return ""
    try:
        # Normalize Z suffix to +00:00 for fromisoformat
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60}m"
        if secs < 86400:
            return f"{secs // 3600}h"
        return f"{secs // 86400}d"
    except Exception:
        return ""


def relative_from_claw_ts(claw_ts: str) -> str:
    """Claw timestamps are 'YYYYMMDD-HHMMSS' (local time)."""
    if not claw_ts or len(claw_ts) < 15:
        return ""
    try:
        dt = datetime.strptime(claw_ts, "%Y%m%d-%H%M%S")
        dt = dt.astimezone()
        delta = datetime.now().astimezone() - dt
        secs = int(delta.total_seconds())
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60}m"
        if secs < 86400:
            return f"{secs // 3600}h"
        return f"{secs // 86400}d"
    except Exception:
        return ""


def _iso_from_lastmod(http_date: str | None) -> str | None:
    """Convert an HTTP Last-Modified date to ISO 8601 for relative_time()."""
    if not http_date:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(http_date).isoformat()
    except Exception:
        return None


def _short_ago(ago: str) -> str:
    """Compress 'N units ago' from git's --pretty=%ar into '5m', '2h', '3d'."""
    if not ago:
        return ""
    parts = ago.split()
    if len(parts) < 2:
        return ago[:6]
    n = parts[0]
    unit = parts[1].lower()
    if unit.startswith("second") or unit == "now":
        return f"{n}s"
    if unit.startswith("minute"):
        return f"{n}m"
    if unit.startswith("hour"):
        return f"{n}h"
    if unit.startswith("day"):
        return f"{n}d"
    if unit.startswith("week"):
        return f"{n}w"
    if unit.startswith("month"):
        return f"{n}mo"
    if unit.startswith("year"):
        return f"{n}y"
    return ago[:6]

# Make studio/lib importable when run as a module
_HARNESS_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_HARNESS_ROOT / "studio"))

from textual.app import App, ComposeResult  # noqa: E402
from textual.binding import Binding  # noqa: E402
from textual.containers import Horizontal, Vertical, VerticalScroll  # noqa: E402
from textual.widgets import DataTable, Footer, Header, Input, RichLog, Select, Static  # noqa: E402

from lib import _env  # noqa: E402
from lib import state_reader as sr  # noqa: E402
from lib import focus_core  # noqa: E402

PANES_FILE = _env.STATE_DIR / "panes.json"
SUPERVISORS_FILE = _env.STATE_DIR / "supervisors.json"


ROT_STYLE = {
    "green": "green",
    "yellow": "yellow",
    "red": "red",
}


class LabsPane(Static, can_focus=True):
    """Lab picker — numbered, color-coded by rot.

    Tracks two indices:
      - cursor_idx: the previewed lab (moved by [ / ])
      - active_idx: the currently-running supervisor lab
    """

    BINDINGS = [
        Binding("up", "cursor_up", show=False),
        Binding("k", "cursor_up", show=False),
        Binding("down", "cursor_down", show=False),
        Binding("j", "cursor_down", show=False),
        Binding("enter", "activate", show=False),
    ]

    cursor_idx: int = 0
    active_idx: int | None = None

    def action_cursor_up(self) -> None:
        self.app.action_move_cursor(-1)

    def action_cursor_down(self) -> None:
        self.app.action_move_cursor(1)

    def action_activate(self) -> None:
        self.app.action_activate_cursor()

    def on_mount(self) -> None:
        self.border_title = "Labs"
        self.refresh_data()

    def set_cursor(self, idx: int, max_idx: int) -> None:
        if max_idx <= 0:
            return
        self.cursor_idx = idx % max_idx
        self.refresh_data()

    def set_active(self, idx: int | None) -> None:
        self.active_idx = idx
        self.refresh_data()

    def refresh_data(self) -> None:
        labs = sr.list_labs()
        if not labs:
            self.update("[dim]no labs found[/dim]")
            return
        lines = []
        for i, lab in enumerate(labs[:9], start=1):
            color = ROT_STYLE.get(lab.rot_color, "white")
            days = lab.days_since_touch
            days_str = f"{days}d" if days is not None else " ·"
            zero_idx = i - 1
            if zero_idx == self.cursor_idx and zero_idx == self.active_idx:
                cursor_mark = "[bold #c5b08a]▶[/bold #c5b08a]"
            elif zero_idx == self.cursor_idx:
                cursor_mark = "[bold #c5b08a]▷[/bold #c5b08a]"
            elif zero_idx == self.active_idx:
                cursor_mark = "[bold #00ff66]●[/bold #00ff66]"
            else:
                cursor_mark = " "
            lines.append(
                f"{cursor_mark} [bold]{i}[/bold]  "
                f"[{color}]●[/{color}] "
                f"{lab.slug:<14} "
                f"[dim]{lab.kind:<14}[/dim] "
                f"[dim]{days_str:>4}[/dim]"
            )
        self.update("\n".join(lines))


class LabFormPane(Vertical):
    """Form for creating a new lab.

    Replaces the LabsPane temporarily. Tab-cycle through fields, Enter
    submits, Esc cancels. Calls cgl-labs new on submit.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Static("[bold]New lab[/bold]\n\n"
                     "[dim]Tab to next field · Enter to submit · Esc to cancel[/dim]",
                     id="form-header")
        yield Static("kind:", classes="form-label")
        yield Select(
            [(k, k) for k in ("surface", "investigation", "systems")],
            id="form-kind", value="surface", allow_blank=False,
        )
        yield Static("slug:", classes="form-label")
        yield Input(placeholder="lowercase-with-hyphens", id="form-slug")
        yield Static("title (optional):", classes="form-label")
        yield Input(placeholder="Display title", id="form-title")
        yield Static("description (optional):", classes="form-label")
        yield Input(placeholder="One-line summary", id="form-desc")
        yield Static("", id="form-status")

    def on_mount(self) -> None:
        self.border_title = "New lab"

    def reset_fields(self) -> None:
        try:
            self.query_one("#form-slug", Input).value = ""
            self.query_one("#form-title", Input).value = ""
            self.query_one("#form-desc", Input).value = ""
            self.query_one("#form-status", Static).update("")
        except Exception:
            pass

    def on_input_submitted(self, event) -> None:
        # Enter on any field submits the form
        self.action_submit()

    def action_cancel(self) -> None:
        self.app.action_close_form()

    def action_submit(self) -> None:
        try:
            kind = self.query_one("#form-kind", Select).value
            slug = self.query_one("#form-slug", Input).value.strip()
            title = self.query_one("#form-title", Input).value.strip()
            desc = self.query_one("#form-desc", Input).value.strip()
            status = self.query_one("#form-status", Static)
        except Exception:
            return
        if not slug:
            status.update("[red]slug required[/red]")
            return
        cmd = ["cgl-labs", "new", kind, slug]
        if title:
            cmd += ["--title", title]
        if desc:
            cmd += ["--desc", desc]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        except Exception as e:
            status.update(f"[red]error: {e}[/red]")
            return
        if r.returncode != 0:
            err = (r.stderr or r.stdout)[:120].strip()
            status.update(f"[red]{err}[/red]")
            return
        full = f"{kind}/{slug}"
        self.app.notify(f"created {full}", timeout=3)
        self.reset_fields()
        self.app.action_close_form()


class FocusPane(Vertical):
    """Live HUD for the active lab.

    Top: Haiku-distilled rollup (calm).
    Bottom: actions DataTable — selectable rows, kind-tagged for action keys.

    When the table has focus:
        ↑/↓ or j/k — navigate
        Enter — open the row
        m — merge (claw, status=done)
        a — abandon (claw)
        t — tail log (claw)
    """

    BINDINGS = [
        Binding("m", "row_merge", "Merge", show=False),
        Binding("a", "row_abandon", "Abandon", show=False),
        Binding("t", "row_tail", "Tail", show=False),
        Binding("e", "row_expand", "Expand", show=False),
        Binding("enter", "open_row", "Open", show=False),
    ]

    # row_key -> {kind, id, slug}
    _row_meta: dict
    # "lab" or "federation"
    _view_mode: str
    # Last rendered rollup string (kept while a fresh one is computing)
    _last_rollup: str
    # Hash of the structured data the last rollup was generated from
    _last_rollup_hash: str
    # Slug the last rollup was for (so a switch invalidates)
    _last_rollup_slug: str
    # Are we currently running a Haiku rollup worker?
    _rollup_in_flight: bool
    # Track the slug + last seen event ts so we only append new events
    _events_slug: str
    _events_seen_ts: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._row_meta = {}
        self._view_mode = "federation"  # default: federation inbox view
        self._last_rollup = "[dim]loading…[/dim]"
        self._last_rollup_hash = ""
        self._last_rollup_slug = ""
        self._rollup_in_flight = False
        self._events_slug = ""
        self._events_seen_ts = ""

    def set_view_mode(self, mode: str) -> None:
        if mode not in ("lab", "federation"):
            return
        self._view_mode = mode
        self.border_title = (
            "Lab focus" if mode == "lab" else "Federation inbox"
        )
        # Show stale rollup immediately, kick a fresh one
        self.refresh_data()
        self._maybe_run_rollup()

    def compose(self) -> ComposeResult:
        yield Static(id="focus-rollup")
        yield DataTable(id="focus-actions", cursor_type="row", zebra_stripes=True)
        yield RichLog(id="focus-events", wrap=True, max_lines=120, markup=True)

    # KILL SWITCH — when False, Bridge does NO Claude/Haiku/cgl-themes calls.
    # Read-only structured rendering only. Kept on for now until system load
    # is back under control.
    HAIKU_ENABLED: bool = False

    def on_mount(self) -> None:
        self.border_title = "Federation inbox"
        self.refresh_data()
        # Fast tick — structured data only (cheap; no Haiku regardless of switch)
        self.set_interval(5.0, self.refresh_data)
        if self.HAIKU_ENABLED:
            # Slow tick — Haiku rollup, async, only fires if state changed
            self.set_interval(15.0, self._maybe_run_rollup)
        # NOTE: federation pipeline tick (_reflect_stale_labs) disabled — see
        # earlier commit. Re-add with rate limiting later.

    def _active_slug(self) -> str | None:
        if not PANES_FILE.exists():
            return None
        try:
            return json.loads(PANES_FILE.read_text()).get("supervisor_slug")
        except Exception:
            return None

    def refresh_data(self) -> None:
        """Fast tick: structured data only. Haiku rollup runs on slow tick."""
        try:
            rollup_widget = self.query_one("#focus-rollup", Static)
            table = self.query_one("#focus-actions", DataTable)
        except Exception:
            return

        if self._view_mode == "federation":
            self._render_federation_view(rollup_widget, table)
            return

        slug = self._active_slug()
        if not slug:
            rollup_widget.update(
                "[dim](no lab active)[/dim]\n\n"
                "[dim]Cycle with [/dim][bold]\\[ \\][/bold][dim] · "
                "Activate with [/dim][bold]Enter[/bold][dim] · "
                "Or jump with [/dim][bold]1-9[/bold][dim] · "
                "[/dim][bold]f[/bold][dim] for federation view.[/dim]"
            )
            self._row_meta = {}
            table.clear()
            return

        snap = self._fetch_snapshot(slug)
        # Render cached rollup immediately (does not block on Haiku)
        rollup_widget.update(f"[bold]{slug}[/bold]\n\n{self._last_rollup}")
        self._populate_table(table, snap)
        self._refresh_events(slug)

    def _render_federation_view(self, rollup_widget: Static, table: DataTable) -> None:
        """Federation view: 3 stacked sections.
            1. Stale & blocked
            2. Director's inbox
            3. Investment dashboard
        Each section is rows in the shared DataTable. Enter on a row activates
        that lab. Section-header rows are inert (Enter is no-op).
        """
        # Hide the rollup widget — we use the section headers in the table instead.
        rollup_widget.update(
            "[bold]Federation[/bold]  [dim]"
            "Enter on a row → activate that lab · "
            "[/dim][bold]f[/bold][dim] back to lab view[/dim]"
        )

        try:
            prev_row = table.cursor_row
        except Exception:
            prev_row = 0
        try:
            table.clear(columns=True)
            table.add_column("when", width=8)
            table.add_column("lab", width=24)
            table.add_column("info", width=140)
        except Exception:
            pass
        self._row_meta = {}

        whole = self._cached_whole_snapshot()

        # ── Section 1: Stale & Blocked ──────────────────────────────
        sb = whole.get("stale_and_blocked", []) or []
        sev_color = {1: "red", 2: "yellow", 3: "#a8a29e", 4: "#57534e"}
        sev_icon = {1: "⚠", 2: "↻", 3: "·", 4: "·"}
        # Section header
        hkey = "h:stale"
        table.add_row(
            "", f"[bold yellow]── STALE & BLOCKED ({len(sb)}) ──[/bold yellow]",
            "", key=hkey,
        )
        self._row_meta[hkey] = {"kind": "header"}
        for i, item in enumerate(sb[:10]):
            sev = item.get("severity", 4)
            color = sev_color.get(sev, "white")
            icon = sev_icon.get(sev, "·")
            row_key = f"sb:{i}:{item['lab']}"
            table.add_row(
                item.get("since", ""),
                f"[{color}]{icon}[/{color}] {item['lab']}",
                item.get("reason", ""),  # full text, column truncates display
                key=row_key,
            )
            self._row_meta[row_key] = {
                "kind": "lab", "slug": item["lab"],
                "full_info": item.get("reason", ""),
            }
        if not sb:
            empty_key = "sb:empty"
            table.add_row("", "[dim]  (nothing stale or blocked)[/dim]", "", key=empty_key)
            self._row_meta[empty_key] = {"kind": "header"}

        # ── Section 2: Director's Inbox ─────────────────────────────
        inbox = whole.get("director_inbox", []) or []
        hkey2 = "h:inbox"
        table.add_row(
            "", f"[bold #c5b08a]── DIRECTOR'S INBOX ({len(inbox)}) ──[/bold #c5b08a]",
            "", key=hkey2,
        )
        self._row_meta[hkey2] = {"kind": "header"}
        for i, item in enumerate(inbox[:10]):
            ts = item.get("ts") or ""
            when = relative_time(ts) if ts else ""
            full_text = (item.get("theme", "") or "").replace("\n", " ")
            row_key = f"ib:{i}:{item['lab']}"
            table.add_row(
                when,
                f"[#c5b08a]→[/#c5b08a] {item['lab']}",
                full_text,
                key=row_key,
            )
            self._row_meta[row_key] = {
                "kind": "lab", "slug": item["lab"],
                "full_info": full_text,
            }
        if not inbox:
            empty_key = "ib:empty"
            table.add_row("", "[dim]  (no open asks)[/dim]", "", key=empty_key)
            self._row_meta[empty_key] = {"kind": "header"}

        # ── Section 3: Investment Dashboard ─────────────────────────
        inv = whole.get("investment", []) or []
        total_total = sum(r.get("dollars_total", 0) for r in inv)
        total_today = sum(r.get("dollars_today", 0) for r in inv)
        hkey3 = "h:inv"
        table.add_row(
            "",
            f"[bold green]── INVESTMENT  today ${total_today:.2f} · "
            f"all-time ${total_total:.2f} ──[/bold green]",
            "", key=hkey3,
        )
        self._row_meta[hkey3] = {"kind": "header"}
        for i, r in enumerate(inv[:12]):
            slug = r["lab"]
            dt = r.get("dollars_total", 0)
            dy = r.get("dollars_today", 0)
            cm = r.get("claws_merged", 0)
            ca = r.get("claws_abandoned", 0)
            cf = r.get("claws_failed", 0)
            cr = r.get("claws_running", 0)
            shipped = r.get("last_shipped")
            shipped_when = relative_time(shipped) if shipped else "never"
            claws_str = []
            if cm: claws_str.append(f"[green]●{cm}[/green]")
            if cr: claws_str.append(f"[yellow]⟳{cr}[/yellow]")
            if cf: claws_str.append(f"[red]⚠{cf}[/red]")
            if ca: claws_str.append(f"[dim]✗{ca}[/dim]")
            claws_blob = " ".join(claws_str) if claws_str else "[dim]—[/dim]"
            cost_blob = f"${dt:.2f}" + (f" today ${dy:.2f}" if dy > 0 else "")
            row_key = f"inv:{i}:{slug}"
            table.add_row(
                shipped_when,
                slug,
                f"{cost_blob} · claws {claws_blob}",
                key=row_key,
            )
            self._row_meta[row_key] = {"kind": "lab", "slug": slug}

        if table.row_count > 0:
            try:
                table.move_cursor(row=min(prev_row, table.row_count - 1))
            except Exception:
                pass

        if table.row_count > 0:
            try:
                table.move_cursor(row=min(prev_row, table.row_count - 1))
            except Exception:
                pass

    def _fetch_snapshot(self, slug: str) -> dict:
        # Try the cached whole-snapshot first (set by federation view's tick)
        whole = getattr(self, "_whole_cache", None)
        if whole and (datetime.now(timezone.utc) - self._whole_cache_ts).total_seconds() < 3:
            for s in whole.get("labs", []):
                if s.get("slug") == slug:
                    return s
        # Otherwise scrape just this lab in-process (no subprocess)
        try:
            return focus_core.collect(slug)
        except Exception:
            return {}

    def _refresh_events(self, slug: str) -> None:
        """Render the themes feed (executive log).

        Themes are produced by cgl-themes (heuristic gates + Haiku reflection).
        Fast tick reads the .intel/themes/<slug>.jsonl file directly. Slow tick
        kicks a worker that runs `cgl-themes --reflect` to produce new themes.
        """
        try:
            log_widget = self.query_one("#focus-events", RichLog)
        except Exception:
            return

        # Read themes file
        from pathlib import Path
        encoded = slug.replace("/", "-")
        themes_file = sr.LAB_ROOT / ".intel" / "themes" / f"{encoded}.jsonl"
        themes: list[dict] = []
        if themes_file.exists():
            try:
                for line in themes_file.read_text().splitlines():
                    if line.strip():
                        themes.append(json.loads(line))
            except Exception:
                themes = []

        # Reload on slug change
        if slug != self._events_slug:
            log_widget.clear()
            self._events_slug = slug
            self._events_seen_ts = ""

        # Append in chrono order so RichLog renders newest at bottom
        # (or render in reverse for newest-at-top — pick reverse for executive feel)
        themes.sort(key=lambda t: t.get("ts") or "")
        last_ts = self._events_seen_ts
        new_themes = [t for t in themes if (t.get("ts") or "") > last_ts]

        kind_color = {
            "status-shift": "yellow",
            "decision": "#c5b08a",
            "outcome": "green",
            "outcome-fail": "red",
            "risk": "red",
            "ask": "#c5b08a",
            "discovery": "magenta",
            "commit": "#a8a29e",
            "claw": "#00ff66",
        }
        kind_icon = {
            "status-shift": "↻",
            "decision": "◆",
            "outcome": "✓",
            "outcome-fail": "✗",
            "risk": "⚠",
            "ask": "→",
            "discovery": "!",
            "commit": "·",
            "claw": "⟳",
        }
        for t in new_themes:
            ts = t.get("ts") or ""
            when = relative_time(ts) if ts else ""
            kind = t.get("kind", "?")
            theme = (t.get("theme") or "").replace("\n", " ")[:200]
            color = kind_color.get(kind, "white")
            icon = kind_icon.get(kind, "·")
            log_widget.write(
                f"[dim]{when:>4}[/dim]  "
                f"[{color}]{icon} {kind:<13}[/{color}] {theme}"
            )
            if ts:
                self._events_seen_ts = max(self._events_seen_ts, ts)

        # KILL SWITCH gate — no Claude/Haiku/cgl-themes spawns when off.
        if not self.HAIKU_ENABLED:
            return

        # Kick a reflection pass in the background ONLY if the supervisor
        # session log changed since the last reflection. The .pyc-fast path:
        # mtime check is one stat() syscall — no subprocess unless dirty.
        try:
            uuid_map = json.loads((SUPERVISORS_FILE).read_text())
            sup_uuid = (uuid_map.get("supervisors") or {}).get(slug, {}).get("uuid")
            if sup_uuid:
                cwd_slug = str(sr.LAB_ROOT / Path(slug.replace("surface/", "surfaces/").replace("investigation/", "research/investigations/").replace("systems/", "systems/"))).replace("/", "-").replace(".", "-")
                # Easier: search for the jsonl
                claude_proj = Path.home() / ".claude" / "projects"
                log = None
                for d in claude_proj.iterdir():
                    candidate = d / f"{sup_uuid}.jsonl"
                    if candidate.exists():
                        log = candidate
                        break
                if log:
                    mtime = log.stat().st_mtime
                    last_mtime = getattr(self, "_themes_last_session_mtime", {}).get(slug, 0)
                    if mtime <= last_mtime:
                        return  # session log unchanged → skip reflection
                    if not hasattr(self, "_themes_last_session_mtime"):
                        self._themes_last_session_mtime = {}
                    self._themes_last_session_mtime[slug] = mtime
        except Exception:
            pass  # if anything fails, fall through to firing the worker

        if not getattr(self, "_themes_reflect_in_flight", False):
            self._themes_reflect_in_flight = True
            self.run_worker(
                self._themes_reflect_worker(slug),
                exclusive=True, thread=True, group="themes-reflect",
            )

    def _themes_reflect_worker(self, slug: str):
        async def work():
            try:
                subprocess.run(
                    ["cgl-themes", slug, "--reflect"],
                    capture_output=True, text=True, timeout=60,
                )
            except Exception:
                pass
            self.app.call_from_thread(self._themes_reflect_done)
        return work()

    def _themes_reflect_done(self) -> None:
        self._themes_reflect_in_flight = False

    def _reflect_stale_labs(self) -> None:
        """Federation tick: for each lab whose supervisor session log is newer
        than its impressions-index file, kick a reflect worker. Cheap
        mtime-only checks; only fires for labs that genuinely have new events.
        """
        if getattr(self, "_fed_reflect_in_flight", False):
            return
        try:
            sups_file = SUPERVISORS_FILE
            if not sups_file.exists():
                return
            sups = (json.loads(sups_file.read_text()).get("supervisors") or {})
        except Exception:
            return

        claude_proj = Path.home() / ".claude" / "projects"
        themes_dir = sr.LAB_ROOT / ".intel" / "themes"

        stale = []
        for slug, info in sups.items():
            uuid = info.get("uuid")
            if not uuid:
                continue
            # Find session log
            log = None
            try:
                for d in claude_proj.iterdir():
                    candidate = d / f"{uuid}.jsonl"
                    if candidate.exists():
                        log = candidate
                        break
            except Exception:
                continue
            if not log:
                continue
            # Compare mtime to impressions-index
            encoded = slug.replace("/", "-")
            impressions = themes_dir / f"{encoded}.impressions.json"
            log_mtime = log.stat().st_mtime
            idx_mtime = impressions.stat().st_mtime if impressions.exists() else 0
            if log_mtime > idx_mtime:
                stale.append(slug)

        if not stale:
            return

        self._fed_reflect_in_flight = True
        self.run_worker(
            self._fed_reflect_worker(stale),
            exclusive=True, thread=True, group="fed-reflect",
        )

    def _fed_reflect_worker(self, slugs: list[str]):
        async def work():
            for slug in slugs:
                try:
                    subprocess.run(
                        ["cgl-themes", slug, "--reflect"],
                        capture_output=True, text=True, timeout=120,
                    )
                except Exception:
                    pass
            self.app.call_from_thread(self._fed_reflect_done)
        return work()

    def _fed_reflect_done(self) -> None:
        self._fed_reflect_in_flight = False

    def _maybe_run_rollup(self) -> None:
        """Slow tick. If state changed since last rollup and we're not
        already running one, kick off a worker to refresh the rollup."""
        if self._rollup_in_flight:
            return
        if self._view_mode == "federation":
            slug_id = "__whole__"
        else:
            slug_id = self._active_slug() or ""
            if not slug_id:
                return

        # Hash structured data to decide if rollup is worth re-running
        try:
            if slug_id == "__whole__":
                snap = self._fetch_whole_snapshot()
            else:
                snap = self._fetch_snapshot(slug_id)
        except Exception:
            return
        state_hash = self._cheap_hash(snap)
        if (
            slug_id == self._last_rollup_slug
            and state_hash == self._last_rollup_hash
        ):
            return  # nothing changed; skip

        self._rollup_in_flight = True
        self.run_worker(
            self._rollup_worker(slug_id, state_hash),
            exclusive=True, thread=True, group="rollup",
        )

    def _fetch_whole_snapshot(self) -> dict:
        # In-process. The federation view caches this for 3s; standalone
        # callers always get a fresh one.
        try:
            return focus_core.collect_whole()
        except Exception:
            return {}

    # 3s TTL cache for the whole snapshot
    _whole_cache: dict = {}
    _whole_cache_ts = None

    def _cached_whole_snapshot(self) -> dict:
        now = datetime.now(timezone.utc)
        if self._whole_cache_ts is not None and (now - self._whole_cache_ts).total_seconds() < 3:
            return self._whole_cache
        whole = self._fetch_whole_snapshot()
        self._whole_cache = whole
        self._whole_cache_ts = now
        return whole

    def _cheap_hash(self, snap: dict) -> str:
        # Hash a stable subset of the snapshot (skip cost.last_hour rolling windows).
        import hashlib
        if "labs" in snap:
            payload = json.dumps([
                {
                    "slug": s.get("slug"),
                    "claws": (s.get("claws") or {}).get("by_status"),
                    "url": (s.get("url_probe") or {}).get("status"),
                    "uncomm": len(s.get("uncommitted") or []),
                    "commits": [c.get("sha") for c in (s.get("recent_commits") or [])[:3]],
                }
                for s in snap.get("labs", [])
            ], sort_keys=True)
        else:
            sess = snap.get("session") or {}
            payload = json.dumps({
                "claws": (snap.get("claws") or {}).get("by_status"),
                "claws_recent": [r.get("ts") + r.get("status") for r in (snap.get("claws") or {}).get("recent", [])],
                "url": (snap.get("url_probe") or {}).get("status"),
                "uncomm": len(snap.get("uncommitted") or []),
                "commits": [c.get("sha") for c in (snap.get("recent_commits") or [])[:3]],
                "last_user_n": len(sess.get("last_user") or []),
                "last_assistant_n": len(sess.get("last_assistant") or []),
                "last_user_tail": (sess.get("last_user") or [""])[-1][:80],
                "last_assistant_tail": (sess.get("last_assistant") or [""])[-1][:80],
            }, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def _rollup_worker(self, slug_id: str, state_hash: str):
        """Worker thread: in-process haiku rollup, post result back."""
        async def work():
            try:
                if slug_id == "__whole__":
                    whole = focus_core.collect_whole()
                    rollup = focus_core.haiku_whole_rollup(whole)
                else:
                    snap = focus_core.collect(slug_id)
                    rollup = focus_core.haiku_rollup(snap)
                rollup = (rollup or "").strip() or "[dim](no rollup)[/dim]"
            except Exception as e:
                rollup = f"[red]rollup error: {e}[/red]"
            # Post back on main loop
            self.app.call_from_thread(self._apply_rollup, slug_id, state_hash, rollup)
        return work()

    def _apply_rollup(self, slug_id: str, state_hash: str, rollup: str) -> None:
        self._last_rollup = rollup
        self._last_rollup_hash = state_hash
        self._last_rollup_slug = slug_id
        self._rollup_in_flight = False
        # Trigger a fast-tick refresh to render the new rollup
        try:
            self.refresh_data()
        except Exception:
            pass

    def _populate_table(self, table: DataTable, snap: dict) -> None:
        # Capture cursor position so we can restore after rebuild
        try:
            prev_row = table.cursor_row
        except Exception:
            prev_row = 0
        # Always reset columns to per-lab shape (in case we just left federation)
        try:
            table.clear(columns=True)
            table.add_column("when", width=6)
            table.add_column("kind", width=10)
            table.add_column("tag", width=18)
            table.add_column("info", width=80)
        except Exception:
            pass
        self._row_meta = {}
        slug = snap.get("slug", "")

        # URL probe row
        url = snap.get("url_probe") or {}
        if url:
            status = url.get("status", "?")
            mark = "🟢" if str(status) == "200" else "🔴"
            when = relative_time(_iso_from_lastmod(url.get("last_modified")))
            row_key = f"url:{url.get('url')}"
            table.add_row(
                when, "url", mark + " " + str(status),
                url.get("url", ""), key=row_key,
            )
            self._row_meta[row_key] = {"kind": "url", "url": url.get("url")}

        # Comms — last director ask + last supervisor reply (with timestamps)
        sess = snap.get("session") or {}
        users_full = sess.get("last_user_full") or []
        assistants_full = sess.get("last_assistant_full") or []
        if users_full:
            entry = users_full[-1]
            when = relative_time(entry.get("ts"))
            short = entry["text"].replace("\n", " ")[:120]
            row_key = f"comm:user:{entry.get('ts','')}"
            table.add_row(when, "→ user", "latest", short, key=row_key)
            self._row_meta[row_key] = {"kind": "comm", "text": entry["text"]}
        if assistants_full:
            entry = assistants_full[-1]
            when = relative_time(entry.get("ts"))
            short = entry["text"].replace("\n", " ")[:120]
            row_key = f"comm:asst:{entry.get('ts','')}"
            table.add_row(when, "← supr", "latest", short, key=row_key)
            self._row_meta[row_key] = {"kind": "comm", "text": entry["text"]}

        # Claws — actionable rows
        cl = snap.get("claws") or {}
        for r in (cl.get("recent") or [])[:10]:
            ts = r.get("ts", "?")
            status = r.get("status", "?")
            summary = (r.get("summary") or "").replace("\n", " ")[:100]
            mark = {
                "running": "⟳",
                "done": "✓",
                "merged": "●",
                "abandoned": "✗",
                "failed": "⚠",
            }.get(status, status[:3])
            when = relative_from_claw_ts(ts)
            row_key = f"claw:{ts}"
            table.add_row(
                when, f"claw {mark}", f"{status[:8]} {ts[-6:]}",
                summary, key=row_key,
            )
            self._row_meta[row_key] = {
                "kind": "claw", "ts": ts, "status": status, "slug": slug,
            }

        # Commits
        for c in (snap.get("recent_commits") or [])[:6]:
            sha = c.get("sha", "")
            subj = (c.get("subject") or "")[:90]
            ago = c.get("ago", "")  # e.g. "5 minutes ago" — squeeze to short form
            when = _short_ago(ago)
            row_key = f"commit:{sha}"
            table.add_row(
                when, "commit", sha, subj, key=row_key,
            )
            self._row_meta[row_key] = {"kind": "commit", "sha": sha}

        # Uncommitted
        for u in (snap.get("uncommitted") or [])[:8]:
            row_key = f"unc:{u}"
            table.add_row("", "uncomm", "WIP", u, key=row_key)
            self._row_meta[row_key] = {"kind": "uncommitted", "path": u}

        # Restore cursor to a valid row
        if table.row_count > 0:
            try:
                table.move_cursor(row=min(prev_row, table.row_count - 1))
            except Exception:
                pass

    def _selected_row_meta(self) -> dict | None:
        try:
            table = self.query_one("#focus-actions", DataTable)
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        except Exception:
            return None
        return self._row_meta.get(row_key)

    def action_row_merge(self) -> None:
        meta = self._selected_row_meta()
        if not meta or meta.get("kind") != "claw" or meta.get("status") != "done":
            self.app.notify("merge: not applicable to this row", timeout=2)
            return
        slug = meta["slug"]
        ts = meta["ts"]
        result = subprocess.run(
            ["cgl-claw", "merge", slug, ts],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            self.app.notify(f"merged {ts}", timeout=2)
            self.refresh_data()
        else:
            err = (result.stderr or result.stdout or "")[:120]
            self.app.notify(f"merge failed: {err}", severity="error", timeout=4)

    def action_row_abandon(self) -> None:
        meta = self._selected_row_meta()
        if not meta or meta.get("kind") != "claw":
            self.app.notify("abandon: not a claw", timeout=2)
            return
        slug = meta["slug"]
        ts = meta["ts"]
        result = subprocess.run(
            ["cgl-claw", "abandon", slug, ts],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            self.app.notify(f"abandoned {ts}", timeout=2)
            self.refresh_data()
        else:
            err = (result.stderr or "")[:120]
            self.app.notify(f"abandon failed: {err}", severity="error", timeout=4)

    def action_row_expand(self) -> None:
        """Show full text of the selected row in a notify (8s)."""
        meta = self._selected_row_meta()
        if not meta:
            return
        text = meta.get("full_info") or meta.get("text") or ""
        if not text:
            self.app.notify("(no full text for this row)", timeout=2)
            return
        # Notify max ~500 chars; longer texts truncate but still useful
        self.app.notify(text[:600], timeout=10)

    def action_open_row(self) -> None:
        """Enter on a row — kind-specific action."""
        meta = self._selected_row_meta()
        if not meta:
            return
        kind = meta.get("kind")
        if kind == "lab":
            # Activate this lab and switch back to per-lab view
            slug = meta["slug"]
            self.app.action_enter_lab_by_slug(slug)
            self.set_view_mode("lab")
        elif kind == "claw":
            # Notify with one-line summary and full result path
            ts = meta.get("ts")
            slug = meta.get("slug")
            self.app.notify(
                f"claw {ts} ({meta.get('status')}) — see .claws/{ts}.result.md",
                timeout=4,
            )
        elif kind == "comm":
            # Show full text as a notify
            self.app.notify(meta.get("text", "")[:500], timeout=8)
        elif kind == "url":
            self.app.notify(meta.get("url", ""), timeout=4)

    def action_row_tail(self) -> None:
        meta = self._selected_row_meta()
        if not meta or meta.get("kind") != "claw":
            self.app.notify("tail: not a claw", timeout=2)
            return
        slug = meta["slug"]
        ts = meta["ts"]
        log = sr.LAB_ROOT / Path(slug.replace("surface/", "surfaces/")) / ".claws" / f"{ts}.log"
        if not log.exists():
            self.app.notify(f"no log: {log}", severity="warning", timeout=3)
            return
        try:
            tail = subprocess.run(
                ["tail", "-n", "10", str(log)],
                capture_output=True, text=True,
            ).stdout.strip()
        except Exception as e:
            tail = f"error: {e}"
        self.app.notify(tail[:400], timeout=8)


class LedgerPane(DataTable):
    def on_mount(self) -> None:
        self.border_title = "Recent ledger"
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_columns("when", "lab", "skill", "model", "$")
        self.refresh_data()

    def refresh_data(self) -> None:
        self.clear()
        rows = sr.studio_ledger(limit=12)
        for r in rows:
            self.add_row(
                r.timestamp.strftime("%m-%d %H:%M"),
                r.lab,
                r.skill,
                r.model,
                f"{r.cost_usd:.4f}",
            )


class SpinePane(Static):
    def on_mount(self) -> None:
        self.border_title = "Spine"
        self.refresh_data()

    def refresh_data(self) -> None:
        spine = sr.list_spine()
        if not spine:
            self.update("[dim]spine empty[/dim]")
            return
        by_kind: dict[str, list[str]] = {}
        for s in spine:
            by_kind.setdefault(s.kind, []).append(s.name)
        # Render every kind state_reader actually returns, in alphabetical order.
        parts = []
        for kind in sorted(by_kind.keys()):
            names = by_kind[kind]
            parts.append(
                f"[bold]{kind}[/bold] ({len(names)}): "
                f"[dim]{', '.join(names[:6])}{'…' if len(names) > 6 else ''}[/dim]"
            )
        self.update("\n".join(parts) if parts else "[dim](no spine assets)[/dim]")


class BridgeApp(App):
    CSS = """
    Screen { background: #1c1917; }

    #main-row { height: 1fr; }
    #left-col { width: 28%; }

    LabsPane {
        border: round #c5b08a;
        padding: 1 2;
        background: #292524;
        color: #e7e5e4;
        height: 1fr;
    }
    LabFormPane {
        border: round #c5b08a;
        padding: 1 2;
        background: #292524;
        color: #e7e5e4;
        height: 1fr;
        display: none;
    }
    LabFormPane.shown { display: block; }
    LabsPane.hidden { display: none; }
    .form-label { color: #c5b08a; padding-top: 1; }
    #form-status { color: red; padding-top: 1; }
    FocusPane {
        border: round #c5b08a;
        padding: 1 2;
        background: #292524;
        color: #e7e5e4;
        width: 1fr;
    }
    #focus-rollup { height: auto; max-height: 14; }
    #focus-actions { height: 40%; }
    #focus-events { height: 1fr; border-top: solid #57534e; padding: 0 1; background: #1c1917; }
    """

    TITLE = f"{_env.TITLE} · bridge"
    SUB_TITLE = "director console"

    BINDINGS = [
        Binding("r", "refresh", "Refresh", priority=True),
        Binding("q", "quit", "Quit", priority=True),
        Binding("tab", "focus_next_pane", "Tab", priority=True),
        Binding("shift+tab", "focus_prev_pane", "Sh-Tab", priority=True),
        Binding("shift+left", "focus_pane_left", "← Pane", priority=True),
        Binding("shift+right", "focus_pane_right", "Pane →", priority=True),
        Binding("h", "focus_pane_left", "← Pane (h)", priority=True, show=False),
        Binding("l", "focus_pane_right", "Pane → (l)", priority=True, show=False),
        Binding("f", "toggle_view", "Federation/Lab", priority=True),
        Binding("N", "open_form", "New", priority=True),
        Binding("D", "delete_lab", "Delete", priority=True),
        Binding("M", "modify_lab", "Modify", priority=True),
        Binding("left_square_bracket", "move_cursor(-1)", "←", priority=True),
        Binding("right_square_bracket", "move_cursor(1)", "→", priority=True),
        *[Binding(str(i), f"enter_lab({i})", f"Lab {i}", priority=True) for i in range(1, 10)],
    ]

    # Pending delete confirmation (slug or None)
    _pending_delete: str | None = None

    async def on_key(self, event) -> None:
        """Catch app-level shortcuts that priority bindings sometimes miss
        when a child widget has focus and consumes the key first."""
        key = event.key

        # Pending delete confirmation — any key besides 'y' cancels
        if self._pending_delete:
            slug = self._pending_delete
            self._pending_delete = None
            if key == "y":
                self._do_archive(slug)
                event.stop()
                return
            else:
                self.notify("delete cancelled", timeout=2)
                event.stop()
                return

        if key == "f":
            self.action_toggle_view()
            event.stop()
        elif key == "tab":
            self.action_focus_next_pane()
            event.stop()
        elif key == "shift+tab":
            self.action_focus_prev_pane()
            event.stop()
        elif key in ("shift+left", "h"):
            self.action_focus_pane_left()
            event.stop()
        elif key in ("shift+right", "l"):
            self.action_focus_pane_right()
            event.stop()
        elif key in ("left_square_bracket", "["):
            self.action_move_cursor(-1)
            event.stop()
        elif key in ("right_square_bracket", "]"):
            self.action_move_cursor(1)
            event.stop()
        elif key == "enter":
            # Route Enter based on which sub-pane has focus.
            try:
                focus = self.query_one("#focus", FocusPane)
                actions = self.query_one("#focus-actions", DataTable)
            except Exception:
                return
            focused = self.focused
            in_actions = focused is actions or (
                focused is not None and actions in focused.ancestors
            )
            if in_actions:
                focus.action_open_row()
            else:
                self.action_activate_cursor()
            event.stop()
        elif key in ("m", "a", "t", "e"):
            # Row actions only fire when focus is in the actions table
            try:
                focus = self.query_one("#focus", FocusPane)
                actions = self.query_one("#focus-actions", DataTable)
            except Exception:
                return
            focused = self.focused
            if focused is actions or (focused and actions in focused.ancestors):
                if key == "m":
                    focus.action_row_merge()
                elif key == "a":
                    focus.action_row_abandon()
                elif key == "t":
                    focus.action_row_tail()
                elif key == "e":
                    focus.action_row_expand()
                event.stop()

    # Order of focusable sub-panes (cycle via Tab)
    FOCUS_ORDER = ["#labs", "#focus-actions"]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="main-row"):
            with Vertical(id="left-col"):
                yield LabsPane(id="labs")
                yield LabFormPane(id="lab-form")
            yield FocusPane(id="focus")
        yield Footer()

    def on_mount(self) -> None:
        snap = sr.studio_snapshot()
        self.sub_title = (
            f"today ${snap.cumulative_dollars_today:.2f} · "
            f"all ${snap.cumulative_dollars_all_time:.2f} · "
            f"{len(snap.labs)} labs"
        )
        # Restore active indicator from panes.json (if running in cgl-tmux)
        if PANES_FILE.exists():
            try:
                current = json.loads(PANES_FILE.read_text()).get("supervisor_slug")
                if current:
                    slugs = [l.slug for l in snap.labs]
                    if current in slugs:
                        active_idx = slugs.index(current)
                        labs_pane = self.query_one("#labs", LabsPane)
                        labs_pane.set_active(active_idx)
                        labs_pane.set_cursor(active_idx, min(len(slugs), 9))
            except Exception:
                pass

    def action_refresh(self) -> None:
        for sel in ("#labs", "#focus"):
            try:
                self.query_one(sel).refresh_data()
            except Exception:
                pass
        snap = sr.studio_snapshot()
        self.sub_title = (
            f"today ${snap.cumulative_dollars_today:.2f} · "
            f"all ${snap.cumulative_dollars_all_time:.2f} · "
            f"{len(snap.labs)} labs"
        )
        self.notify("refreshed", timeout=1.5)

    def action_focus_next_pane(self) -> None:
        self._cycle_focus(+1)

    def action_focus_prev_pane(self) -> None:
        self._cycle_focus(-1)

    def action_focus_pane_left(self) -> None:
        """Top-level: focus the LabsPane (left column)."""
        try:
            self.query_one("#labs", LabsPane).focus()
        except Exception:
            pass

    def action_focus_pane_right(self) -> None:
        """Top-level: focus the FocusPane's actions table (right column)."""
        try:
            # Prefer the actions DataTable so arrows navigate immediately
            self.query_one("#focus-actions").focus()
        except Exception:
            try:
                self.query_one("#focus", FocusPane).focus()
            except Exception:
                pass

    def action_toggle_view(self) -> None:
        try:
            focus = self.query_one("#focus", FocusPane)
        except Exception:
            return
        new_mode = "federation" if focus._view_mode == "lab" else "lab"
        focus.set_view_mode(new_mode)
        self.notify(f"view → {new_mode}", timeout=2)

    def action_enter_lab_by_slug(self, slug: str) -> None:
        labs = sr.list_labs()
        for i, lab in enumerate(labs):
            if lab.slug == slug:
                self.action_enter_lab(i + 1)
                return

    # ── N / M / D form actions ──────────────────────────────────────────
    def action_open_form(self) -> None:
        try:
            labs_pane = self.query_one("#labs", LabsPane)
            form = self.query_one("#lab-form", LabFormPane)
        except Exception:
            return
        labs_pane.add_class("hidden")
        form.add_class("shown")
        # Focus the slug input first
        try:
            form.query_one("#form-slug", Input).focus()
        except Exception:
            pass

    def action_close_form(self) -> None:
        try:
            labs_pane = self.query_one("#labs", LabsPane)
            form = self.query_one("#lab-form", LabFormPane)
        except Exception:
            return
        form.remove_class("shown")
        labs_pane.remove_class("hidden")
        # Refresh labs list
        try:
            labs_pane.refresh_data()
            labs_pane.focus()
        except Exception:
            pass

    def action_delete_lab(self) -> None:
        try:
            labs_pane = self.query_one("#labs", LabsPane)
        except Exception:
            return
        labs = sr.list_labs()
        if not labs:
            return
        idx = labs_pane.cursor_idx
        if idx >= len(labs):
            return
        slug = labs[idx].slug
        # Confirm via notify with a follow-up keypress: simpler — set a "pending"
        # state and handle next 'y' or 'n' in the on_key router.
        self._pending_delete = slug
        self.notify(
            f"delete {slug}? press [bold]y[/bold] to confirm or any other key to cancel",
            timeout=8, severity="warning",
        )

    def action_modify_lab(self) -> None:
        self.notify("modify: not yet wired — placeholder", timeout=2)

    def _do_archive(self, slug: str) -> None:
        try:
            r = subprocess.run(
                ["cgl-labs", "archive", slug],
                capture_output=True, text=True, timeout=15,
            )
        except Exception as e:
            self.notify(f"archive error: {e}", severity="error", timeout=4)
            return
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "")[:200].strip()
            self.notify(f"archive failed: {err}", severity="error", timeout=5)
            return
        self.notify(f"archived {slug}", timeout=3)
        try:
            self.query_one("#labs", LabsPane).refresh_data()
        except Exception:
            pass

    def _cycle_focus(self, direction: int) -> None:
        order = self.FOCUS_ORDER
        # Find which is currently focused
        focused = self.focused
        cur_sel = None
        for sel in order:
            try:
                w = self.query_one(sel)
                if w is focused or (focused and w in focused.ancestors):
                    cur_sel = sel
                    break
            except Exception:
                continue
        if cur_sel is None:
            new_idx = 0
        else:
            new_idx = (order.index(cur_sel) + direction) % len(order)
        try:
            self.query_one(order[new_idx]).focus()
            self.notify(f"focus → {order[new_idx]}", timeout=1.5)
        except Exception:
            pass

    def action_move_cursor(self, direction: int) -> None:
        """Move the lab-picker highlight cursor (does NOT activate)."""
        labs = sr.list_labs()
        if not labs:
            return
        try:
            labs_pane = self.query_one("#labs", LabsPane)
        except Exception:
            return
        new_idx = (labs_pane.cursor_idx + direction) % min(len(labs), 9)
        labs_pane.set_cursor(new_idx, min(len(labs), 9))

    def action_activate_cursor(self) -> None:
        """Activate the lab currently under the cursor."""
        try:
            labs_pane = self.query_one("#labs", LabsPane)
        except Exception:
            return
        self.action_enter_lab(labs_pane.cursor_idx + 1)

    def action_enter_lab(self, n: int) -> None:
        labs = sr.list_labs()
        if n - 1 >= len(labs):
            self.notify(f"no lab {n}", severity="warning", timeout=1.5)
            return
        lab = labs[n - 1]

        # If we're running inside cgl-tmux, route activation to the
        # supervisor pane. Otherwise fall back to the suspend-and-run-Lab-TUI
        # path so cgl-bridge still works standalone.
        if PANES_FILE.exists():
            self._activate_supervisor(lab.slug)
            # Update labs pane indicator
            try:
                labs_pane = self.query_one("#labs", LabsPane)
                labs_pane.set_active(n - 1)
            except Exception:
                pass
            return

        with self.suspend():
            subprocess.run(["cgl-lab", lab.slug])
        self.action_refresh()

    def _activate_supervisor(self, slug: str) -> None:
        """Route a lab activation into the visible supervisor slot.

        Model:
          - Each active lab's supervisor lives as a tmux pane.
          - The "visible slot" is bottom-right of the lab window.
          - Backgrounded supervisors live in the hidden _supervisors window,
            tagged by slug via pane_title.
          - Activating: park the currently-visible supervisor back to holding
            (if any), then either join-pane the existing one for <slug> or
            create a fresh pane in the visible slot.
          - Backgrounded supervisors keep running.
        """
        try:
            panes_data = json.loads(PANES_FILE.read_text())
            socket = panes_data.get("socket", "cgl")
            visible_pane = panes_data["panes"].get("supervisor", "")
            util_pane = panes_data["panes"]["utility"]
            visible_slug = panes_data.get("supervisor_slug")
            holding_map = panes_data.get("holding", {})  # slug -> pane_id
        except (KeyError, json.JSONDecodeError, OSError) as e:
            self.notify(f"can't read panes: {e}", severity="error", timeout=3)
            return

        if visible_slug == slug:
            self.notify(f"{slug} already active", timeout=2)
            return

        live_panes = self._tmux_live_panes(socket)

        # Reconcile holding_map with reality — drop entries whose pane is dead
        holding_map = {
            s: p for s, p in holding_map.items() if p in live_panes
        }

        # If visible pane is dead, clear stale state.
        if visible_pane and visible_pane not in live_panes:
            visible_pane = ""
            visible_slug = None

        # Step 1: park or kill the currently visible pane.
        if visible_slug and visible_pane in live_panes:
            if self._park_pane(socket, visible_pane):
                holding_map[visible_slug] = visible_pane
            else:
                self.notify(
                    f"could not park {visible_slug}; aborting switch",
                    severity="error", timeout=3,
                )
                return
        elif not visible_slug and visible_pane and visible_pane in live_panes:
            subprocess.run(
                ["tmux", "-L", socket, "kill-pane", "-t", visible_pane],
                check=False,
            )

        # Step 2: bring back from holding or create fresh.
        if slug in holding_map:
            holding_pane = holding_map[slug]
            new_visible = self._unpark_pane(socket, holding_pane, util_pane)
            if not new_visible:
                self.notify(
                    "join-pane failed; supervisor stuck in holding pen",
                    severity="error", timeout=3,
                )
                return
            del holding_map[slug]  # no longer in holding
            self.notify(f"resumed → {slug}", timeout=2)
        else:
            new_visible = self._fresh_supervisor(socket, util_pane, slug)
            if not new_visible:
                self.notify(
                    "could not create supervisor pane",
                    severity="error", timeout=3,
                )
                return
            self.notify(f"supervisor → {slug}", timeout=2)

        # Step 3: persist
        panes_data["panes"]["supervisor"] = new_visible
        panes_data["supervisor_slug"] = slug
        panes_data["holding"] = holding_map
        PANES_FILE.write_text(json.dumps(panes_data, indent=2) + "\n")

    def _tmux_live_panes(self, socket: str) -> list[str]:
        return subprocess.run(
            ["tmux", "-L", socket, "list-panes", "-s", "-F", "#{pane_id}"],
            capture_output=True, text=True,
        ).stdout.split()

    def _park_pane(self, socket: str, pane: str) -> bool:
        """Move a pane into the _supervisors holding window. Returns success."""
        out = subprocess.run(
            ["tmux", "-L", socket, "list-panes", "-t", "cgl:_supervisors",
             "-F", "#{pane_id}"],
            capture_output=True, text=True,
        ).stdout.split()
        if not out:
            r = subprocess.run(
                ["tmux", "-L", socket, "break-pane", "-d", "-s", pane],
                capture_output=True, text=True,
            )
            return r.returncode == 0
        # Try every pane in _supervisors as the join target until one works
        for target in out:
            r = subprocess.run(
                ["tmux", "-L", socket, "join-pane", "-d", "-s", pane, "-t", target],
                capture_output=True, text=True,
            )
            if r.returncode == 0:
                # Rebalance layout so future joins have room
                subprocess.run(
                    ["tmux", "-L", socket, "select-layout", "-t", "cgl:_supervisors", "tiled"],
                    check=False,
                )
                return True
        # Last resort: break to a new window — never returns "pane too small"
        r = subprocess.run(
            ["tmux", "-L", socket, "break-pane", "-d", "-s", pane],
            capture_output=True, text=True,
        )
        if r.returncode == 0:
            # Move that new window's pane into _supervisors via move-pane
            # (find the orphan pane: it's the one whose window has 1 pane and
            # isn't lab/_supervisors/distribution-engine)
            wins = subprocess.run(
                ["tmux", "-L", socket, "list-windows", "-t", "cgl",
                 "-F", "#{window_id}\t#{window_name}\t#{window_panes}"],
                capture_output=True, text=True,
            ).stdout.splitlines()
            for line in wins:
                wid, wname, wpanes = line.split("\t")
                if wname not in ("lab", "_supervisors", "distribution-engine") \
                   and wpanes == "1":
                    orphan = subprocess.run(
                        ["tmux", "-L", socket, "list-panes", "-t", wid,
                         "-F", "#{pane_id}"],
                        capture_output=True, text=True,
                    ).stdout.strip()
                    if orphan and out:
                        subprocess.run(
                            ["tmux", "-L", socket, "move-pane", "-d",
                             "-s", orphan, "-t", out[0]],
                            check=False,
                        )
                        subprocess.run(
                            ["tmux", "-L", socket, "select-layout",
                             "-t", "cgl:_supervisors", "tiled"],
                            check=False,
                        )
                        return True
        return False

    def _unpark_pane(self, socket: str, holding_pane: str, util_pane: str) -> str | None:
        """Move a pane from holding back into the visible bottom-right slot."""
        # join-pane -s <holding> -t <util> -h -l 50% places it horizontally
        # to the right of the utility pane, which is the bottom-right slot.
        result = subprocess.run(
            ["tmux", "-L", socket, "join-pane", "-h", "-l", "50%",
             "-s", holding_pane, "-t", util_pane],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return None
        # The pane id is preserved across join-pane.
        return holding_pane

    def _fresh_supervisor(self, socket: str, util_pane: str, slug: str) -> str | None:
        """Split a new pane in the visible slot and start the supervisor."""
        split = subprocess.run(
            ["tmux", "-L", socket, "split-window",
             "-t", util_pane, "-h", "-l", "50%",
             "-c", str(sr.LAB_ROOT),
             "-P", "-F", "#{pane_id}"],
            capture_output=True, text=True,
        )
        new_pane = split.stdout.strip()
        if not new_pane:
            return None
        context = self._build_supervisor_context(slug)
        subprocess.run(
            ["tmux", "-L", socket, "respawn-pane", "-k", "-t", new_pane,
             f"cgl-supervisor activate {shell_quote(slug)} "
             f"--inject {shell_quote(context)}"],
            check=False,
        )
        return new_pane

    def _build_supervisor_context(self, slug: str) -> str:
        """Bundle lab card + recent ledger + contract into an initial prompt."""
        lab = sr.get_lab(slug)
        if lab is None:
            return f"Activated lab {slug} (lab not found)."

        rows = sr.lab_ledger(slug, limit=5)
        contracts = sr.list_contracts(slug)

        lines = [
            f"You are the supervisor for **{slug}** ({lab.kind}).",
            f"Status: {lab.status} · last touched: {lab.days_since_touch}d ago",
            f"Path: {lab.path}",
        ]
        if lab.description:
            lines.append(f"Description: {lab.description}")

        if contracts:
            c = contracts[-1]
            lines.append(
                f"\nActive contract v{c.version}: {c.question[:200]}"
            )

        if rows:
            lines.append("\nRecent ledger:")
            for r in rows:
                lines.append(
                    f"  {r.timestamp:%m-%d %H:%M} {r.skill} ({r.model}) ${r.cost_usd:.4f}"
                )

        lines.append(
            "\nThe director just activated this lab. "
            "Wait for direction unless there's an obvious next move."
        )
        lines.append(
            "\n## How you work\n"
            "You are a *supervisor*, not a worker. When the director gives you "
            "a task that takes more than a few seconds or doesn't need your "
            f"direct attention, spawn a background claw:\n\n"
            f"  cgl-claw spawn {slug} \"<exact task description>\"\n\n"
            "The claw runs `claude -p` in the background in this lab's "
            f"worktree. Logs land in {lab.path}/.claws/<ts>.log and the "
            f"final result in {lab.path}/.claws/<ts>.result.md. You stay free "
            "to take more direction immediately. Tell the director the claw is "
            "spawned and move on. Check `cgl-claw list "
            f"{slug}` to see what's running. "
            "Only do work yourself for trivial things (one-line answers, "
            "quick file reads) where spawning would be overkill."
        )
        return "\n".join(lines)


def shell_quote(s: str) -> str:
    """Single-quote for shell, escaping internal single quotes."""
    return "'" + s.replace("'", "'\\''") + "'"


def main() -> None:
    BridgeApp().run()


if __name__ == "__main__":
    main()
