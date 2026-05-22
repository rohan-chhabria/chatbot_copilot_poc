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
    from src.memory.conversation_store import ConversationStore
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
        r"(what\s+is\s+my\s+history|what'?s\s+my\s+history|whats\s+my\s+history)",
        r"(what\s+did\s+i\s+ask|what\s+was\s+my|my\s+(earlier|previous|last)\s+question)",
        r"(what\s+had\s+i\s+asked|what\s+all\s+i\s+had\s+asked|is\s+that\s+all\s+i\s+have\s+asked)",
        r"(repeat\s+that|what\s+have\s+we\s+discussed)",
        r"(history\s+of\s+what\s+we\s+have\s+discussed)",
        r"(show\s+my\s+history|conversation\s+history)",
        r"^\s*history\??\s*$",
        r"(what\s+have\s+i\s+asked|what\s+all\s+have\s+i\s+asked)",
        r"(as\s+of\s+now|as\s+of\s+(this\s+moment|date)|till\s+now|till\s+date|to\s+date|so\s+far|in\s+the\s+past|past\s+questions?|totally|in\s+general|overall)",
    ]

    DATA_QUERY_SIGNALS = [
        "show", "list", "find", "where", "how many", "count", "inmate",
        "notes", "entries", "officer", "facility", "movement", "status",
        "today", "yesterday", "week", "month", "top", "last",
    ]

    def __init__(self, conversation_store: ConversationStore | None = None):
        self._conversation_store = conversation_store

    def handle(self, message: str, session: Session) -> dict[str, Any] | None:
        """
        Check if message is cross-scope and handle if so.

        Returns None if message should be routed to pipeline.
        """
        message_lower = self._normalize_message(message)

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

    def _normalize_message(self, message: str) -> str:
        normalized = message.lower().strip()
        normalized = normalized.replace("’", "'").replace("`", "'")
        normalized = re.sub(r"\bwhat'?s\b", "what is", normalized)
        normalized = re.sub(r"\bwhats\b", "what is", normalized)
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip()

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

        mode = self._resolve_recall_mode(message=message, session=session, scope_mentioned=scope_mentioned)
        filter_scope = mode["scope"]
        include_ltm = mode["include_ltm"]
        include_all_scopes = mode["include_all_scopes"]
        scope_label = mode["scope_label"]

        user_turns = self._get_user_turns_for_recall(
            session=session,
            scope=filter_scope,
            include_all_scopes=include_all_scopes,
            include_ltm=include_ltm,
        )

        if not user_turns:
            return {
                "summary": f"No questions yet in {scope_label}. What would you like to know?",
                "is_recall": True,
                "row_count": 0,
            }

        lines = [f"Here's what you've asked in {scope_label}:\n"]
        display_turns = user_turns[-10:]
        for i, turn in enumerate(display_turns, 1):
            lines.append(f"  {i}. {turn['content']}")

        if len(user_turns) > 10:
            lines.append(f"\n... and {len(user_turns) - 10} more.")

        lines.append("\nWant me to revisit any of these?")

        return {
            "summary": "\n".join(lines),
            "is_recall": True,
            "query_count": len(user_turns),
            "row_count": 0,
            "recall_items": [
                {"index": i, "content": turn["content"]}
                for i, turn in enumerate(display_turns, 1)
            ],
            "recall_scope": filter_scope,
        }

    def _resolve_recall_mode(
        self,
        message: str,
        session: Session,
        scope_mentioned: str | None,
    ) -> dict[str, Any]:
        # Explicit all-scopes memory request.
        if scope_mentioned is None and re.search(
            r"(all\s+scopes|across\s+all\s+(scopes|topics)|in\s+general|overall|across\s+topics|all\s+topics|what\s+all\s+have\s+i\s+asked\s+totally)",
            message,
            re.I,
        ):
            return {
                "scope": None,
                "include_ltm": True,
                "include_all_scopes": True,
                "scope_label": "all scopes",
            }

        # Explicit scope in the question should include historical turns for that scope.
        if scope_mentioned:
            scope_def = ScopeRegistry.get_definition(scope_mentioned)
            return {
                "scope": scope_mentioned,
                "include_ltm": True,
                "include_all_scopes": False,
                "scope_label": scope_def.label if scope_def else scope_mentioned,
            }

        # Phrases that explicitly ask for deeper historical memory in current scope.
        if re.search(
            r"(in\s+the\s+past|as\s+of\s+now|as\s+of\s+(this\s+moment|date)|till\s+now|till\s+date|to\s+date|so\s+far|what\s+all\s+have\s+i\s+asked|what\s+all\s+i\s+had\s+asked|what\s+had\s+i\s+asked)",
            message,
            re.I,
        ):
            if session.active_scope:
                scope_def = ScopeRegistry.get_definition(session.active_scope)
                scope_label = scope_def.label if scope_def else session.active_scope
            else:
                scope_label = "this session"
            return {
                "scope": session.active_scope,
                "include_ltm": bool(session.active_scope),
                "include_all_scopes": False,
                "scope_label": scope_label,
            }

        # Default: recent current-session memory only, scoped if active.
        if session.active_scope:
            scope_def = ScopeRegistry.get_definition(session.active_scope)
            return {
                "scope": session.active_scope,
                "include_ltm": False,
                "include_all_scopes": False,
                "scope_label": scope_def.label if scope_def else session.active_scope,
            }
        return {
            "scope": None,
            "include_ltm": False,
            "include_all_scopes": False,
            "scope_label": "this session",
        }

    def _get_user_turns_for_recall(
        self,
        session: Session,
        scope: str | None,
        include_all_scopes: bool,
        include_ltm: bool,
    ) -> list[dict[str, Any]]:
        # 1) Current session turns (STM)
        stm_turns = session.turns if include_all_scopes else session.get_turns_for_scope(scope)
        merged: list[dict[str, Any]] = [
            {
                "session_id": session.session_id,
                "scope": t.scope,
                "content": t.content,
                "timestamp": t.timestamp,
            }
            for t in stm_turns
            if t.role == "user"
        ]

        # 2) Long-term turns (LTM)
        if include_ltm and self._conversation_store is not None:
            ltm_scope = None if include_all_scopes else scope
            ltm_turns = self._conversation_store.get_user_turns(
                customer_key=session.customer_key,
                user_id=session.user_id,
                limit=120,
                scope=ltm_scope,
            )
            for turn in ltm_turns:
                merged.append(
                    {
                        "session_id": turn.get("session_id"),
                        "scope": turn.get("scope"),
                        "content": turn.get("content", ""),
                        "timestamp": float(turn.get("timestamp", 0)),
                    }
                )

        # 3) De-duplicate and sort by time
        deduped: dict[tuple[str, str | None, int], dict[str, Any]] = {}
        for turn in merged:
            key = (
                turn["content"].strip().lower(),
                turn.get("scope"),
                round(float(turn.get("timestamp", 0)), 3),
            )
            if key not in deduped:
                deduped[key] = turn

        return sorted(deduped.values(), key=lambda t: float(t.get("timestamp", 0)))
