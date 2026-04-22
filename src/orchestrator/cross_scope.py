"""
Handles scope-agnostic interactions (greetings, recall, help).

These messages don't require a specific scope and can be handled
regardless of the current scope state.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from src.orchestrator.persona import (
    DEFAULT_BOT_NAME,
    build_capability_response,
    build_farewell_response,
    build_greeting_response,
    build_self_identity_response,
)
from src.orchestrator.scope_registry import ScopeRegistry

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

    SELF_IDENTITY_PATTERNS = [
        r"(what('?s|\s+is)\s+my\s+name|who\s+am\s+i|who\s+i\s+am|my\s+name|my\s+identity)",
        r"(what\s+do\s+you\s+know\s+about\s+me|tell\s+me\s+about\s+myself|my\s+profile|my\s+info)",
        r"(who\s+am\s+i\s+logged\s+in\s+as|who\s+i\s+am\s+logged)",
    ]

    RECALL_PATTERNS = [
        r"(what\s+did\s+i\s+ask|what\s+was\s+my|my\s+(earlier|previous|last)\s+question)",
        r"(repeat\s+that|what\s+have\s+we\s+discussed)",
        r"(show\s+my\s+history|conversation\s+history)",
    ]

    DATA_QUERY_SIGNALS = [
        "show", "list", "find", "where", "how many", "count", "inmate",
        "notes", "entries", "officer", "facility", "movement", "status",
        "today", "yesterday", "week", "month", "top", "last",
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

        if self._is_self_identity(message_lower):
            return self._handle_self_identity(session)

        if self._is_recall(message_lower):
            return self._handle_recall(message_lower, session)

        return None

    def _is_greeting(self, message: str) -> bool:
        # Allow "hello ...<data query>..." to route to pipeline when user includes a real request.
        match = None
        for pattern in self.GREETING_PATTERNS:
            found = re.search(pattern, message, re.I)
            if found:
                match = found
                break
        if match:
            remaining = message[match.end():].strip()
            if remaining and any(signal in remaining for signal in self.DATA_QUERY_SIGNALS):
                return False
        return any(re.search(p, message, re.I) for p in self.GREETING_PATTERNS)

    def _is_farewell(self, message: str) -> bool:
        return any(re.search(p, message, re.I) for p in self.FAREWELL_PATTERNS)

    def _is_help(self, message: str) -> bool:
        return any(re.search(p, message, re.I) for p in self.HELP_PATTERNS)

    def _is_self_identity(self, message: str) -> bool:
        return any(re.search(p, message, re.I) for p in self.SELF_IDENTITY_PATTERNS)

    def _is_recall(self, message: str) -> bool:
        return any(re.search(p, message, re.I) for p in self.RECALL_PATTERNS)

    def _handle_greeting(self, session: Session) -> dict[str, Any]:
        """Respond to greeting with optional scope prompt."""
        options = ScopeRegistry.get_options_for_api()
        scope_label = None
        if session.active_scope:
            scope = ScopeRegistry.get_definition(session.active_scope)
            scope_label = scope.label if scope else session.active_scope

        return build_greeting_response(
            has_active_scope=bool(session.active_scope),
            scope_label=scope_label,
            scope_id=session.active_scope,
            options=options,
        )

    def _handle_farewell(self, session: Session) -> dict[str, Any]:
        """Respond to farewell."""
        turn_count = len([t for t in session.turns if t.role == "user"])
        return build_farewell_response(turn_count)

    def _handle_help(self, session: Session) -> dict[str, Any]:
        """Explain capabilities."""
        options = ScopeRegistry.get_options_for_api()
        active_scope_label = None
        if session.active_scope:
            scope_def = ScopeRegistry.get_definition(session.active_scope)
            active_scope_label = scope_def.label if scope_def else session.active_scope

        return build_capability_response(
            bot_name=DEFAULT_BOT_NAME,
            options=options,
            active_scope_label=active_scope_label,
            include_options=not session.active_scope,
        )

    def _handle_self_identity(self, session: Session) -> dict[str, Any]:
        """Respond to self-identity questions."""
        return build_self_identity_response(session)

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
