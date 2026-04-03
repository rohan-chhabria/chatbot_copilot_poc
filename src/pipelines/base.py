"""
Abstract base class for all pipelines.

Each pipeline handles a specific type of query (SQL, RAG, etc.)
and is registered with the ScopeRegistry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, AsyncGenerator

if TYPE_CHECKING:
    from src.session.models import ScopeContext, Session


class Pipeline(ABC):
    """
    Abstract base for capability pipelines.

    Each pipeline handles a specific type of query (SQL, RAG, etc.)
    and is registered with the ScopeRegistry.
    """

    # Class attributes for registry (set by @register_pipeline decorator)
    scope_id: str = ""  # "inmate_data", "document_qa"
    scope_label: str = ""  # "Inmate Data", "Documents"
    scope_icon: str = ""  # "📊", "📄"
    scope_description: str = ""  # "Query notes, inmates..."

    # If True, pipeline auto-executes on scope selection (with empty question)
    supports_auto_execute: bool = False

    @abstractmethod
    async def process(
        self,
        question: str,
        session: Session,
        scope_context: ScopeContext,
    ) -> dict[str, Any]:
        """
        Process a question and return response.

        Args:
            question: User's question
            session: Full session state
            scope_context: Scope-specific working memory

        Returns:
            Response dict with at minimum:
            - summary: str
            - row_count: int (or equivalent)
        """
        pass

    @abstractmethod
    async def process_stream(
        self,
        question: str,
        session: Session,
        scope_context: ScopeContext,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream response as SSE events.

        Yields dicts with:
        - {"event": "status", "data": "Processing..."}
        - {"event": "token", "data": "partial text"}
        - {"event": "result", "data": {full response}}
        - {"event": "error", "data": "error message"}
        """
        # This yield is required for the method to be a generator
        yield {}  # pragma: no cover

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        """
        Health check for this pipeline.

        Returns:
            {"status": "healthy"|"degraded"|"unhealthy", ...}
        """
        pass

    def get_welcome_message(self, is_returning: bool = False) -> str:
        """Get welcome message when entering this scope."""
        if is_returning:
            return f"Welcome back to {self.scope_label}. What would you like to know?"
        return f"Now helping with {self.scope_label}. {self.scope_description}"
