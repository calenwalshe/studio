"""cockpit.py — Studio Cockpit: federation home screen.

Run via:
    CGL_LAB_ROOT=examples/hello-lab bin/cgl-cockpit

Or directly:
    studio/.venv/bin/python studio/lab_tui/cockpit.py examples/hello-lab

Reads federation root from CGL_LAB_ROOT env var (matching harness convention).
Falls back to argv[1] if env not set. Errors clearly if neither is provided.

Layout:
    Header strip (status counts)
    Body — LabList accordion (left 50%) | DirectorChat (right 50%)
    Footer — q quit, r refresh, enter Expand/Collapse, c Chat about lab, ? help
"""
from __future__ import annotations

import asyncio
import os
import sys
import textwrap
from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Footer, Header, Input, Static

from lab_tui.actions import (
    apply_decision,
    archive_claw,
    archive_lab,
    create_lab,
    spawn_dry_run_claw,
)

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

from lab_tui.loaders import LabSummary, ClawBundle, discover_labs  # noqa: E402


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
# LabRow — custom accordion row widget
# ---------------------------------------------------------------------------

_NO_REVIEW_RECS = frozenset({"abandon", "dry_run"})
_REVIEW_COLOR = {
    "merge": "bold green",
    "keep_evidence": "bold yellow",
    "promote": "bold green",
    "partial_promote": "bold yellow",
    "abandon": "dim",
    "dry_run": "dim",
}


def _claw_rec_markup(rec: str) -> str:
    color = _REVIEW_COLOR.get(rec, "")
    if color:
        return f"[{color}]{rec}[/{color}]"
    return rec


# ---------------------------------------------------------------------------
# Expansion body formatting helpers
# ---------------------------------------------------------------------------

def _pad_kv(rows: list[tuple[str, str]], indent: int = 2, max_width: int = 100) -> str:
    """Format key-value pairs with aligned colons.

    All keys are padded to (longest_key + 2) width. Long values wrap aligned
    with the value column (continuation lines start at the same column).
    """
    if not rows:
        return ""
    prefix = " " * indent
    key_width = max(len(k) for k, _ in rows) + 2  # +2 for ": "
    output_lines: list[str] = []
    for key, value in rows:
        label = f"{key}:".ljust(key_width)
        value_col = indent + key_width  # absolute column where value starts
        # Wrap long values at word boundaries
        available = max_width - value_col
        if available < 20:
            available = 20
        wrapped = textwrap.wrap(str(value), width=available) if value else [""]
        if not wrapped:
            wrapped = [""]
        first = wrapped[0]
        output_lines.append(f"{prefix}{label}{first}")
        continuation_prefix = " " * value_col
        for cont in wrapped[1:]:
            output_lines.append(f"{continuation_prefix}{cont}")
    return "\n".join(output_lines)


def _format_table(
    headers: list[str],
    rows: list[list[str]],
    indent: int = 2,
    right_align_cols: list[int] | None = None,
) -> str:
    """Format a table with auto-computed column widths.

    Two spaces between columns. Numeric (right_align_cols) columns are
    right-aligned; all others left-aligned.
    """
    if right_align_cols is None:
        right_align_cols = []

    col_count = len(headers)
    # Compute column widths from headers and data
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < col_count:
                widths[i] = max(widths[i], len(str(cell)))

    prefix = " " * indent
    sep = "  "

    def _fmt_row(cells: list[str]) -> str:
        parts = []
        for i, cell in enumerate(cells[:col_count]):
            w = widths[i] if i < len(widths) else 0
            if i in right_align_cols:
                parts.append(str(cell).rjust(w))
            else:
                parts.append(str(cell).ljust(w))
        return prefix + sep.join(parts).rstrip()

    lines = [_fmt_row(headers)]
    for row in rows:
        lines.append(_fmt_row(row))
    return "\n".join(lines)


def _build_expansion_text(summary: LabSummary, selected_claw_index: int = 0) -> str:
    """Build the column-aligned body shown when a LabRow is expanded.

    selected_claw_index: which claw row (0-based) should show the -> marker.
    """
    lines: list[str] = []

    # --- 1. Orientation block ---
    lines.append("Orientation")
    if summary.orientations:
        orient = summary.orientations[0]
        sources = getattr(orient, "sources", [])
        stop_rule = getattr(orient, "stop_rule", None)
        kv_rows: list[tuple[str, str]] = [
            ("Objective", orient.objective),
        ]
        if sources:
            kv_rows.append(("Sources", ", ".join(sources)))
        kv_rows.append(("Status", getattr(orient, "status", "?")))
        if stop_rule:
            kv_rows.append(("Stop rule", stop_rule))
        lines.append(_pad_kv(kv_rows, indent=2))

        constraints = getattr(orient, "constraints", {})
        if constraints:
            lines.append("  Constraints")
            c_rows = [(k, str(v)) for k, v in constraints.items()]
            # indent=4 for constraints sub-block
            lines.append(_pad_kv(c_rows, indent=4))
    else:
        lines.append("  (no orientations defined)")

    lines.append("")

    # --- 2. Claws table (with -> selection marker) ---
    lines.append("Claws")
    if summary.bundles:
        tbl_headers = ["", "ID", "ROLE", "RECOMMENDATION", "CLAIMS", "EVENTS", "STATUS"]
        tbl_rows: list[list[str]] = []
        for i, bundle in enumerate(summary.bundles):
            marker = "->" if i == selected_claw_index else "  "
            tbl_rows.append([
                marker,
                bundle.bundle_id,
                bundle.meta.get("role", "?"),
                bundle.meta.get("promotion_recommendation", "?"),
                str(bundle.claim_count),
                str(bundle.trace_count),
                bundle.meta.get("status", "?"),
            ])
        # CLAIMS=col5, EVENTS=col6 are numeric -> right-align
        lines.append(_format_table(tbl_headers, tbl_rows, indent=2, right_align_cols=[4, 5]))
    else:
        lines.append("  (no claws yet — lab is stale, spawn a scout)")

    lines.append("")

    # --- 3. Director Queue items for this lab ---
    lines.append("Director Queue")
    review_bundles = [
        b for b in summary.bundles
        if b.meta.get("promotion_recommendation", "abandon") not in _NO_REVIEW_RECS
    ]
    if review_bundles:
        for bundle in review_bundles:
            rec = bundle.meta.get("promotion_recommendation", "?")
            first_line = (
                bundle.result_text.strip().splitlines()[0][:80]
                if bundle.result_text.strip()
                else "(no result.md)"
            )
            lines.append(f"  {bundle.bundle_id} | {rec} | {first_line}")
    else:
        lines.append("  (nothing awaiting review)")

    lines.append("")

    # --- 4. Quick actions ---
    lines.append("Press 'c' to ask the chat about this lab  •  Esc or Enter to collapse")

    return "\n".join(lines)


class LabRow(Widget):
    """A single accordion row: always-visible header + collapsible body."""

    DEFAULT_CSS = """
    LabRow {
        width: 1fr;
        height: auto;
        background: #16213e;
        color: #e2e2e2;
    }

    LabRow > .lab-row-header {
        height: 1;
        background: #16213e;
        color: #e2e2e2;
        padding: 0 1;
    }

    LabRow:focus > .lab-row-header {
        background: #1f3460;
        color: #ffffff;
    }

    LabRow.expanded > .lab-row-header {
        background: #1f3460;
        color: #ffffff;
    }

    LabRow > .lab-row-body {
        height: auto;
        background: #12122a;
        color: #cdd6f4;
        padding: 0 2;
        display: none;
    }

    LabRow.expanded > .lab-row-body {
        display: block;
    }
    """

    def __init__(self, summary: LabSummary, **kwargs) -> None:
        super().__init__(**kwargs)
        self._summary = summary
        self._expanded = False
        self._selected_claw_index: int = 0
        self.can_focus = True

    def compose(self) -> ComposeResult:
        sym = _symbol(self._summary.status)
        short_obj = _orientation_summary(self._summary)
        claw_count = len(self._summary.bundles)
        promo = self._summary.promotion_candidates
        header_text = (
            f"{sym} {self._summary.lab_id:<25} "
            f"{self._summary.kind:<14} "
            f"{short_obj:<52} "
            f"claws={claw_count} promo={promo}"
        )
        yield Static(header_text, classes="lab-row-header")
        body_text = _build_expansion_text(self._summary, self._selected_claw_index)
        yield Static(body_text, classes="lab-row-body", markup=False)

    def selected_claw(self):
        """Return the currently selected ClawBundle, or None."""
        if not self._summary.bundles:
            return None
        idx = max(0, min(self._selected_claw_index, len(self._summary.bundles) - 1))
        return self._summary.bundles[idx]

    def move_claw_selection(self, delta: int) -> None:
        """Move claw selection up/down within the expanded claws list."""
        if not self._summary.bundles:
            return
        new_idx = max(0, min(len(self._summary.bundles) - 1, self._selected_claw_index + delta))
        if new_idx != self._selected_claw_index:
            self._selected_claw_index = new_idx
            self._refresh_body()

    @property
    def lab_id(self) -> str:
        return self._summary.lab_id

    @property
    def expanded(self) -> bool:
        return self._expanded

    def expand(self) -> None:
        self._expanded = True
        self.add_class("expanded")
        self.scroll_visible()

    def collapse(self) -> None:
        self._expanded = False
        self.remove_class("expanded")

    def toggle(self) -> None:
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    def _refresh_body(self) -> None:
        """Re-render the body text with the current selected claw index."""
        try:
            body: Static = self.query_one(".lab-row-body", Static)
            body.update(_build_expansion_text(self._summary, self._selected_claw_index))
        except Exception:
            pass

    def refresh_data(self, summary: LabSummary) -> None:
        self._summary = summary
        # Clamp selected index in case claws were removed
        if self._summary.bundles:
            self._selected_claw_index = max(0, min(self._selected_claw_index, len(self._summary.bundles) - 1))
        else:
            self._selected_claw_index = 0
        sym = _symbol(summary.status)
        short_obj = _orientation_summary(summary)
        claw_count = len(summary.bundles)
        promo = summary.promotion_candidates
        header_text = (
            f"{sym} {summary.lab_id:<25} "
            f"{summary.kind:<14} "
            f"{short_obj:<52} "
            f"claws={claw_count} promo={promo}"
        )
        header: Static = self.query_one(".lab-row-header", Static)
        header.update(header_text)
        body: Static = self.query_one(".lab-row-body", Static)
        body.update(_build_expansion_text(summary, self._selected_claw_index))


# ---------------------------------------------------------------------------
# LabList — scrollable container of LabRows
# ---------------------------------------------------------------------------

class LabList(VerticalScroll):
    """Scrollable list of LabRow widgets forming an accordion."""

    DEFAULT_CSS = """
    LabList {
        width: 1fr;
        height: 1fr;
        border: round #888888;
        background: #16213e;
    }
    """

    def __init__(self, summaries: list[LabSummary], **kwargs) -> None:
        super().__init__(**kwargs)
        self._summaries = summaries
        self._focused_idx: int = 0

    def compose(self) -> ComposeResult:
        for i, s in enumerate(self._summaries):
            yield LabRow(s, id=f"lab-row-{i}")

    def on_mount(self) -> None:
        rows = list(self.query(LabRow))
        if rows:
            rows[0].focus()

    def _rows(self) -> list[LabRow]:
        return list(self.query(LabRow))

    def focused_row(self) -> LabRow | None:
        rows = self._rows()
        for row in rows:
            if row.has_focus:
                return row
        return rows[0] if rows else None

    def focused_index(self) -> int:
        rows = self._rows()
        for i, row in enumerate(rows):
            if row.has_focus:
                return i
        return 0

    def move_focus(self, delta: int) -> None:
        rows = self._rows()
        if not rows:
            return
        idx = self.focused_index()
        new_idx = max(0, min(len(rows) - 1, idx + delta))
        rows[new_idx].focus()

    def toggle_focused(self) -> str | None:
        """Toggle the focused row. Collapse any other expanded row first.
        Returns the lab_id of the now-expanded row, or None if collapsed."""
        rows = self._rows()
        focused = self.focused_row()
        if not focused:
            return None

        # Collapse all others
        for row in rows:
            if row is not focused and row.expanded:
                row.collapse()

        focused.toggle()
        expanded_lab_id = focused.lab_id if focused.expanded else None

        # Notify the app about the scope change
        if expanded_lab_id is not None:
            self.post_message(LabList.LabExpanded(expanded_lab_id, focused._summary.lab_root))
        else:
            self.post_message(LabList.LabCollapsed())

        return expanded_lab_id

    class LabExpanded(Message):
        """Posted when a lab row is expanded."""
        def __init__(self, lab_id: str, lab_root: Path) -> None:
            super().__init__()
            self.lab_id = lab_id
            self.lab_root = lab_root

    class LabCollapsed(Message):
        """Posted when the expanded lab row is collapsed (no row is expanded)."""
        def __init__(self) -> None:
            super().__init__()

    def collapse_all(self) -> None:
        for row in self._rows():
            if row.expanded:
                row.collapse()

    def refresh_all(self, summaries: list[LabSummary]) -> None:
        """Refresh all rows with new summary data."""
        self._summaries = summaries
        rows = self._rows()
        for i, summary in enumerate(summaries):
            if i < len(rows):
                rows[i].refresh_data(summary)


# ---------------------------------------------------------------------------
# Header strip widget
# ---------------------------------------------------------------------------

class LabHeaderStrip(Static):
    """One-line strip above the lab list: lab count + status counts."""

    DEFAULT_CSS = """
    LabHeaderStrip {
        width: 1fr;
        height: 1;
        background: #0d0d1a;
        color: #888888;
        padding: 0 1;
    }
    """

    def __init__(self, summaries: list[LabSummary], federation_root: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self._summaries = summaries
        self._federation_root = federation_root

    def on_mount(self) -> None:
        self._render_strip()

    def _render_strip(self) -> None:
        count = len(self._summaries)
        lab_word = "lab" if count == 1 else "labs"

        needs_review = sum(1 for s in self._summaries if s.status == "needs_review")
        idle = sum(1 for s in self._summaries if s.status == "idle")
        stale = sum(1 for s in self._summaries if s.status == "stale")
        active = sum(1 for s in self._summaries if s.status == "active")
        error = sum(1 for s in self._summaries if s.status == "error")

        left = f"{count} {lab_word} — {self._federation_root}"
        parts = []
        if needs_review:
            parts.append(f"! {needs_review} needs review")
        if active:
            parts.append(f"● {active} active")
        if idle:
            parts.append(f"◐ {idle} idle")
        if stale:
            parts.append(f"○ {stale} stale")
        if error:
            parts.append(f"× {error} error")
        right = "  ".join(parts)

        self.update(f"{left}   |   {right}" if right else left)

    def refresh_strip(self, summaries: list[LabSummary]) -> None:
        self._summaries = summaries
        self._render_strip()


# ---------------------------------------------------------------------------
# PaginatedTranscript — page-block scrolling chat transcript
# ---------------------------------------------------------------------------

_DIVIDER_WIDTH = 60  # width of question divider line


class PaginatedTranscript(VerticalScroll):
    """Scrollable chat transcript with viewport-sized block paging.

    Each "block" is exactly viewport_height lines tall. Question blocks are
    padded with blank lines to fill the viewport. Reply blocks are split at
    paragraph boundaries and padded similarly.

    key_pageup / key_pagedown snap to block anchors.
    append_question / append_reply add new blocks to the end.
    """

    DEFAULT_CSS = """
    PaginatedTranscript {
        width: 1fr;
        height: 1fr;
        background: #1a1a2e;
        color: #cdd6f4;
        padding: 0 1;
    }
    """

    # Reserve 4 lines for: status bar (1) + input border-top (1) + input (1) + input border-bottom (1)
    _RESERVED_LINES = 4

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._blocks: list[Static] = []   # one Static widget per block
        self._block_index: int = 0        # index of the "current" block (for paging)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @property
    def _viewport_height(self) -> int:
        """Usable lines per block (container height minus reserved chrome)."""
        h = self.content_size.height or self.size.height or 20
        return max(5, h - self._RESERVED_LINES)

    def _pad_to_block(self, lines: list[str]) -> list[str]:
        """Return lines padded with blank lines to exactly _viewport_height."""
        vh = self._viewport_height
        result = list(lines)
        while len(result) < vh:
            result.append("")
        return result

    def _split_paragraphs(self, text: str) -> list[str]:
        """Split text on blank lines, returning non-empty paragraph strings."""
        paras: list[str] = []
        current: list[str] = []
        for line in text.splitlines():
            if line.strip() == "":
                if current:
                    paras.append("\n".join(current))
                    current = []
            else:
                current.append(line)
        if current:
            paras.append("\n".join(current))
        return paras

    def _make_block_widget(self, lines: list[str]) -> Static:
        text = "\n".join(self._pad_to_block(lines))
        return Static(text, markup=False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append_question(self, text: str) -> None:
        """Append a question block (viewport-tall) and auto-scroll to it."""
        divider = "─" * _DIVIDER_WIDTH
        lines = [f"{divider[:4]} Q: {text} {divider}"[:_DIVIDER_WIDTH + 10]]
        widget = self._make_block_widget(lines)
        self._blocks.append(widget)
        self.mount(widget)
        self._block_index = len(self._blocks) - 1
        self.scroll_to_widget(widget, top=True, animate=False)

    def append_reply(self, markdown_text: str) -> None:
        """Append one or more reply blocks split at paragraph boundaries."""
        vh = self._viewport_height
        paras = self._split_paragraphs(markdown_text)
        if not paras:
            paras = ["(empty reply)"]

        all_block_widgets: list[Static] = []
        current_lines: list[str] = []
        first_block = True

        for para in paras:
            para_lines = para.splitlines()
            # If this paragraph alone exceeds viewport, split at line boundaries
            if len(para_lines) > vh:
                for chunk_start in range(0, len(para_lines), vh):
                    chunk = para_lines[chunk_start : chunk_start + vh]
                    if current_lines:
                        # flush current
                        w = self._make_block_widget(current_lines)
                        all_block_widgets.append(w)
                        current_lines = []
                    header = ["agent:"] if first_block and not all_block_widgets else []
                    w = self._make_block_widget(header + chunk)
                    all_block_widgets.append(w)
                    first_block = False
                continue

            # Would adding this paragraph overflow the current block?
            needed = len(current_lines) + len(para_lines) + (1 if current_lines else 0)
            if current_lines and needed > vh:
                # flush current block
                w = self._make_block_widget(current_lines)
                all_block_widgets.append(w)
                first_block = False
                current_lines = []

            if not current_lines and first_block and not all_block_widgets:
                current_lines.append("agent:")
            if current_lines:
                current_lines.append("")  # paragraph gap
            current_lines.extend(para_lines)

        # flush remaining
        if current_lines:
            w = self._make_block_widget(current_lines)
            all_block_widgets.append(w)

        if not all_block_widgets:
            all_block_widgets.append(self._make_block_widget(["agent:", "(empty reply)"]))

        first_new_idx = len(self._blocks)
        for w in all_block_widgets:
            self._blocks.append(w)
            self.mount(w)

        # Auto-scroll so the agent's first reply block is at the top of the
        # viewport — director just asked, now they want to read the answer.
        # PageUp jumps back to the question block (still snap-aligned).
        if first_new_idx < len(self._blocks):
            self._block_index = first_new_idx
            self.scroll_to_widget(self._blocks[first_new_idx], top=True, animate=False)

    def clear_transcript(self) -> None:
        """Remove all blocks."""
        for w in self._blocks:
            w.remove()
        self._blocks = []
        self._block_index = 0

    # ------------------------------------------------------------------
    # Paging key handlers
    # ------------------------------------------------------------------

    def key_pageup(self) -> None:
        if not self._blocks:
            return
        new_idx = max(0, self._block_index - 1)
        self._block_index = new_idx
        self.scroll_to_widget(self._blocks[new_idx], top=True, animate=False)

    def key_pagedown(self) -> None:
        if not self._blocks:
            return
        new_idx = min(len(self._blocks) - 1, self._block_index + 1)
        self._block_index = new_idx
        self.scroll_to_widget(self._blocks[new_idx], top=True, animate=False)


# ---------------------------------------------------------------------------
# Director Chat pane
# ---------------------------------------------------------------------------

_CHAT_PLACEHOLDER_CHIEF = (
    "Talk to the Chief of Staff.\n"
    "Try: 'what needs my attention?'"
)

_MAX_HISTORY_TURNS = 6  # purge to last N turns to keep context bounded

_SCOPE_KEY_CHIEF = "chief"


def _lab_scope_key(lab_id: str) -> str:
    return f"lab:{lab_id}"


class DirectorChat(Vertical):
    """Right pane: paginated transcript + input field.

    Scope model:
      _scope: {"kind": "chief"} or {"kind": "lab", "lab_id": str, "lab_root": Path}
      _histories: dict[str, list[dict]]  — keyed by _SCOPE_KEY_CHIEF or "lab:<id>"
      _transcripts: dict[str, list[Static]]  — per-scope block widgets
    """

    DEFAULT_CSS = """
    DirectorChat {
        width: 1fr;
        border: round #888888;
        background: #1a1a2e;
        color: #cdd6f4;
        height: 1fr;
    }

    DirectorChat > PaginatedTranscript {
        height: 1fr;
        background: #1a1a2e;
        color: #cdd6f4;
        padding: 0 1;
    }

    DirectorChat > #chat-status {
        height: 1;
        background: #1e1e2e;
        color: #888888;
        padding: 0 1;
    }

    DirectorChat > #chat-scope-hint {
        height: 1;
        background: #1e1e2e;
        color: #555577;
        padding: 0 1;
    }

    DirectorChat > Input {
        height: 3;
        background: #16213e;
        border: round #555577;
        color: #e2e2e2;
    }
    """

    def __init__(self, federation_root: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self._federation_root = federation_root
        # Per-scope histories: {"chief": [...], "lab:foo": [...]}
        self._histories: dict[str, list[dict]] = {}
        self._thinking = False
        # Current scope
        self._scope: dict = {"kind": "chief"}

    # ------------------------------------------------------------------
    # Compose + mount
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield PaginatedTranscript(id="chat-log")
        yield Static("", id="chat-status")
        yield Static("", id="chat-scope-hint")
        yield Input(placeholder="Ask the Chief of Staff...", id="chat-input")

    def on_mount(self) -> None:
        self._apply_scope_ui()

    # ------------------------------------------------------------------
    # Focus indicator — show hint in app sub_title while chat is active
    # ------------------------------------------------------------------

    def on_focus(self, event) -> None:
        """Any child within DirectorChat gaining focus triggers this bubble."""
        try:
            self.app.sub_title = "[chat] enter Send  shift+tab Leave"
        except Exception:
            pass

    def on_blur(self, event) -> None:
        """Fired when focus leaves DirectorChat entirely."""
        try:
            self.app.sub_title = ""
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Scope management
    # ------------------------------------------------------------------

    def _scope_key(self) -> str:
        if self._scope["kind"] == "chief":
            return _SCOPE_KEY_CHIEF
        return _lab_scope_key(self._scope["lab_id"])

    def _current_history(self) -> list[dict]:
        return self._histories.setdefault(self._scope_key(), [])

    def _apply_scope_ui(self) -> None:
        """Update title, hint, input placeholder, and transcript to match current scope."""
        transcript: PaginatedTranscript = self.query_one("#chat-log", PaginatedTranscript)
        hint: Static = self.query_one("#chat-scope-hint", Static)
        chat_input: Input = self.query_one("#chat-input", Input)

        if self._scope["kind"] == "chief":
            self.border_title = "Director Chat — Chief of Staff"
            hint.update("")
            chat_input.placeholder = "Ask the Chief of Staff..."
            self._render_transcript(transcript, _SCOPE_KEY_CHIEF, _CHAT_PLACEHOLDER_CHIEF)
        else:
            lab_id = self._scope["lab_id"]
            self.border_title = f"Director Chat — {lab_id} Lab"
            hint.update(
                "Esc to return to Chief of Staff, or collapse the lab in the table"
            )
            chat_input.placeholder = f"Ask the {lab_id} lab agent..."
            self._render_transcript(
                transcript,
                _lab_scope_key(lab_id),
                f"Talk to the agent for {lab_id}. Try: 'walk me through your claws'",
            )

        # Visual ping: briefly flash .scope-changed class so the border lights up
        self.add_class("scope-changed")
        self.set_timer(1.5, lambda: self.remove_class("scope-changed"))

    def _render_transcript(
        self,
        transcript: "PaginatedTranscript",
        scope_key: str,
        placeholder: str,
    ) -> None:
        """Clear the transcript and render the history for the given scope."""
        transcript.clear_transcript()
        history = self._histories.get(scope_key, [])
        if not history:
            transcript.mount(Static(placeholder, markup=False))
        else:
            # Re-render conversation turns
            for i in range(0, len(history), 2):
                if i < len(history):
                    transcript.append_question(history[i]["content"])
                if i + 1 < len(history):
                    transcript.append_reply(history[i + 1]["content"])

    def set_scope_chief(self) -> None:
        """Switch scope to the Chief of Staff. Preserves per-scope histories."""
        if self._scope["kind"] == "chief":
            return  # already there
        self._scope = {"kind": "chief"}
        self._apply_scope_ui()

    def set_scope_lab(self, lab_id: str, lab_root: Path) -> None:
        """Switch scope to a specific lab agent. Preserves per-scope histories."""
        current_key = self._scope_key()
        new_key = _lab_scope_key(lab_id)
        if current_key == new_key:
            return  # already there
        self._scope = {"kind": "lab", "lab_id": lab_id, "lab_root": lab_root}
        self._apply_scope_ui()

    # ------------------------------------------------------------------
    # Send message
    # ------------------------------------------------------------------

    async def send_message(self, text: str) -> None:
        """Handle a user message: display it, call the scoped agent, display reply."""
        if self._thinking:
            return

        text = text.strip()
        if not text:
            return

        transcript: PaginatedTranscript = self.query_one("#chat-log", PaginatedTranscript)
        status: Static = self.query_one("#chat-status", Static)
        chat_input: Input = self.query_one("#chat-input", Input)

        # Display user question block
        transcript.append_question(text)

        # Set status
        self._thinking = True
        status.update("thinking...")
        chat_input.disabled = True

        # Build bounded history slice
        history = self._current_history()
        history_slice = history[-_MAX_HISTORY_TURNS:]

        # Route to the correct agent
        try:
            if self._scope["kind"] == "chief":
                from lab_tui.chat_agents import ask_chief_of_staff
                reply = await ask_chief_of_staff(
                    self._federation_root,
                    history_slice,
                    text,
                )
            else:
                from lab_tui.chat_agents import ask_lab_agent
                reply = await ask_lab_agent(
                    self._scope["lab_root"],
                    self._scope["lab_id"],
                    history_slice,
                    text,
                )
        except Exception as exc:
            reply = f"(agent error: {exc})"

        # Update scoped history
        history.append({"role": "human", "content": text})
        history.append({"role": "agent", "content": reply})

        # Display reply blocks
        transcript.append_reply(reply)

        # Clear status and re-enable input
        self._thinking = False
        status.update("")
        chat_input.disabled = False
        chat_input.focus()

    # ------------------------------------------------------------------
    # Accessors for tests / serializers
    # ------------------------------------------------------------------

    @property
    def _history(self) -> list[dict]:
        """Return current-scope history (backward compat for tests)."""
        return self._current_history()

    def get_transcript_text(self) -> str:
        """Return a plain-text dump of current-scope conversation history."""
        lines: list[str] = []
        for turn in self._current_history():
            prefix = "> human:" if turn["role"] == "human" else "agent:"
            lines.append(f"{prefix} {turn['content']}")
        return "\n".join(lines) if lines else "(empty)"

    def prefill_input(self, text: str) -> None:
        """Focus the chat input and pre-fill it with text (does not submit)."""
        chat_input: Input = self.query_one("#chat-input", Input)
        chat_input.value = text
        chat_input.focus()
        # Move cursor to end
        chat_input.action_end()


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

class CockpitApp(App):
    """Studio Cockpit — federation home screen."""

    CSS = """
    Screen { background: #1a1a2e; }

    #lab-panel {
        width: 1fr;
        height: 1fr;
    }

    #lab-header-strip {
        height: 1;
    }

    #lab-list {
        height: 1fr;
    }

    #main-body {
        height: 1fr;
    }

    #chat-pane {
        width: 1fr;
        height: 1fr;
    }

    LabList {
        border: tall $primary;
    }

    LabList:focus-within {
        border: heavy $accent;
    }

    DirectorChat {
        border: tall $primary;
    }

    DirectorChat:focus-within {
        border: heavy $accent;
    }

    .scope-changed {
        border: heavy $boost;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("tab", "focus_chat", "Focus chat"),
        Binding("shift+tab", "focus_labs", "Focus labs"),
        Binding("enter", "toggle_expand", "Expand/Collapse"),
        Binding("c", "chat_about_lab", "Chat about lab"),
        Binding("s", "spawn_claw", "Spawn"),
        Binding("n", "new_lab", "New lab"),
        Binding("d", "archive_lab", "Archive lab"),
        Binding("p", "promote_claw", "Promote"),
        Binding("a", "archive_claw", "Archive claw"),
        Binding("v", "view_result", "View result"),
        Binding("escape", "collapse_all", "Collapse"),
        Binding("?", "show_help", "Help"),
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
            with Vertical(id="lab-panel"):
                yield LabHeaderStrip([], self._federation_root, id="lab-header-strip")
                yield LabList([], id="lab-list")
            yield DirectorChat(self._federation_root, id="chat-pane")
        yield Footer()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self.title = f"Studio Cockpit — {self._federation_root.name}"
        self._load_data()

    def _load_data(self) -> None:
        self._summaries = discover_labs(self._federation_root)
        self._populate_list()

        count = len(self._summaries)
        self.sub_title = (
            f"{count} lab{'s' if count != 1 else ''} — "
            f"{self._federation_root}"
        )

    def _populate_list(self) -> None:
        lab_list: LabList = self.query_one("#lab-list", LabList)
        header_strip: LabHeaderStrip = self.query_one("#lab-header-strip", LabHeaderStrip)

        # Check if we need to rebuild (different number of labs)
        existing_rows = list(lab_list.query(LabRow))
        if len(existing_rows) == len(self._summaries):
            # Refresh in place
            lab_list.refresh_all(self._summaries)
        else:
            # Remove all and recreate
            for row in existing_rows:
                row.remove()
            for i, summary in enumerate(self._summaries):
                lab_list.mount(LabRow(summary, id=f"lab-row-{i}"))
            rows = list(lab_list.query(LabRow))
            if rows:
                rows[0].focus()

        header_strip.refresh_strip(self._summaries)

    # ------------------------------------------------------------------
    # Focus-swap actions (Tab / Shift-Tab)
    # ------------------------------------------------------------------

    def action_focus_chat(self) -> None:
        """Move focus to the chat input (Tab)."""
        chats = list(self.query(DirectorChat))
        if chats:
            chat = chats[0]
            try:
                chat_input = chat.query_one("#chat-input")
                chat_input.focus()
            except Exception:
                pass

    def action_focus_labs(self) -> None:
        """Move focus back to the lab list (Shift-Tab)."""
        lab_lists = list(self.query(LabList))
        if lab_lists:
            ll = lab_lists[0]
            rows = list(ll.query(LabRow))
            if rows:
                selected = next((r for r in rows if r.has_focus), None) or rows[0]
                selected.focus()

    # ------------------------------------------------------------------
    # Scope auto-switch — react to LabList expand/collapse messages
    # ------------------------------------------------------------------

    def on_lab_list_lab_expanded(self, event: LabList.LabExpanded) -> None:
        """Switch chat scope to the expanded lab."""
        chat: DirectorChat = self.query_one("#chat-pane", DirectorChat)
        chat.set_scope_lab(event.lab_id, event.lab_root)

    def on_lab_list_lab_collapsed(self, event: LabList.LabCollapsed) -> None:
        """Switch chat scope back to Chief of Staff when all rows are collapsed."""
        chat: DirectorChat = self.query_one("#chat-pane", DirectorChat)
        chat.set_scope_chief()

    # ------------------------------------------------------------------
    # Input handler — routes Enter from the chat input
    # ------------------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter in the chat input field. Fire-and-forget to keep UI responsive."""
        chat: DirectorChat = self.query_one("#chat-pane", DirectorChat)
        text = event.value.strip()
        event.input.clear()
        if text:
            # Spawn as worker so the agent call doesn't block the event loop's
            # rendering or other key handlers (PageUp/PageDown, Tab, etc).
            chat.run_worker(chat.send_message(text), exclusive=True)

    # ------------------------------------------------------------------
    # Key routing — nav keys drive LabList when chat is not focused
    # ------------------------------------------------------------------

    def on_key(self, event) -> None:
        """Route j/k to the lab list or claw list when chat-input is not focused.

        If the focused LabRow is expanded, j/k navigate within the claw list.
        If not expanded (or no claws), j/k navigate between lab rows.
        """
        # When a modal is pushed, the screen stack has >1 screen.  The modal
        # handles its own keys; this handler must not try to query widgets that
        # only exist on the base screen.
        if len(self.screen_stack) > 1:
            return

        chat_input: Input = self.query_one("#chat-input", Input)
        if chat_input.has_focus:
            # Route PageUp/PageDown to the transcript even while typing,
            # so the director can scroll while reading the agent's reply.
            if event.key in ("pageup", "page_up"):
                self.query_one("#chat-log", PaginatedTranscript).key_pageup()
                event.stop()
            elif event.key in ("pagedown", "page_down"):
                self.query_one("#chat-log", PaginatedTranscript).key_pagedown()
                event.stop()
            return  # other keys: let chat input handle them

        lab_list: LabList = self.query_one("#lab-list", LabList)

        if event.key in ("j", "down", "k", "up"):
            delta = 1 if event.key in ("j", "down") else -1
            focused_row = lab_list.focused_row()
            # If expanded and has claws, navigate within claws
            if focused_row and focused_row.expanded and focused_row._summary.bundles:
                focused_row.move_claw_selection(delta)
            else:
                lab_list.move_focus(delta)
            event.stop()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_refresh(self) -> None:
        self._load_data()
        self.notify("Refreshed", timeout=1.5)

    def action_toggle_expand(self) -> None:
        """Toggle expansion of the focused lab row."""
        chat_input: Input = self.query_one("#chat-input", Input)
        if chat_input.has_focus:
            return  # Enter in chat submits, not toggle

        lab_list: LabList = self.query_one("#lab-list", LabList)
        lab_list.toggle_focused()

    def action_collapse_all(self) -> None:
        """Collapse all expanded rows."""
        lab_list: LabList = self.query_one("#lab-list", LabList)
        lab_list.collapse_all()

    def action_chat_about_lab(self) -> None:
        """Pre-fill the chat input with 'Tell me about <lab-id>' and focus it."""
        chat_input: Input = self.query_one("#chat-input", Input)
        if chat_input.has_focus:
            return  # already in chat

        lab_list: LabList = self.query_one("#lab-list", LabList)
        focused_row = lab_list.focused_row()
        if not focused_row:
            return

        chat: DirectorChat = self.query_one("#chat-pane", DirectorChat)
        chat.prefill_input(f"Tell me about {focused_row.lab_id}")

    def _focused_lab_row(self) -> "LabRow | None":
        lab_list: LabList = self.query_one("#lab-list", LabList)
        return lab_list.focused_row()

    @work
    async def action_spawn_claw(self) -> None:
        """Open SpawnClawModal for the focused lab."""
        from lab_tui.modals import SpawnClawModal
        row = self._focused_lab_row()
        if not row:
            self.notify("No lab selected", severity="warning")
            return

        result = await self.push_screen_wait(SpawnClawModal(row._summary))
        if result is None:
            return

        orientation_id, role = result
        res = spawn_dry_run_claw(row._summary.lab_root, orientation_id, role)
        if res.success:
            self.notify(res.message, timeout=3)
            self.action_refresh()
        else:
            self.notify(res.message, severity="error", timeout=5)

    @work
    async def action_new_lab(self) -> None:
        """Open NewLabModal to create a new lab in the federation."""
        from lab_tui.modals import NewLabModal
        result = await self.push_screen_wait(NewLabModal(self._federation_root))
        if result is None:
            return

        res = create_lab(
            self._federation_root,
            slug=result["slug"],
            kind=result["kind"],
            title=result["title"],
            objective=result["objective"],
        )
        if res.success:
            self.notify(res.message, timeout=3)
            self.action_refresh()
        else:
            self.notify(res.message, severity="error", timeout=5)

    @work
    async def action_archive_lab(self) -> None:
        """Open ConfirmModal to archive (soft-delete) the focused lab."""
        from lab_tui.modals import ConfirmModal
        row = self._focused_lab_row()
        if not row:
            self.notify("No lab selected", severity="warning")
            return

        lab_id = row.lab_id
        confirmed = await self.push_screen_wait(
            ConfirmModal(
                title=f"Archive lab '{lab_id}'?",
                message="The lab will be moved to .archive/ (recoverable).",
            )
        )
        if not confirmed:
            return

        res = archive_lab(self._federation_root, lab_id)
        if res.success:
            self.notify(res.message, timeout=3)
            self.action_refresh()
        else:
            self.notify(res.message, severity="error", timeout=5)

    @work
    async def action_promote_claw(self) -> None:
        """Apply promotion_recommendation decision to the selected claw."""
        from lab_tui.modals import ConfirmModal
        row = self._focused_lab_row()
        if not row:
            self.notify("No lab selected", severity="warning")
            return
        if not row.expanded:
            self.notify("Expand the lab row first (Enter)", severity="warning")
            return

        claw = row.selected_claw()
        if not claw:
            self.notify("No claws in this lab", severity="warning")
            return

        outcome = claw.meta.get("promotion_recommendation", "")
        if not outcome:
            self.notify("No promotion_recommendation in claw meta", severity="warning")
            return

        confirmed = await self.push_screen_wait(
            ConfirmModal(
                title=f"Apply outcome '{outcome}' to {claw.bundle_id}?",
                message=f"This will write a decision.json with outcome='{outcome}'.",
            )
        )
        if not confirmed:
            return

        claw_dir = row._summary.lab_root / ".claws" / claw.bundle_id
        res = apply_decision(claw_dir, outcome)
        if res.success:
            self.notify(res.message, timeout=3)
            self.action_refresh()
        else:
            self.notify(res.message, severity="error", timeout=5)

    @work
    async def action_archive_claw(self) -> None:
        """Soft-delete the selected claw to .archive/."""
        from lab_tui.modals import ConfirmModal
        row = self._focused_lab_row()
        if not row:
            self.notify("No lab selected", severity="warning")
            return
        if not row.expanded:
            self.notify("Expand the lab row first (Enter)", severity="warning")
            return

        claw = row.selected_claw()
        if not claw:
            self.notify("No claws in this lab", severity="warning")
            return

        confirmed = await self.push_screen_wait(
            ConfirmModal(
                title=f"Archive claw '{claw.bundle_id}'?",
                message="The bundle will be moved to .claws/.archive/ (recoverable).",
            )
        )
        if not confirmed:
            return

        claw_dir = row._summary.lab_root / ".claws" / claw.bundle_id
        res = archive_claw(claw_dir)
        if res.success:
            self.notify(res.message, timeout=3)
            self.action_refresh()
        else:
            self.notify(res.message, severity="error", timeout=5)

    @work
    async def action_view_result(self) -> None:
        """Open ClawViewerModal to view result.md for the selected claw."""
        from lab_tui.modals import ClawViewerModal
        row = self._focused_lab_row()
        if not row:
            self.notify("No lab selected", severity="warning")
            return
        if not row.expanded:
            self.notify("Expand the lab row first (Enter)", severity="warning")
            return

        claw = row.selected_claw()
        if not claw:
            self.notify("No claws in this lab", severity="warning")
            return

        claw_dir = row._summary.lab_root / ".claws" / claw.bundle_id
        await self.push_screen_wait(ClawViewerModal(claw_dir))

    def action_show_help(self) -> None:
        self.notify(
            "j/k — move between labs (or claws when expanded)\n"
            "Enter — expand/collapse lab row\n"
            "c — pre-fill chat with selected lab\n"
            "s — spawn dry-run claw\n"
            "n — create new lab\n"
            "d — archive (soft-delete) selected lab\n"
            "p — promote selected claw (apply recommendation)\n"
            "a — archive selected claw\n"
            "v — view claw result.md\n"
            "Esc — collapse all\n"
            "r — refresh data\n"
            "q — quit",
            title="Cockpit Keybindings",
            timeout=10,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    CockpitApp().run()


if __name__ == "__main__":
    main()
