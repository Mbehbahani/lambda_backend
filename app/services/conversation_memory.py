"""
Lightweight in-memory conversation memory for session-based follow-up support.

Stores only the last tool name, arguments, and pending follow-up per conversation.
Memory resets on server restart — no persistence required.
"""

from typing import Any
from collections import defaultdict

_MEMORY: dict[str, dict[str, Any]] = defaultdict(dict)


def get_memory(conversation_id: str) -> dict[str, Any]:
    """Return the full memory dict for a conversation."""
    return _MEMORY.setdefault(conversation_id, {})


def set_last_tool(conversation_id: str, tool_name: str, tool_args: dict) -> None:
    """Store the most recent tool call for a conversation."""
    _MEMORY.setdefault(conversation_id, {})
    _MEMORY[conversation_id]["last_tool_name"] = tool_name
    _MEMORY[conversation_id]["last_tool_args"] = tool_args


def get_last_tool(conversation_id: str) -> tuple[str | None, dict | None]:
    """Retrieve the last tool name and arguments for a conversation."""
    mem = _MEMORY.get(conversation_id, {})
    return mem.get("last_tool_name"), mem.get("last_tool_args")


# ── Pending follow-up tracking ─────────────────────────────────────────────


def set_pending_followup(conversation_id: str, followup: dict) -> None:
    """Store a pending follow-up action (e.g. after assistant offers a breakdown)."""
    _MEMORY.setdefault(conversation_id, {})
    _MEMORY[conversation_id]["pending_followup"] = followup


def get_pending_followup(conversation_id: str) -> dict | None:
    """Retrieve the pending follow-up for a conversation, if any."""
    mem = _MEMORY.get(conversation_id, {})
    return mem.get("pending_followup")


def clear_pending_followup(conversation_id: str) -> None:
    """Remove the pending follow-up after it has been handled."""
    if conversation_id in _MEMORY:
        _MEMORY[conversation_id].pop("pending_followup", None)
