"""Execution Session Manager — enables long task chains under MAREF governance.

A session is a bounded execution context where SEMI_TRUSTED or UNTRUSTED
agents can run autonomous task chains without per-action HITL blocking.
Within a session:

  - write_file / shell / exec → AUDIT (notified, not blocked)
  - rm -rf / sudo / DROP TABLE → DENY (P0 safety unchanged)
  - Circuit breaker depth → relaxed to session.max_steps

Usage:
    from maref.gaas.session_manager import declare_session

    sess = declare_session("trae", "refactor module A", max_steps=50)
    if is_session_active(sess.session_id):
        # governance evaluates with relaxed=True
        ...
    complete_session(sess.session_id, success=True)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_ACTIVE_SESSIONS_PER_AGENT = 3
MAX_STEPS_MIN = 1
MAX_STEPS_MAX = 200
MAX_GOAL_LENGTH = 200
MAX_CRITERIA_LENGTH = 200
STALE_SESSION_SECONDS = 7200  # 2h idle → eligible for cleanup

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_SessionStore = dict[str, "Session"]

_sessions: _SessionStore = {}


@dataclass
class Session:
    """A single execution session bound to one agent."""

    session_id: str = ""
    agent_id: str = ""
    goal: str = ""
    max_steps: int = 50
    completion_criteria: str = ""
    created_at: float = 0.0
    completed_at: float | None = None
    success: bool | None = None
    result: str = ""
    steps: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_VALID_SESSION_AGENTS = {"SEMI_TRUSTED", "UNTRUSTED"}


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


def _clamp(val: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, val))


def _trim(text: str, limit: int) -> str:
    return text[:limit] if len(text) > limit else text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def declare_session(
    agent_id: str,
    goal: str = "",
    max_steps: int = 50,
    completion_criteria: str = "",
    trust_level: str = "SEMI_TRUSTED",
) -> Session:
    """Create a new execution session.

    Raises ValueError if the agent's trust_level is not in _VALID_SESSION_AGENTS.
    """
    level = trust_level.upper()
    if level not in _VALID_SESSION_AGENTS:
        raise ValueError(
            f"Cannot create session: trust_level={level!r} is not supported. "
            f"Only {_VALID_SESSION_AGENTS} agents may declare sessions."
        )

    # Enforce concurrent session limit
    active = get_active_sessions(agent_id)
    if len(active) >= MAX_ACTIVE_SESSIONS_PER_AGENT:
        raise RuntimeError(
            f"Agent {agent_id!r} already has {len(active)} active sessions "
            f"(max {MAX_ACTIVE_SESSIONS_PER_AGENT})."
        )

    now = time.time()
    session = Session(
        session_id=_new_id(),
        agent_id=agent_id,
        goal=_trim(goal, MAX_GOAL_LENGTH),
        max_steps=_clamp(max_steps, MAX_STEPS_MIN, MAX_STEPS_MAX),
        completion_criteria=_trim(completion_criteria, MAX_CRITERIA_LENGTH),
        created_at=now,
    )
    _sessions[session.session_id] = session
    return session


def get_session(session_id: str) -> Session | None:
    """Retrieve a session by ID."""
    return _sessions.get(session_id)


def is_session_active(session_id: str) -> bool:
    """Check if a session exists and is still active (not completed, not exhausted)."""
    sess = _sessions.get(session_id)
    if sess is None:
        return False
    if sess.completed_at is not None:
        return False
    return not sess.steps >= sess.max_steps


def increment_step(
    session_id: str,
    tool_name: str = "",
    verdict: str = "",
    risk_score: float = 0.0,
) -> Session | None:
    """Record one step in the session. Returns None if session is gone or exhausted."""
    sess = _sessions.get(session_id)
    if sess is None:
        return None
    if sess.completed_at is not None:
        return sess  # already done, no-op (but still return session)

    sess.steps += 1
    sess.history.append(
        {
            "step": sess.steps,
            "tool": tool_name,
            "verdict": verdict,
            "risk_score": risk_score,
            "timestamp": time.time(),
        }
    )
    # Keep history bounded
    if len(sess.history) > MAX_STEPS_MAX:
        sess.history = sess.history[-MAX_STEPS_MAX:]

    # Auto-terminate if steps exhausted
    if sess.steps >= sess.max_steps:
        sess.completed_at = time.time()
        sess.success = False
        sess.result = "max_steps_reached"

    return sess


def complete_session(
    session_id: str,
    success: bool,
    result: str = "",
) -> Session | None:
    """Mark a session as completed. Returns None if session_id not found."""
    sess = _sessions.get(session_id)
    if sess is None:
        return None
    sess.completed_at = time.time()
    sess.success = success
    sess.result = result
    return sess


def get_active_sessions(agent_id: str | None = None) -> list[Session]:
    """List active (non-completed, non-exhausted) sessions."""
    now = time.time()
    result: list[Session] = []
    for sess in _sessions.values():
        if sess.completed_at is not None:
            continue
        if sess.steps >= sess.max_steps:
            continue
        # Don't return sessions that have been idle for too long
        last_activity = sess.history[-1]["timestamp"] if sess.history else sess.created_at
        if now - last_activity > STALE_SESSION_SECONDS:
            continue
        if agent_id is not None and sess.agent_id != agent_id:
            continue
        result.append(sess)
    return result


def cleanup_stale_sessions(max_idle_seconds: float = STALE_SESSION_SECONDS) -> int:
    """Remove sessions idle for longer than max_idle_seconds. Returns count removed."""
    now = time.time()
    stale_ids = [
        sid
        for sid, sess in _sessions.items()
        if sess.completed_at is not None and now - sess.completed_at > max_idle_seconds
    ]
    for sid in stale_ids:
        del _sessions[sid]
    return len(stale_ids)
