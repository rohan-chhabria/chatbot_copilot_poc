"""
Handles scope-agnostic interactions (greetings, recall, help).

These messages don't require a specific scope and can be handled
regardless of the current scope state.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from src.orchestrator.scope_registry import ScopeRegistry
from src.shared.config import BOT_NAME

if TYPE_CHECKING:
    from src.session.models import Session


class CrossScopeHandler:
    """
    Handles messages that don't require a specific scope.

    - Greetings: "Hello", "Hi Sarah"
    - Help/Capabilities: "What can you do?"
    - Recall: "What did I ask earlier?"
    - Farewells: "Goodbye", "Thanks"
    """

    GREETING_PATTERNS = [
        r"^(hi|hello|hey|good\s+(morning|afternoon|evening))(\s|!|\.|$)",
        r"^(yo|sup|howdy)(\s|!|\.|$)",
    ]

    FAREWELL_PATTERNS = [
        r"^(bye|goodbye|see\s+you|thanks?|thank\s+you)(\s|!|\.|$)",
        r"^(that'?s?\s+all|done|exit|quit)(\s|!|\.|$)",
    ]

    HELP_PATTERNS = [
        r"(what\s+can\s+you\s+do|help|capabilities)",
        r"(how\s+do\s+(you|i)\s+use|how\s+does\s+this\s+work)",
    ]

    RECALL_PATTERNS = [
        r"(what\s+did\s+i\s+ask|what\s+was\s+my|my\s+(earlier|previous|last)\s+question)",
        r"(repeat\s+that|what\s+have\s+we\s+discussed)",
        r"(show\s+my\s+history|conversation\s+history)",
    ]

    def handle(self, message: str, session: Session) -> dict[str, Any] | None:
        """
        Check if message is cross-scope and handle if so.

        Returns None if message should be routed to pipeline.
        """
        message_lower = message.lower().strip()

        if self._is_greeting(message_lower):
            return self._handle_greeting(session)

        if self._is_farewell(message_lower):
            return self._handle_farewell(session)

        if self._is_help(message_lower):
            return self._handle_help(session)

        if self._is_recall(message_lower):
            return self._handle_recall(message_lower, session)

        return None

    def _is_greeting(self, message: str) -> bool:
        return any(re.search(p, message, re.I) for p in self.GREETING_PATTERNS)

    def _is_farewell(self, message: str) -> bool:
        return any(re.search(p, message, re.I) for p in self.FAREWELL_PATTERNS)

    def _is_help(self, message: str) -> bool:
        return any(re.search(p, message, re.I) for p in self.HELP_PATTERNS)

    def _is_recall(self, message: str) -> bool:
        return any(re.search(p, message, re.I) for p in self.RECALL_PATTERNS)

    def _handle_greeting(self, session: Session) -> dict[str, Any]:
        """Respond to greeting with optional scope prompt."""
        options = ScopeRegistry.get_options_for_api()

        if session.active_scope:
            scope = ScopeRegistry.get_definition(session.active_scope)
            scope_label = scope.label if scope else session.active_scope
            return {
                "summary": f"Hi there! I'm currently helping you with {scope_label}. What would you like to know?",
                "is_greeting": True,
                "scope": session.active_scope,
                "row_count": 0,
            }

        return {
            "summary": f"Hi! I'm {BOT_NAME}. What would you like help with today?",
            "is_greeting": True,
            "requires_scope": True,
            "options": options,
            "row_count": 0,
        }

    def _handle_farewell(self, session: Session) -> dict[str, Any]:
        """Respond to farewell."""
        turn_count = len([t for t in session.turns if t.role == "user"])

        if turn_count > 0:
            return {
                "summary": f"Goodbye! We covered {turn_count} questions today. Come back anytime!",
                "is_farewell": True,
                "row_count": 0,
            }

        return {
            "summary": "Goodbye! Feel free to come back whenever you need help.",
            "is_farewell": True,
            "row_count": 0,
        }

    def _handle_help(self, session: Session) -> dict[str, Any]:
        """Explain capabilities."""
        options = ScopeRegistry.get_options_for_api()

        lines = [f"I'm {BOT_NAME}, your assistant. Here's what I can help with:\n"]
        for opt in options:
            lines.append(f"  {opt['icon']} **{opt['label']}**: {opt['description']}")

        if session.active_scope:
            scope_def = ScopeRegistry.get_definition(session.active_scope)
            scope_label = scope_def.label if scope_def else session.active_scope
            lines.append(
                f"\nYou're currently in **{scope_label}**. Use the Switch button to change."
            )
        else:
            lines.append("\nSelect an option above to get started!")

        return {
            "summary": "\n".join(lines),
            "is_help": True,
            "options": options if not session.active_scope else None,
            "row_count": 0,
        }

    def _handle_recall(self, message: str, session: Session) -> dict[str, Any]:
        """Recall conversation history."""
        # Check if asking about specific scope
        scope_mentioned = None
        for opt in ScopeRegistry.get_all():
            if opt.id in message or opt.label.lower() in message:
                scope_mentioned = opt.id
                break

        if scope_mentioned:
            turns = session.get_turns_for_scope(scope_mentioned)
            scope_def = ScopeRegistry.get_definition(scope_mentioned)
            scope_label = scope_def.label if scope_def else scope_mentioned
        elif "all" in message:
            turns = session.turns
            scope_label = "all scopes"
        else:
            # Default to current scope or all
            turns = (
                session.get_turns_for_scope()
                if session.active_scope
                else session.turns
            )
            if session.active_scope:
                scope_def = ScopeRegistry.get_definition(session.active_scope)
                scope_label = scope_def.label if scope_def else session.active_scope
            else:
                scope_label = "this session"

        user_turns = [t for t in turns if t.role == "user"]

        if not user_turns:
            return {
                "summary": f"No questions yet in {scope_label}. What would you like to know?",
                "is_recall": True,
                "row_count": 0,
            }

        lines = [f"Here's what you've asked in {scope_label}:\n"]
        for i, turn in enumerate(user_turns[-10:], 1):
            lines.append(f"  {i}. {turn.content}")

        if len(user_turns) > 10:
            lines.append(f"\n... and {len(user_turns) - 10} more.")

        lines.append("\nWant me to revisit any of these?")

        return {
            "summary": "\n".join(lines),
            "is_recall": True,
            "query_count": len(user_turns),
            "row_count": 0,
        }
