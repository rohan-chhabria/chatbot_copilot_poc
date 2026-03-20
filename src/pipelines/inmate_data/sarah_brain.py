"""
Sarah's Brain — Domain intelligence, personality, and conversational responses.

Handles all non-SQL intents: greetings, capabilities, domain questions,
farewells, clarifications, and out-of-scope deflections.

Sarah is a knowledgeable correctional intelligence assistant who speaks
concisely and professionally. She never exposes SQL or technical internals
to the user — she abstracts the data layer completely.
"""

from __future__ import annotations

import random
from typing import Any

from src.pipelines.inmate_data.intent_engine import Intent, IntentResult
from src.session.session_manager import Session
from src.shared.config import BOT_NAME
from src.shared.logger import get_logger

logger = get_logger(__name__)

_NAME = BOT_NAME or "Sarah"

# ── Greeting responses ────────────────────────────────────────────────────

_GREETINGS_FIRST = [
    (
        "Hi! I'm {name}, your Inmate Intelligence assistant.\n\n"
        "I can help you with:\n"
        "• 📋 Notes & entries — search, filter, count by officer/keyword/date\n"
        "• 👤 Inmate info — status, location, movement history\n"
        "• 🏢 Facility data — dorms, rooms, occupancy\n"
        "• 📊 Analytics — top officers, trends, compliance gaps\n"
        "• 🔴 Alerts — red-marked entries, fire watch, suicide watch\n\n"
        "Try: \"Show fire watch notes today\" or \"Where is inmate Anthony?\""
    ),
]

_GREETINGS_RETURNING = [
    "Welcome back! What would you like to look into?",
    "Hey again! Ready to help — what do you need?",
    "I'm here. What can I pull up for you?",
]

# ── Capability responses ──────────────────────────────────────────────────

_CAPABILITIES = (
    "Here's what I can do for you:\n\n"
    "📋 **Notes & Entries**\n"
    "  • Search notes by keyword, officer, date, or inmate\n"
    "  • Find fire watch, suicide watch, rounds, security entries\n"
    "  • Count notes by officer, shift, or time period\n"
    "  • Red-highlighted / priority entries\n"
    "  • Visitor log entries\n\n"
    "👤 **Inmate Intelligence**\n"
    "  • Current status and location (room, bed, facility)\n"
    "  • Movement history — transfers between facilities/rooms\n"
    "  • Status change timeline\n"
    "  • Search by name or booking number\n\n"
    "🏢 **Facility & Officer Data**\n"
    "  • Active facilities and dorms\n"
    "  • Officer activity and note counts\n"
    "  • Inactive user activity tracking\n"
    "  • Shift-based reporting\n\n"
    "📊 **Analytics**\n"
    "  • Top officers by note volume\n"
    "  • Keyword usage trends\n"
    "  • Daily/weekly/monthly summaries\n"
    "  • Compliance gap detection\n\n"
    "💡 **Try asking:**\n"
    "  • \"Show fire watch notes today\"\n"
    "  • \"Where is inmate Anthony Nova?\"\n"
    "  • \"Top 5 officers by notes this month\"\n"
    "  • \"Red marked entries in last 7 days\"\n"
    "  • \"Inmate movement in last 7 days\""
)

# ── Farewell responses ────────────────────────────────────────────────────

_FAREWELLS = [
    "Glad I could help! Stay safe out there. 👋",
    "Anytime. I'll be here when you need me.",
    "Take care! Your session is still active if you need anything else.",
    "You're welcome! Have a good shift.",
]

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
    intent = intent_result.intent
    q = intent_result.rewritten_question.lower()

    if intent == Intent.GREETING:
        return _handle_greeting(session)

    if intent == Intent.SELF_IDENTITY:
        return _handle_self_identity(session)

    if intent == Intent.FAREWELL:
        return _handle_farewell(session)

    if intent == Intent.CAPABILITY:
        return _handle_capability(q)

    if intent == Intent.OUT_OF_SCOPE:
        return _handle_out_of_scope()

    if intent == Intent.CLARIFICATION:
        return _handle_clarification()

    if intent == Intent.GENERAL_DOMAIN:
        return _handle_domain_question(q)

    return _handle_clarification()


def _handle_greeting(session: Session | None) -> dict[str, Any]:
    if not session:
        text = random.choice(_GREETINGS_FIRST).format(name=_NAME)
        return _wrap(text)

    user_name = session.display_name or session.user_id.replace(".", " ").title()
    role = session.role.title() if session.role else "Officer"

    if len(session.turns) > 0:
        text = f"Hey {user_name}! Ready to help — what do you need?"
    else:
        text = (
            f"Hello {role} {user_name}, I'm {_NAME} — your Inmate Intelligence assistant. "
            f"I can help you search notes, track inmates, check compliance, and more. "
            f"What can I help you with?"
        )
    return _wrap(text)


def _handle_self_identity(session: Session | None) -> dict[str, Any]:
    if not session:
        return _wrap("I don't have your profile loaded yet. Please log in to get started.")
    user_name = session.display_name or session.user_id.replace(".", " ").title()
    role = session.role.title() if session.role else "Officer"
    fac_count = len(session.facility_ids) if session.facility_ids else 0

    turn_count = len([t for t in session.turns if t.role == "user"])
    topics = []
    for t in reversed(session.turns):
        if t.role == "user" and len(t.content) > 5:
            topics.append(t.content)
            if len(topics) >= 3:
                break

    lines = [f"You're **{user_name}**, logged in as **{role}**."]
    if fac_count:
        lines.append(f"You have access to **{fac_count} facilities**.")
    if turn_count > 0:
        lines.append(f"We've had **{turn_count}** exchange{'s' if turn_count != 1 else ''} so far this session.")
    if topics:
        topic_str = ", ".join(f'"{t}"' for t in reversed(topics))
        lines.append(f"Recent topics: {topic_str}")
    lines.append("\nI scope all queries to your facilities automatically. Just ask away!")
    return _wrap("\n".join(lines))


def _handle_farewell(session: Session | None = None) -> dict[str, Any]:
    user_name = ""
    if session:
        user_name = session.display_name or session.user_id.replace(".", " ").title()
    farewells = [
        f"Glad I could help{', ' + user_name if user_name else ''}! Stay safe out there. 👋",
        "Anytime. I'll be here when you need me.",
        f"Take care{', ' + user_name if user_name else ''}! Your session is still active if you need anything.",
    ]
    return _wrap(random.choice(farewells))


def _handle_capability(question: str = "") -> dict[str, Any]:
    if question and any(p in question for p in ("who are you", "what are you", "your name")):
        return _wrap(
            f"I'm **{_NAME}**, your Inmate Intelligence assistant. "
            "I'm built to help correctional officers and wardens get fast, "
            "accurate answers from your facility data — notes, inmates, movements, "
            "compliance, and more.\n\n" + _CAPABILITIES
        )
    return _wrap(_CAPABILITIES)


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
