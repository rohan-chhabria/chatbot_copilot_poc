"""
Scope state machine for guided conversation flow.

Manages scope state and transitions:
- NO_SCOPE: No active scope, show options
- SCOPE_ACTIVE: Processing within a scope

Transitions:
- select_scope: NO_SCOPE → SCOPE_ACTIVE
- switch_scope: SCOPE_ACTIVE → SCOPE_ACTIVE (different scope)
- clear_scope: SCOPE_ACTIVE → NO_SCOPE
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncGenerator

from src.orchestrator.cross_scope import CrossScopeHandler
from src.orchestrator.scope_registry import ScopeRegistry
from src.session.models import ConversationTurn
from src.shared.exceptions import ScopeError
from src.shared.logger import get_logger

if TYPE_CHECKING:
    from src.memory.conversation_store import ConversationStore
    from src.session.models import Session

logger = get_logger(__name__)


class ScopeStateMachine:
    """
    Manages scope state and transitions.

    States:
        NO_SCOPE: No active scope, show options
        SCOPE_ACTIVE: Processing within a scope

    Transitions:
        select_scope: NO_SCOPE → SCOPE_ACTIVE
        switch_scope: SCOPE_ACTIVE → SCOPE_ACTIVE (different scope)
        clear_scope: SCOPE_ACTIVE → NO_SCOPE
    """

    def __init__(self, conversation_store: ConversationStore | None = None):
        self._conversation_store = conversation_store
        self._cross_scope = CrossScopeHandler()

    async def handle_message(
        self,
        message: str,
        session: Session,
    ) -> dict[str, Any]:
        """
        Main entry point for message handling.

        Returns response dict or routes to appropriate pipeline.
        """
        # 1. Check cross-scope handlers (greetings, recall, help)
        cross_scope_response = self._cross_scope.handle(message, session)
        if cross_scope_response:
            self._save_conversational_turn(session, message, cross_scope_response)
            return cross_scope_response

        # 2. No active scope? Prompt for selection
        if session.active_scope is None:
            return self._prompt_scope_selection(message, session)

        # 3. Route to active pipeline
        return await self._dispatch_to_pipeline(message, session)

    def select_scope(self, scope_id: str, session: Session) -> dict[str, Any]:
        """
        User selected a scope (clicked option block).

        Returns welcome message for the scope.
        """
        if not ScopeRegistry.is_valid_scope(scope_id):
            raise ScopeError(f"Invalid scope: {scope_id}")

        previous_scope = session.active_scope
        is_returning = scope_id in session.scope_contexts

        # Switch scope (preserves previous context)
        scope_context = session.switch_scope(scope_id)

        # Get pipeline welcome
        pipeline = ScopeRegistry.get(scope_id)
        welcome = pipeline.get_welcome_message(is_returning)

        # If returning, add context reminder
        if is_returning and scope_context.recent_queries:
            last_query = scope_context.recent_queries[-1]
            truncated = last_query[:50] + "..." if len(last_query) > 50 else last_query
            welcome = (
                f"Welcome back to {pipeline.scope_label}. "
                f'Last time you asked: "{truncated}" '
                f"Continue from there or ask something new!"
            )

        logger.info(
            "Scope selected: %s (previous: %s, returning: %s)",
            scope_id,
            previous_scope,
            is_returning,
        )

        return {
            "summary": welcome,
            "scope": scope_id,
            "previous_scope": previous_scope,
            "is_scope_change": True,
            "row_count": 0,
        }

    def get_scope_options(self, session: Session) -> dict[str, Any]:
        """Get available scope options for UI."""
        options = ScopeRegistry.get_options_for_api()

        # Mark current scope if any
        for opt in options:
            opt["is_current"] = opt["id"] == session.active_scope
            opt["is_visited"] = opt["id"] in session.scope_contexts

        return {
            "options": options,
            "current_scope": session.active_scope,
        }

    async def _dispatch_to_pipeline(
        self,
        message: str,
        session: Session,
    ) -> dict[str, Any]:
        """Dispatch to the active pipeline."""
        pipeline = ScopeRegistry.get(session.active_scope)
        scope_context = session.get_scope_context()

        response = await pipeline.process(message, session, scope_context)

        # Update scope context
        scope_context.add_query(message)

        # Tag response with scope
        response["scope"] = session.active_scope

        return response

    async def dispatch_stream(
        self,
        message: str,
        session: Session,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Dispatch to pipeline with streaming."""
        if session.active_scope is None:
            yield {"event": "error", "data": "Please select a scope first."}
            return

        pipeline = ScopeRegistry.get(session.active_scope)
        scope_context = session.get_scope_context()

        async for event in pipeline.process_stream(message, session, scope_context):
            yield event

        # Update scope context after completion
        scope_context.add_query(message)

    def _prompt_scope_selection(
        self,
        message: str,
        session: Session,
    ) -> dict[str, Any]:
        """Prompt user to select a scope."""
        options = ScopeRegistry.get_options_for_api()

        # Check if user typed something that looks like an option
        message_lower = message.lower()
        for opt in options:
            if opt["id"] in message_lower or opt["label"].lower() in message_lower:
                # Auto-select if user typed the scope name
                return self.select_scope(opt["id"], session)

        return {
            "summary": (
                "I'd love to help with that! Please select an option "
                "so I know how to assist you."
            ),
            "requires_scope": True,
            "options": options,
            "row_count": 0,
        }

    def _save_conversational_turn(
        self,
        session: Session,
        question: str,
        response: dict[str, Any],
    ) -> None:
        """Save non-pipeline conversational turns (greetings, help, etc.)."""
        user_turn = ConversationTurn(role="user", content=question)
        assistant_turn = ConversationTurn(
            role="assistant",
            content=response.get("summary", "")[:200],
        )
        session.add_turn(user_turn)
        session.add_turn(assistant_turn)
