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

import re
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
        self._cross_scope = CrossScopeHandler(conversation_store=conversation_store)

    async def handle_message(
        self,
        message: str,
        session: Session,
    ) -> dict[str, Any]:
        """
        Main entry point for message handling.

        Returns response dict or routes to appropriate pipeline.
        """
        logger.debug(
            "handle_message: message=%r, session=%s, active_scope=%s",
            message[:100],
            session.session_id[:8],
            session.active_scope,
        )

        original_message = message
        message = message.strip()
        dispatch_message = message
        scope_context_message = message
        rewrite_kind: str | None = None

        dispatch_message, scope_context_message, early_response, rewrite_kind = self._resolve_memory_commands(
            message=message,
            session=session,
        )
        if early_response is not None:
            self._record_turn_pair(session, original_message, early_response)
            return early_response

        # 1. Check cross-scope handlers (greetings, recall, help)
        cross_scope_response = self._cross_scope.handle(dispatch_message, session)
        if cross_scope_response:
            logger.debug(
                "Cross-scope handled: type=%s",
                "greeting" if cross_scope_response.get("is_greeting") else
                "farewell" if cross_scope_response.get("is_farewell") else
                "help" if cross_scope_response.get("is_help") else
                "recall" if cross_scope_response.get("is_recall") else "unknown",
            )
            self._record_turn_pair(session, original_message, cross_scope_response)
            self._store_recall_index_map(session, cross_scope_response)
            return cross_scope_response

        # 2. No active scope? Prompt for selection
        if session.active_scope is None:
            logger.debug("No active scope, prompting selection")
            result = self._prompt_scope_selection(dispatch_message, session)
            self._record_turn_pair(session, original_message, result)
            return result

        # 3. Route to active pipeline
        logger.debug("Dispatching to pipeline: %s", session.active_scope)
        result = await self._dispatch_to_pipeline(dispatch_message, session, scope_context_message)
        if rewrite_kind:
            result[f"{rewrite_kind}_rewrite"] = True
        self._record_turn_pair(session, original_message, result)
        return result

    def select_scope(self, scope_id: str, session: Session) -> dict[str, Any]:
        """
        User selected a scope (clicked option block).

        Returns welcome message for the scope.
        For pipelines with supports_auto_execute=True, returns auto_execute flag
        so the API layer can trigger the pipeline execution.
        """
        if not ScopeRegistry.is_valid_scope(scope_id):
            raise ScopeError(f"Invalid scope: {scope_id}")

        previous_scope = session.active_scope
        is_returning = scope_id in session.scope_contexts

        # Switch scope (preserves previous context)
        scope_context = session.switch_scope(scope_id)
        self._clear_recall_index_map(scope_context)

        # Get pipeline welcome
        pipeline = ScopeRegistry.get(scope_id)
        welcome = pipeline.get_welcome_message(is_returning)

        # If returning, add context reminder (for non-auto-execute pipelines)
        if is_returning and scope_context.recent_queries and not pipeline.supports_auto_execute:
            last_query = scope_context.recent_queries[-1]
            truncated = last_query[:50] + "..." if len(last_query) > 50 else last_query
            welcome = f'Welcome back to {pipeline.scope_label}. Last time you asked: "{truncated}".'
            welcome += " Continue from there or ask something new!"

        logger.info(
            "Scope selected: %s (previous: %s, returning: %s, auto_execute: %s)",
            scope_id,
            previous_scope,
            is_returning,
            pipeline.supports_auto_execute,
        )

        return {
            "summary": welcome,
            "scope": scope_id,
            "previous_scope": previous_scope,
            "is_scope_change": True,
            "row_count": 0,
            "auto_execute": pipeline.supports_auto_execute,
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
        scope_context_message: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch to the active pipeline."""
        logger.debug(
            "Dispatching to pipeline: scope=%s, message=%r",
            session.active_scope,
            message[:80],
        )

        pipeline = ScopeRegistry.get(session.active_scope)
        scope_context = session.get_scope_context()

        logger.debug("Calling pipeline.process()...")
        response = await pipeline.process(message, session, scope_context)

        logger.debug(
            "Pipeline returned: row_count=%s, has_summary=%s",
            response.get("row_count"),
            bool(response.get("summary")),
        )

        self._update_scope_context(session, scope_context_message or message, response)

        # Tag response with scope
        response["scope"] = session.active_scope

        return response

    async def dispatch_stream(
        self,
        message: str,
        session: Session,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Dispatch to pipeline with streaming."""
        logger.debug(
            "dispatch_stream: scope=%s, message=%r",
            session.active_scope,
            message[:80],
        )

        original_message = message
        message = message.strip()
        dispatch_message = message
        scope_context_message = message
        rewrite_kind: str | None = None

        dispatch_message, scope_context_message, early_response, rewrite_kind = self._resolve_memory_commands(
            message=message,
            session=session,
        )
        if early_response is not None:
            self._record_turn_pair(session, original_message, early_response)
            yield {"event": "result", "data": early_response}
            return

        cross_scope_response = self._cross_scope.handle(dispatch_message, session)
        if cross_scope_response:
            logger.debug(
                "Cross-scope handled in stream path: type=%s",
                "greeting" if cross_scope_response.get("is_greeting") else
                "farewell" if cross_scope_response.get("is_farewell") else
                "help" if cross_scope_response.get("is_help") else
                "self_identity" if cross_scope_response.get("is_self_identity") else
                "recall" if cross_scope_response.get("is_recall") else "unknown",
            )
            self._record_turn_pair(session, original_message, cross_scope_response)
            self._store_recall_index_map(session, cross_scope_response)
            yield {"event": "result", "data": cross_scope_response}
            return

        if session.active_scope is None:
            logger.debug("No scope selected, returning error")
            yield {"event": "error", "data": "Please select a scope first."}
            return

        pipeline = ScopeRegistry.get(session.active_scope)
        scope_context = session.get_scope_context()

        logger.debug("Starting pipeline stream...")
        event_count = 0
        final_result: dict[str, Any] | None = None
        last_error: str | None = None
        async for event in pipeline.process_stream(dispatch_message, session, scope_context):
            event_count += 1
            if event.get("event") == "result" and isinstance(event.get("data"), dict):
                final_result = event["data"]
            if event.get("event") == "error":
                payload = event.get("data")
                last_error = payload if isinstance(payload, str) else str(payload)
            yield event

        logger.debug("Pipeline stream complete: %d events", event_count)

        if final_result:
            final_result["scope"] = session.active_scope
            if rewrite_kind:
                final_result[f"{rewrite_kind}_rewrite"] = True
            self._update_scope_context(session, scope_context_message, final_result)
            self._record_turn_pair(session, original_message, final_result)
        elif last_error:
            self._record_turn_pair(
                session,
                original_message,
                {"summary": f"Error: {last_error}", "error": last_error, "row_count": 0},
            )

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

    def _update_scope_context(
        self,
        session: Session,
        question: str,
        response: dict[str, Any],
    ) -> None:
        scope_context = session.get_scope_context()
        if scope_context is None:
            return
        if question.strip():
            scope_context.add_query(question)
            self._clear_recall_index_map(scope_context)
        summary = response.get("summary", "").strip()
        if summary:
            truncated = summary[:120] + ("..." if len(summary) > 120 else "")
            scope_context.update_entity("last_assistant_summary", truncated)

    def _record_turn_pair(
        self,
        session: Session,
        question: str,
        response: dict[str, Any],
    ) -> None:
        """Persist user/assistant turns for all message flows."""
        if not question.strip():
            return

        assistant_content = response.get("summary", "")
        if not assistant_content and response.get("error"):
            assistant_content = str(response["error"])

        metadata = {
            "is_recall": bool(response.get("is_recall")),
            "is_help": bool(response.get("is_help")),
            "is_greeting": bool(response.get("is_greeting")),
            "is_farewell": bool(response.get("is_farewell")),
            "continue_rewrite": bool(response.get("continue_rewrite")),
            "revisit_rewrite": bool(response.get("revisit_rewrite")),
        }

        user_turn = ConversationTurn(role="user", content=question)
        assistant_turn = ConversationTurn(
            role="assistant",
            content=assistant_content[:300],
            sql=response.get("sql", "") or "",
            row_count=int(response.get("row_count", 0) or 0),
            metadata=metadata,
        )
        session.add_turn(user_turn)
        session.add_turn(assistant_turn)
        if self._conversation_store is not None:
            self._conversation_store.save_turn(session, user_turn)
            self._conversation_store.save_turn(session, assistant_turn)

    def _is_continue_request(self, message: str) -> bool:
        return bool(
            re.search(
                r"\b(continue|go\s+on|carry\s+on|pick\s+up|resume|continue\s+that|continue\s+from\s+there)\b",
                message,
                re.I,
            ),
        )

    def _extract_revisit_index(self, message: str, session: Session) -> int | None:
        normalized = re.sub(r"\s+", " ", message.lower().strip())
        patterns = [
            r"^(?:revisit|revist|review)\s*(?:question\s*)?(\d+)(?:\s*from\s*list)?$",
            r"^(?:yes)\s+(\d+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, normalized, re.I)
            if not match:
                continue
            if pattern.startswith("^(?:yes)") and not self._has_recall_index_map(session):
                return None
            return int(match.group(1))
        return None

    def _has_recall_index_map(self, session: Session) -> bool:
        scope_context = session.get_scope_context()
        if scope_context is None:
            return False
        return isinstance(scope_context.recent_entities.get("recall_index_map"), dict)

    def _resolve_continue_question(self, session: Session) -> str | None:
        last_user_turn = session.get_last_turn(role="user")
        if not last_user_turn:
            return None
        return last_user_turn.content.strip() or None

    def _resolve_memory_commands(
        self,
        message: str,
        session: Session,
    ) -> tuple[str, str, dict[str, Any] | None, str | None]:
        dispatch_message = message
        scope_context_message = message

        if not session.active_scope:
            return dispatch_message, scope_context_message, None, None

        revisit_index = self._extract_revisit_index(message, session)
        if revisit_index is not None:
            revisit_question = self._resolve_revisit_question(session, revisit_index)
            if revisit_question is None:
                return (
                    dispatch_message,
                    scope_context_message,
                    {
                        "summary": (
                            f"I couldn't find item {revisit_index} in your latest recall list. "
                            "Ask 'what have i asked?' first, then say 'revisit N'."
                        ),
                        "row_count": 0,
                    },
                    None,
                )
            return revisit_question, revisit_question, None, "revisit"

        if self._is_continue_request(message):
            continued_question = self._resolve_continue_question(session)
            if continued_question is None:
                return (
                    dispatch_message,
                    scope_context_message,
                    {
                        "summary": "I don't have a recent question in this scope yet. Ask one, then I can continue from it.",
                        "row_count": 0,
                    },
                    None,
                )
            return continued_question, continued_question, None, "continue"

        return dispatch_message, scope_context_message, None, None

    def _resolve_revisit_question(self, session: Session, revisit_index: int) -> str | None:
        if revisit_index < 1:
            return None
        scope_context = session.get_scope_context()
        if scope_context is None:
            return None

        recall_map = scope_context.recent_entities.get("recall_index_map")
        recall_scope = scope_context.recent_entities.get("recall_index_scope")
        recall_turn_count = scope_context.recent_entities.get("recall_index_user_turn_count")
        if not isinstance(recall_map, dict) or recall_scope != session.active_scope:
            return None

        if not isinstance(recall_turn_count, int):
            return None

        current_turn_count = len([t for t in session.get_turns_for_scope() if t.role == "user"])
        if current_turn_count != recall_turn_count:
            return None

        question = recall_map.get(str(revisit_index))
        if not isinstance(question, str) or not question.strip():
            return None
        return question.strip()

    def _store_recall_index_map(self, session: Session, response: dict[str, Any]) -> None:
        if not response.get("is_recall"):
            return
        scope_context = session.get_scope_context()
        if scope_context is None:
            return
        recall_items = response.get("recall_items")
        if not isinstance(recall_items, list) or not recall_items:
            return

        recall_map: dict[str, str] = {}
        for item in recall_items:
            if not isinstance(item, dict):
                continue
            index = item.get("index")
            content = item.get("content")
            if isinstance(index, int) and isinstance(content, str) and content.strip():
                recall_map[str(index)] = content.strip()

        if not recall_map:
            return

        scope_context.update_entity("recall_index_map", recall_map)
        scope_context.update_entity("recall_index_scope", session.active_scope)
        scope_context.update_entity(
            "recall_index_user_turn_count",
            len([t for t in session.get_turns_for_scope() if t.role == "user"]),
        )

    def _clear_recall_index_map(self, scope_context: Any) -> None:
        if not hasattr(scope_context, "recent_entities"):
            return
        for key in ("recall_index_map", "recall_index_scope", "recall_index_user_turn_count"):
            if key in scope_context.recent_entities:
                del scope_context.recent_entities[key]
