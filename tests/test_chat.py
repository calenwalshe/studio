"""tests/test_chat.py — tests for the Director Chat pane and director_agent module.

Fast tests (no subprocess):
  - test_render_lab_snapshot_includes_hello_lab

Slow tests (calls real claude subprocess, mark @pytest.mark.slow):
  - test_chat_pane_sends_and_receives

Run fast tests only:
    CGL_LAB_ROOT=examples/hello-lab studio/.venv/bin/pytest tests/test_chat.py -v -m "not slow"

Run all tests:
    CGL_LAB_ROOT=examples/hello-lab studio/.venv/bin/pytest tests/test_chat.py -v
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

HARNESS_ROOT = Path(__file__).resolve().parents[1]
_STUDIO_PATH = str(HARNESS_ROOT / "studio")
if _STUDIO_PATH not in sys.path:
    sys.path.insert(0, _STUDIO_PATH)

HELLO_LAB = HARNESS_ROOT / "examples" / "hello-lab"

# Set env so the cockpit module-level resolver doesn't abort at import
os.environ.setdefault("CGL_LAB_ROOT", str(HELLO_LAB))

from lab_tui.director_agent import render_lab_snapshot, is_long_form_request, build_prompt  # noqa: E402
from lab_tui.chat_agents import (  # noqa: E402
    render_federation_snapshot,
    render_lab_snapshot as render_lab_snapshot_deep,
    build_chief_prompt,
    build_lab_prompt,
    DELEGATE_RE,
    expand_delegations,
)

FEDERATION_DEMO = HARNESS_ROOT / "examples" / "federation-demo"
AGENT_INFRA = FEDERATION_DEMO / "agent-infra"


# ---------------------------------------------------------------------------
# Fast tests — no subprocess
# ---------------------------------------------------------------------------

def test_render_lab_snapshot_includes_hello_lab():
    """render_lab_snapshot must include the lab id, orientation id, claw id,
    and the first claim text from the fixture data."""
    snapshot = render_lab_snapshot(HELLO_LAB)

    # Lab id from .studio/lab.toml
    assert "hello-lab" in snapshot, f"'hello-lab' not found in snapshot:\n{snapshot}"

    # Orientation id from .studio/orientations.toml
    assert "orient-hello-lab-studio-exploration" in snapshot, (
        f"orientation id not found in snapshot:\n{snapshot}"
    )

    # Claw id (bundle directory name)
    assert "20260501-150000-scout-hello-lab" in snapshot, (
        f"claw id not found in snapshot:\n{snapshot}"
    )

    # First claim text from evidence.jsonl
    assert "Studio v0 uses tmux sessions" in snapshot, (
        f"first claim text not found in snapshot:\n{snapshot}"
    )


def test_render_lab_snapshot_includes_recommendation():
    """Snapshot should include the promotion recommendation."""
    snapshot = render_lab_snapshot(HELLO_LAB)
    assert "keep_evidence" in snapshot


def test_render_lab_snapshot_includes_claim_count():
    """Snapshot should mention the claim count for the bundle."""
    snapshot = render_lab_snapshot(HELLO_LAB)
    # claims=3 should appear in the bundle summary line
    assert "claims=3" in snapshot


def test_render_lab_snapshot_nonexistent_root(tmp_path):
    """render_lab_snapshot on a missing path returns a graceful message."""
    snapshot = render_lab_snapshot(tmp_path / "does_not_exist")
    assert "no labs found" in snapshot


def test_is_long_form_request_detects_phrases():
    """is_long_form_request should detect all trigger phrases and reject normal queries."""
    assert is_long_form_request("give me a detailed report") is True
    assert is_long_form_request("let's do a deep dive") is True
    assert is_long_form_request("full report please") is True
    assert is_long_form_request("I want everything you have on this") is True
    assert is_long_form_request("give me a deeper report") is True
    assert is_long_form_request("comprehensive breakdown") is True
    # Normal queries should not trigger long-form
    assert is_long_form_request("what's the status?") is False
    assert is_long_form_request("what needs my attention?") is False
    assert is_long_form_request("is cgl-publish shippable?") is False


def test_build_prompt_includes_default_mode_directive():
    """build_prompt with a normal question should include the DEFAULT MODE directive."""
    prompt = build_prompt(HELLO_LAB, [], "what needs my attention?")
    assert "DEFAULT MODE" in prompt
    assert "LONG-FORM MODE" not in prompt


def test_build_prompt_includes_long_form_directive():
    """build_prompt with a trigger phrase should include the LONG-FORM MODE directive."""
    prompt = build_prompt(HELLO_LAB, [], "give me a detailed report on cgl-publish")
    assert "LONG-FORM MODE ACTIVE" in prompt
    assert "DEFAULT MODE" not in prompt


# ---------------------------------------------------------------------------
# PaginatedTranscript tests
# ---------------------------------------------------------------------------

def test_paginated_transcript_blocks():
    """PaginatedTranscript: paragraph splitting and block logic is correct.

    Tests the internal helpers without mounting a live Textual app.
    """
    from lab_tui.cockpit import PaginatedTranscript  # noqa: E402

    transcript = PaginatedTranscript.__new__(PaginatedTranscript)
    # Initialise the two attributes we care about (no Textual Widget.__init__)
    transcript._blocks = []
    transcript._block_index = 0

    # --- _split_paragraphs ---
    text = "Para one.\n\nPara two.\n\nPara three."
    paras = transcript._split_paragraphs(text)
    assert len(paras) == 3, f"Expected 3 paragraphs, got {len(paras)}: {paras}"
    assert paras[0] == "Para one."
    assert paras[2] == "Para three."

    # Empty-line-only input returns empty list
    assert transcript._split_paragraphs("") == []
    assert transcript._split_paragraphs("\n\n\n") == []

    # --- _pad_to_block ---
    # Force a small viewport height via monkeypatching the property
    class _FixedViewport(PaginatedTranscript):
        @property
        def _viewport_height(self):
            return 5

    tv = _FixedViewport.__new__(_FixedViewport)
    tv._blocks = []
    tv._block_index = 0

    padded = tv._pad_to_block(["line1", "line2"])
    assert len(padded) == 5, f"Expected 5 lines after padding, got {len(padded)}"
    assert padded[0] == "line1"
    assert padded[2] == ""   # padding

    # Exact fit — no extra lines
    padded_exact = tv._pad_to_block(["a", "b", "c", "d", "e"])
    assert len(padded_exact) == 5

    # Overflow — returns as-is (no truncation)
    padded_over = tv._pad_to_block(["a", "b", "c", "d", "e", "f"])
    assert len(padded_over) == 6

    # --- block count after simulated append sequence ---
    # Use _FixedViewport so viewport height is controlled
    class _MockStatic:
        """Stub for Static widget — we don't need a real Textual widget."""
        def __init__(self, text, markup=False):
            self.text = text

        def scroll_visible(self):
            pass

    import unittest.mock as mock

    with mock.patch("lab_tui.cockpit.Static", _MockStatic):
        fv = _FixedViewport.__new__(_FixedViewport)
        fv._blocks = []
        fv._block_index = 0

        # Patch mount to just append the widget to a list we track
        mounted = []

        def fake_mount(w):
            mounted.append(w)

        fv.mount = fake_mount
        # scroll_to_widget requires a fully mounted Textual widget; stub it out.
        fv.scroll_to_widget = lambda widget, top=False, animate=True: None

        # append_question adds 1 block
        fv.append_question("What needs my attention?")
        assert len(fv._blocks) == 1, f"Expected 1 block after question, got {len(fv._blocks)}"
        assert fv._block_index == 0

        # append_reply with 3 short paragraphs on a viewport_height=5 terminal
        # Each paragraph is 1 line; all 3 fit in one block (3 lines < 5)
        reply = "Para one.\n\nPara two.\n\nPara three."
        fv.append_reply(reply)
        assert len(fv._blocks) >= 2, f"Expected >= 2 blocks after reply, got {len(fv._blocks)}"
        # Block index should point to the FIRST REPLY block (block 1) — director
        # just asked, now they want to read the answer at top of viewport.
        # PageUp from there returns to the question block.
        assert fv._block_index == 1, f"Expected block_index=1 (first reply block), got {fv._block_index}"

        # key_pagedown advances index (if more blocks exist)
        initial_idx = fv._block_index
        fv.key_pagedown()
        # if only 2 blocks total, stays at 1
        assert fv._block_index >= initial_idx

        # key_pageup retreats index
        after_down = fv._block_index
        fv.key_pageup()
        assert fv._block_index <= after_down, "key_pageup should not advance"
        assert fv._block_index >= 0


# ---------------------------------------------------------------------------
# New tiered-agent tests
# ---------------------------------------------------------------------------

def test_render_federation_snapshot_includes_all_labs():
    """render_federation_snapshot must include all 5 lab ids from federation-demo."""
    snapshot = render_federation_snapshot(FEDERATION_DEMO)
    expected_labs = ["agent-infra", "cgl-publish", "distribution-engine", "hello-lab", "surface-snake"]
    for lab_id in expected_labs:
        assert lab_id in snapshot, f"'{lab_id}' not found in federation snapshot:\n{snapshot[:500]}"


def test_render_lab_snapshot_full_evidence():
    """render_lab_snapshot (deep) must include all 3 claws and ALL claim text for agent-infra."""
    snapshot = render_lab_snapshot_deep(AGENT_INFRA)

    # All 3 claw bundle ids
    expected_claws = [
        "20260428-103000-scout-agent-infra",
        "20260429-141500-researcher-agent-infra",
        "20260430-080000-scout-agent-infra",
    ]
    for claw_id in expected_claws:
        assert claw_id in snapshot, f"'{claw_id}' not found in deep snapshot"

    # Full claim text — not just first lines
    # claim-001 from 20260428 claw
    assert "Aider uses a persistent git-worktree-per-session model" in snapshot
    # claim-002 from 20260428 claw
    assert "Crystal uses a message-passing supervisor model" in snapshot
    # claim-003 from 20260428 claw
    assert "awesome-cli-coding-agents list tracks 23 distinct harnesses" in snapshot


def test_build_lab_prompt_includes_lab_id():
    """build_lab_prompt must substitute lab_id into the system prompt."""
    prompt = build_lab_prompt(AGENT_INFRA, "agent-infra", [], "walk me through your claws")
    # LAB_AGENT_SYSTEM_TEMPLATE has {lab_id} substituted
    assert "Lab Agent for agent-infra" in prompt, "lab_id substitution missing from prompt"
    assert "LAB SNAPSHOT: agent-infra" in prompt


def test_build_chief_prompt_uses_federation_snapshot():
    """build_chief_prompt must include the federation snapshot in the prompt."""
    prompt = build_chief_prompt(FEDERATION_DEMO, [], "what needs my attention?")
    assert "FEDERATION SNAPSHOT" in prompt
    # The snapshot content for at least one lab should appear
    assert "agent-infra" in prompt
    assert "DEFAULT MODE" in prompt


# ---------------------------------------------------------------------------
# Delegation tests
# ---------------------------------------------------------------------------

def test_delegate_re_matches():
    """DELEGATE_RE should match well-formed {{delegate:lab-id:question}} markers."""
    import re

    text = "Some preamble.\n{{delegate:agent-infra:What does the convergent pattern mean?}}\nMore text."
    matches = list(DELEGATE_RE.finditer(text))
    assert len(matches) == 1, f"Expected 1 match, got {len(matches)}"
    m = matches[0]
    assert m.group(1) == "agent-infra"
    assert "convergent pattern" in m.group(2)

    # Multiple markers
    multi = (
        "{{delegate:agent-infra:Question one?}}\n"
        "{{delegate:cgl-publish:Question two?}}"
    )
    multi_matches = list(DELEGATE_RE.finditer(multi))
    assert len(multi_matches) == 2
    assert multi_matches[0].group(1) == "agent-infra"
    assert multi_matches[1].group(1) == "cgl-publish"

    # Should NOT match if lab-id is malformed (starts with digit)
    bad = "{{delegate:1bad-lab:question}}"
    assert not list(DELEGATE_RE.finditer(bad)), "Should not match lab-id starting with digit"


def test_expand_delegations_no_markers_returns_unchanged():
    """expand_delegations returns the original string when there are no markers."""
    import asyncio

    text = "No delegation markers here. Plain response."
    result = asyncio.run(
        expand_delegations(text, FEDERATION_DEMO)
    )
    assert result == text, f"Expected unchanged text, got: {result!r}"


def test_expand_delegations_handles_unknown_lab():
    """expand_delegations replaces unknown lab markers with a graceful failure message."""
    import asyncio

    text = "Intro.\n{{delegate:nonexistent-lab:What is this?}}\nOutro."
    result = asyncio.run(
        expand_delegations(text, FEDERATION_DEMO)
    )
    assert "delegation failed" in result, f"Expected 'delegation failed' in result: {result!r}"
    assert "nonexistent-lab" in result
    # Original intro and outro should be preserved
    assert "Intro." in result
    assert "Outro." in result


def test_chief_system_includes_top_priority_rule():
    from studio.lab_tui.chat_agents import CHIEF_OF_STAFF_SYSTEM
    assert "Top priority:" in CHIEF_OF_STAFF_SYSTEM
    assert "TRIAGE QUESTIONS" in CHIEF_OF_STAFF_SYSTEM


# ---------------------------------------------------------------------------
# Session persistence tests — fast, no LLM
# ---------------------------------------------------------------------------

def test_get_or_create_session_assigns_uuid(tmp_path, monkeypatch):
    """get_or_create_session must assign a UUID to a new scope key."""
    monkeypatch.setenv("CGL_STATE_DIR", str(tmp_path))
    from lab_tui.chat_sessions import get_or_create_session

    session = get_or_create_session("chief", tmp_path, "system prompt text")
    assert session.session_uuid, "session_uuid must be non-empty"
    assert session.is_new is True, "first call must mark session as new"
    assert session.scope_key == "chief"


def test_get_or_create_session_persists_across_calls(tmp_path, monkeypatch):
    """Calling get_or_create_session twice with the same scope key returns the same UUID."""
    monkeypatch.setenv("CGL_STATE_DIR", str(tmp_path))
    from lab_tui.chat_sessions import get_or_create_session

    s1 = get_or_create_session("chief", tmp_path, "system prompt")
    s2 = get_or_create_session("chief", tmp_path, "system prompt")
    assert s1.session_uuid == s2.session_uuid, (
        f"Expected same UUID on second call, got {s1.session_uuid!r} vs {s2.session_uuid!r}"
    )


def test_reset_session_forces_new_uuid(tmp_path, monkeypatch):
    """reset_session must cause the next get_or_create_session to produce a new UUID."""
    monkeypatch.setenv("CGL_STATE_DIR", str(tmp_path))
    from lab_tui.chat_sessions import get_or_create_session, reset_session

    s1 = get_or_create_session("chief", tmp_path, "system prompt")
    old_uuid = s1.session_uuid

    reset_ok = reset_session("chief")
    assert reset_ok is True, "reset_session must return True when scope key existed"

    s2 = get_or_create_session("chief", tmp_path, "system prompt")
    assert s2.session_uuid != old_uuid, (
        "After reset, get_or_create_session must assign a new UUID"
    )
    assert s2.is_new is True


# ---------------------------------------------------------------------------
# Slow test — calls real claude subprocess
# ---------------------------------------------------------------------------

@pytest.mark.slow
async def test_chat_pane_sends_and_receives():
    """Launch CockpitApp in test mode, type a message, assert transcript has both labels."""
    from lab_tui.cockpit import CockpitApp  # noqa: E402

    user_msg = "what needs my attention?"

    async with CockpitApp().run_test(size=(120, 40)) as pilot:
        # Give the app time to mount
        await pilot.pause()

        # Focus the chat input
        await pilot.click("#chat-input")
        await pilot.pause()

        # Type the question
        await pilot.type(user_msg)
        await pilot.pause()

        # Submit
        await pilot.press("enter")

        # Wait for agent response (up to 90s in 1s increments)
        chat = pilot.app.query_one("#chat-pane")
        for _ in range(90):
            await pilot.pause(delay=1.0)
            if not chat._thinking:
                break

        # Inspect history
        history = chat._history
        assert len(history) >= 2, f"Expected at least 2 history turns, got {len(history)}"

        human_turns = [t for t in history if t["role"] == "human"]
        agent_turns = [t for t in history if t["role"] == "agent"]

        assert human_turns, "No human turns in history"
        assert agent_turns, "No agent turns in history"

        # Agent should mention hello-lab since the snapshot includes it
        agent_reply = agent_turns[0]["content"]
        assert "hello-lab" in agent_reply.lower(), (
            f"Expected 'hello-lab' in agent reply:\n{agent_reply}"
        )

        # Verify transcript renders both labels
        transcript = chat.get_transcript_text()
        assert "> human:" in transcript
        assert "agent:" in transcript
