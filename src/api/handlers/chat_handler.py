"""
Chat Handler — Main chat orchestration logic.

Handles message processing through the orchestrator layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncGenerator

from src.orchestrator.state_machine import ScopeStateMachine
from src.session.models import Session
from src.shared.logger import get_logger

if TYPE_CHECKING:
    from src.memory.conversation_store import ConversationStore
    from src.session.session_manager import SessionStore

logger = get_logger(__name__)


class ChatHandler:
    """
    Handles chat message processing through the orchestrator.

    Coordinates:
    - Session management
    - Scope state machine
    - Pipeline dispatch
    - Response formatting
    """

    def __init__(
        self,
        session_store: SessionStore,
        conversation_store: ConversationStore,
    ):
        self._session_store = session_store
        self._conversation_store = conversation_store
        self._state_machine = ScopeStateMachine(conversation_store)

    async def handle_message(
        self,
        message: str,
        session: Session,
    ) -> dict[str, Any]:
        """
        Process a chat message through the orchestrator.

        Args:
            message: User's message
            session: Current session

        Returns:
            Response dict with summary, row_count, scope info, etc.
        """
        try:
            result = await self._state_machine.handle_message(message, session)
            self._session_store.save(session)
            return result
        except Exception as e:
            logger.exception("Chat handler error")
            return {
                "summary": f"An error occurred: {str(e)}",
                "row_count": 0,
                "error": str(e),
            }

    async def handle_message_stream(
        self,
        message: str,
        session: Session,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream a chat message response.

        Args:
            message: User's message
            session: Current session

        Yields:
            SSE event dicts with event type and data
        """
        # If no active scope, handle with state machine (non-streaming)
        if session.active_scope is None:
            result = await self._state_machine.handle_message(message, session)
            self._session_store.save(session)
            yield {"event": "result", "data": result}
            return

        # Stream from active pipeline
        try:
            async for event in self._state_machine.dispatch_stream(message, session):
                yield event
            self._session_store.save(session)
        except Exception as e:
            logger.exception("Chat stream handler error")
            yield {"event": "error", "data": str(e)}

    def select_scope(self, scope_id: str, session: Session) -> dict[str, Any]:
        """
        Select a scope for the session.

        Args:
            scope_id: Scope to select
            session: Current session

        Returns:
            Response dict with welcome message and scope info
        """
        result = self._state_machine.select_scope(scope_id, session)
        self._session_store.save(session)
        return result

    def get_scope_options(self, session: Session) -> dict[str, Any]:
        """
        Get available scope options for the session.

        Args:
            session: Current session

        Returns:
            Dict with options list and current_scope
        """
        return self._state_machine.get_scope_options(session)
