"""
Shared orchestrator-level bot persona responses.
"""

from __future__ import annotations

from typing import Any

from src.shared.config import BOT_GREETING, BOT_NAME


def build_greeting_response(
    *,
    has_active_scope: bool,
    scope_label: str | None,
    scope_id: str | None,
    options: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build greeting response with consistent persona across scopes."""
    if has_active_scope and scope_label:
        return {
            "summary": f"Hi there! I'm currently helping you with {scope_label}. What would you like to know?",
            "is_greeting": True,
            "scope": scope_id,
            "row_count": 0,
        }

    return {
        "summary": BOT_GREETING,
        "is_greeting": True,
        "requires_scope": True,
        "options": options,
        "row_count": 0,
    }


def build_farewell_response(user_turn_count: int) -> dict[str, Any]:
    """Build farewell response."""
    if user_turn_count > 0:
        return {
            "summary": f"Goodbye! We covered {user_turn_count} questions today. Come back anytime!",
            "is_farewell": True,
            "row_count": 0,
        }
    return {
        "summary": "Goodbye! Feel free to come back whenever you need help.",
        "is_farewell": True,
        "row_count": 0,
    }


def build_capability_response(
    *,
    bot_name: str,
    options: list[dict[str, Any]],
    active_scope_label: str | None,
    include_options: bool,
) -> dict[str, Any]:
    """Build capability/help response."""
    lines = [f"I'm {bot_name}, your assistant. Here's what I can help with:\n"]
    for opt in options:
        lines.append(f"  {opt['icon']} **{opt['label']}**: {opt['description']}")

    if active_scope_label:
        lines.append(
            f"\nYou're currently in **{active_scope_label}**. Use the Switch button to change."
        )
    else:
        lines.append("\nSelect an option above to get started!")

    return {
        "summary": "\n".join(lines),
        "is_help": True,
        "options": options if include_options else None,
        "row_count": 0,
    }


def build_self_identity_response(session: Any) -> dict[str, Any]:
    """Build self-identity response based on current session context."""
    user_name = session.display_name or session.user_id.replace(".", " ").title()
    role = session.role.title() if session.role else "Officer"
    fac_count = len(session.facility_ids) if session.facility_ids else 0
    turn_count = len([t for t in session.turns if t.role == "user"])

    topics = []
    for turn in reversed(session.turns):
        if turn.role == "user" and len(turn.content) > 5:
            topics.append(turn.content)
            if len(topics) >= 3:
                break

    lines = [f"You're **{user_name}**, logged in as **{role}**."]
    if fac_count:
        lines.append(f"You have access to **{fac_count} facilities**.")
    if turn_count > 0:
        lines.append(
            f"We've had **{turn_count}** exchange{'s' if turn_count != 1 else ''} so far this session."
        )
    if topics:
        topic_str = ", ".join(f'"{t}"' for t in reversed(topics))
        lines.append(f"Recent topics: {topic_str}")
    lines.append(
        "\nI scope all queries to your facilities automatically. Just ask away!"
    )

    return {
        "summary": "\n".join(lines),
        "is_self_identity": True,
        "row_count": 0,
    }


DEFAULT_BOT_NAME = BOT_NAME
