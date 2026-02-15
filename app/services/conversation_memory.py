"""
Lightweight in-memory conversation memory for session-based follow-up support.

Stores the last tool name, arguments, pending follow-up, and recently
mentioned jobs per conversation.  Memory resets on server restart —
no persistence required.
"""

from typing import Any
from collections import defaultdict

_MEMORY: dict[str, dict[str, Any]] = defaultdict(dict)

# Keep only the N most-recent jobs in memory (newest first)
_MAX_MENTIONED_JOBS = 10


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


# ── Recently mentioned jobs ───────────────────────────────────────────────


def set_mentioned_jobs(conversation_id: str, jobs: list[dict[str, Any]]) -> None:
    """
    Store the jobs most recently surfaced to the user.

    Each entry should be a slim dict:
      { "job_id": ..., "actual_role": ..., "company_name": ..., "url": ..., "posted_date": ... }

    Newest jobs go first; list is capped at _MAX_MENTIONED_JOBS.
    Duplicates (by job_id) are removed, keeping the latest occurrence.
    """
    _MEMORY.setdefault(conversation_id, {})
    existing: list[dict[str, Any]] = _MEMORY[conversation_id].get("mentioned_jobs", [])

    # Merge: new jobs first, existing after, deduplicate by job_id
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for job in jobs + existing:
        jid = job.get("job_id")
        if jid and jid not in seen:
            seen.add(jid)
            merged.append(job)
        if len(merged) >= _MAX_MENTIONED_JOBS:
            break

    _MEMORY[conversation_id]["mentioned_jobs"] = merged


def get_mentioned_jobs(conversation_id: str) -> list[dict[str, Any]]:
    """Return the most recently mentioned jobs (newest first)."""
    return _MEMORY.get(conversation_id, {}).get("mentioned_jobs", [])
