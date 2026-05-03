"""director_agent.py — backward-compat shim.

New code should import from chat_agents directly.
This module re-exports the names that existing tests and cockpit code depend on.
"""
from __future__ import annotations

# Re-export everything tests/cockpit currently imports from this module
from lab_tui.chat_agents import (  # noqa: F401
    ask_chief_of_staff as ask_director,
    build_chief_prompt as build_prompt,
    is_long_form_request,
    render_federation_snapshot as render_lab_snapshot,
    LONG_FORM_TRIGGERS,
    CHIEF_OF_STAFF_SYSTEM as DIRECTOR_SYSTEM,
)
