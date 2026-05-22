"""
Inmate domain responses for non-SQL, pipeline-specific interactions.
"""

from __future__ import annotations

import random
from typing import Any

from src.pipelines.inmate_data.intent_engine import Intent, IntentResult
from src.session.session_manager import Session
from src.shared.logger import get_logger

logger = get_logger(__name__)

# ── Out of scope ──────────────────────────────────────────────────────────

_OUT_OF_SCOPE = (
    "I'm focused on correctional facility intelligence — inmate data, officer notes, "
    "facility operations, and compliance.\n\n"
    "I can't help with that, but try asking me:\n"
    "• \"How many notes were added today?\"\n"
    "• \"Show fire watch entries this week\"\n"
    "• \"Where is inmate Anthony?\""
)

# ── Clarification ─────────────────────────────────────────────────────────

_CLARIFICATIONS = [
    (
        "I want to help, but I need a bit more detail. Could you try:\n"
        "• An inmate name — \"show entries for inmate John Smith\"\n"
        "• A keyword — \"fire watch notes today\"\n"
        "• An officer — \"notes by officer Richard Bell\"\n"
        "• A time range — \"entries in last 7 days\""
    ),
    (
        "Can you be more specific? For example:\n"
        "• \"How many notes added this week?\"\n"
        "• \"List all inmates in facility\"\n"
        "• \"Red marked entries yesterday\""
    ),
]

# ── General domain knowledge (no SQL needed) ──────────────────────────────

_DOMAIN_KNOWLEDGE: dict[str, str] = {
    "highlighter": (
        "Highlighter colors in the system:\n"
        "  🔴 Red (11) — High priority / critical\n"
        "  🟢 Light Green (12) — Routine\n"
        "  🔵 Blue (13) — Informational\n"
        "  🟡 Yellow (14) — Caution\n"
        "  🩷 Pink (15) — Medical\n"
        "  ⚪ White (21) — Default\n"
        "  🟠 Orange (22) — Warning\n\n"
        "Ask me: \"Show red marked entries in last 7 days\""
    ),
    "shift": (
        "The system tracks 9 shift types. Notes are tagged with shift_id to indicate "
        "when they were created.\n\nAsk me: \"Notes from shift 1 today\""
    ),
    "keyword": (
        "Notes are tagged with keywords like Fire Watch, Suicide Watch, Rounds, "
        "Medical Rounds, Zone Check, Census Count, Meals, Security, and more.\n\n"
        "Ask me: \"Show fire watch notes today\" or \"Count security entries this week\""
    ),
    "status": (
        "Inmates have status types: Meal, Recreation, Medical, Cell, In Transit, "
        "Segregation, and more. Status changes are tracked with timestamps.\n\n"
        "Ask me: \"Show inmates in medical status\" or \"Status changes for inmate Anthony\""
    ),
}


def generate_response(
    intent_result: IntentResult,
    session: Session | None = None,
) -> dict[str, Any]:
    """Generate a non-SQL response based on classified intent."""
    _ = session
    intent = intent_result.intent
    q = intent_result.rewritten_question.lower()

    if intent == Intent.OUT_OF_SCOPE:
        return _handle_out_of_scope()

    if intent == Intent.CLARIFICATION:
        return _handle_clarification()

    if intent == Intent.GENERAL_DOMAIN:
        return _handle_domain_question(q)

    return _handle_clarification()


def _handle_out_of_scope() -> dict[str, Any]:
    return _wrap(_OUT_OF_SCOPE)


def _handle_clarification() -> dict[str, Any]:
    return _wrap(random.choice(_CLARIFICATIONS))


def _handle_domain_question(question: str) -> dict[str, Any]:
    for key, answer in _DOMAIN_KNOWLEDGE.items():
        if key in question:
            return _wrap(answer)
    return _handle_clarification()


def _wrap(text: str) -> dict[str, Any]:
    return {
        "summary": text,
        "row_count": 0,
        "is_conversational": True,
    }


def enrich_data_response(
    response: dict[str, Any],
    question: str,
    session: Session | None = None,
) -> dict[str, Any]:
    """Add smart follow-up suggestions to data query responses."""
    suggestions = _generate_suggestions(question, response)
    if suggestions:
        current_summary = response.get("summary", "")
        response["summary"] = current_summary + "\n\n💡 " + suggestions
    return response


def _generate_suggestions(question: str, response: dict[str, Any]) -> str:
    """Context-aware follow-up suggestions based on the question + results."""
    q = question.lower()
    row_count = response.get("row_count", 0)

    if row_count == 0:
        return "Try broadening the date range or checking the spelling."

    suggestions = []

    if "fire watch" in q or "suicide watch" in q:
        suggestions.append("Ask: \"Which facilities have compliance gaps?\"")
    if "inmate" in q and "movement" not in q:
        suggestions.append("Ask: \"Show movement history for this inmate\"")
    if "top" in q and "officer" in q:
        suggestions.append("Ask: \"Show notes by [officer name] this week\"")
    if "red" in q or "highlight" in q:
        suggestions.append("Ask: \"Who added these red-marked entries?\"")
    if "today" in q:
        suggestions.append("Ask: \"Compare with yesterday's data\"")
    if row_count > 50:
        suggestions.append("Ask: \"Narrow down by keyword or officer\"")

    return suggestions[0] if suggestions else ""
