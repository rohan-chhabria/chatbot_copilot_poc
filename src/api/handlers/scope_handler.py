"""
Scope Handler — Scope selection and management.

Handles scope-related operations independently of chat flow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.orchestrator.scope_registry import ScopeRegistry
from src.shared.exceptions import ScopeError
from src.shared.logger import get_logger

if TYPE_CHECKING:
    from src.session.models import Session
    from src.session.session_manager import SessionStore

logger = get_logger(__name__)


class ScopeHandler:
    """
    Handles scope selection and management.

    Provides:
    - Scope selection
    - Scope options listing
    - Scope validation
    """

    def __init__(self, session_store: SessionStore):
        self._session_store = session_store

    def select_scope(self, scope_id: str, session: Session) -> dict[str, Any]:
        """
        Select a scope for the session.

        Args:
            scope_id: Scope to select (e.g., "inmate_data", "document_qa")
            session: Session to update

        Returns:
            Response dict with welcome message and scope info

        Raises:
            ScopeError: If scope is invalid
        """
        if not ScopeRegistry.is_valid_scope(scope_id):
            raise ScopeError(f"Invalid scope: {scope_id}")

        previous_scope = session.active_scope
        is_returning = scope_id in session.scope_contexts

        # Switch scope
        scope_context = session.switch_scope(scope_id)

        # Get pipeline welcome message
        pipeline = ScopeRegistry.get(scope_id)
        welcome = pipeline.get_welcome_message(is_returning)

        # Add context reminder for returning users
        if is_returning and scope_context.recent_queries:
            last_query = scope_context.recent_queries[-1]
            truncated = last_query[:50] + "..." if len(last_query) > 50 else last_query
            welcome = (
                f"Welcome back to {pipeline.scope_label}. "
                f'Last time you asked: "{truncated}" '
                f"Continue from there or ask something new!"
            )

        # Save session
        self._session_store.save(session)

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

    def get_options(self, session: Session | None = None) -> dict[str, Any]:
        """
        Get available scope options.

        Args:
            session: Optional session to mark current/visited scopes

        Returns:
            Dict with options list and current_scope
        """
        options = ScopeRegistry.get_options_for_api()

        # Mark current and visited if session provided
        if session:
            for opt in options:
                opt["is_current"] = opt["id"] == session.active_scope
                opt["is_visited"] = opt["id"] in session.scope_contexts

        return {
            "options": options,
            "current_scope": session.active_scope if session else None,
        }

    def validate_scope(self, scope_id: str) -> bool:
        """Check if a scope is valid and enabled."""
        return ScopeRegistry.is_valid_scope(scope_id)

    def get_scope_definition(self, scope_id: str) -> dict[str, Any] | None:
        """Get scope definition metadata."""
        defn = ScopeRegistry.get_definition(scope_id)
        if not defn:
            return None
        return {
            "id": defn.id,
            "label": defn.label,
            "icon": defn.icon,
            "description": defn.description,
            "category": defn.category,
            "enabled": defn.enabled,
        }

    def list_scopes_by_category(self) -> dict[str, list[dict[str, Any]]]:
        """Get scopes grouped by category."""
        by_category = ScopeRegistry.get_by_category()
        result: dict[str, list[dict[str, Any]]] = {}

        for category, scopes in by_category.items():
            result[category] = [
                {
                    "id": s.id,
                    "label": s.label,
                    "icon": s.icon,
                    "description": s.description,
                }
                for s in scopes
            ]

        return result
