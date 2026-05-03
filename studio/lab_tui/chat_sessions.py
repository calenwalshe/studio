"""Real Claude Code chat sessions — per-scope persistent UUID sessions.

One session per chat scope:
- Chief of Staff: scope_key="chief"  → UUID stored as "chief" in chat-sessions.json
- Lab Agent:     scope_key=f"lab:{lab_id}" → UUID stored under that key

Each session is a real Claude Code session with:
- Persistent conversation history (stored at ~/.claude/projects/<cwd>/<uuid>.jsonl)
- Tools available (Read, Grep, Bash) for the agent to inspect evidence on demand
- System prompt injected ONCE at session creation
- Resumable across cockpit restarts (UUIDs persisted to disk)
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path


SESSIONS_FILE_NAME = "chat-sessions.json"  # in CGL_STATE_DIR


def _state_dir() -> Path:
    """Resolve CGL_STATE_DIR consistent with _studio_env.sh logic."""
    base = os.environ.get("CGL_STATE_DIR")
    if base:
        return Path(base)
    # Fallback if env not set (e.g. headless tests)
    home = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
    return home / "studio" / "default"


def _sessions_file() -> Path:
    return _state_dir() / SESSIONS_FILE_NAME


def _load_sessions() -> dict:
    f = _sessions_file()
    if not f.exists():
        return {"schema": 1, "sessions": {}}
    try:
        return json.loads(f.read_text())
    except json.JSONDecodeError:
        return {"schema": 1, "sessions": {}}


def _save_sessions(state: dict) -> None:
    f = _sessions_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.rename(f)


def _session_log_path(session_uuid: str, cwd: Path) -> Path:
    """Path to ~/.claude/projects/<cwd-slug>/<uuid>.jsonl"""
    cwd_slug = str(cwd.resolve()).replace("/", "-").replace(".", "-")
    return Path.home() / ".claude" / "projects" / cwd_slug / f"{session_uuid}.jsonl"


@dataclass
class ChatSession:
    scope_key: str
    session_uuid: str
    cwd: Path             # the directory the session runs in (federation root or lab root)
    system_prompt: str
    is_new: bool          # True if this is a freshly-created UUID, False if resumed


def get_or_create_session(scope_key: str, cwd: Path, system_prompt: str) -> ChatSession:
    """Return the ChatSession for scope_key. Creates a new UUID if first time."""
    state = _load_sessions()
    sessions = state.setdefault("sessions", {})

    if scope_key in sessions:
        sid = sessions[scope_key]["uuid"]
        log_exists = _session_log_path(sid, cwd).exists()
        return ChatSession(
            scope_key=scope_key,
            session_uuid=sid,
            cwd=cwd,
            system_prompt=system_prompt,
            is_new=not log_exists,  # UUID stored but log gone (e.g. cleared) → treat as new
        )

    sid = str(uuid.uuid4())
    sessions[scope_key] = {
        "uuid": sid,
        "cwd": str(cwd.resolve()),
        "scope_kind": "chief" if scope_key == "chief" else "lab",
    }
    _save_sessions(state)
    return ChatSession(
        scope_key=scope_key,
        session_uuid=sid,
        cwd=cwd,
        system_prompt=system_prompt,
        is_new=True,
    )


def reset_session(scope_key: str) -> bool:
    """Forget the UUID for scope_key. Next call to get_or_create_session creates fresh.
    Used for /refresh after major state changes (promote, spawn, archive, etc.)."""
    state = _load_sessions()
    sessions = state.setdefault("sessions", {})
    if scope_key not in sessions:
        return False
    del sessions[scope_key]
    _save_sessions(state)
    return True


async def send_message(session: ChatSession, message: str, timeout: int = 120) -> str:
    """Send a message to the Claude Code session and return the reply text.

    First call (is_new=True): creates session with --session-id and --append-system-prompt
    Subsequent calls: --resume <uuid>
    """
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)  # force subscription billing

    if session.is_new:
        cmd = [
            "claude", "-p",
            "--session-id", session.session_uuid,
            "--append-system-prompt", session.system_prompt,
            "--output-format", "text",
            message,
        ]
        # After first call, mark as no-longer-new (for in-process state)
        # The persistent state on disk doesn't need updating — get_or_create_session
        # detects via session_log_path() existence
    else:
        cmd = [
            "claude", "-p",
            "--resume", session.session_uuid,
            "--output-format", "text",
            message,
        ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(session.cwd),
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return f"_(session timeout after {timeout}s)_"

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")[:300]
        return f"_(session error: {err})_"

    # Mutate the dataclass to reflect that this is now an existing session
    session.is_new = False
    return stdout.decode("utf-8", errors="replace").strip()
