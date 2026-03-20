"""
Inmate Data Pipeline — wraps existing Vanna/SQL functionality.

This is the main pipeline class that integrates the existing agent
functionality with the new orchestrator architecture.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, AsyncGenerator

from src.orchestrator.scope_registry import register_pipeline
from src.pipelines.base import Pipeline
from src.shared.logger import get_logger

if TYPE_CHECKING:
    from src.session.models import ScopeContext, Session

logger = get_logger(__name__)


@register_pipeline(
    scope_id="inmate_data",
    label="Inmate Data",
    icon="📊",
    description="Query notes, inmates, officers, and facilities",
    category="Data & Analytics",
)
class InmateDataPipeline(Pipeline):
    """
    Inmate Data Pipeline using Vanna for text-to-SQL.

    Wraps the existing AgentPipeline with the new Pipeline interface.
    """

    def __init__(self):
        from src.memory.conversation_store import create_conversation_store
        from src.session.session_manager import create_session_store

        self._session_store = create_session_store()
        self._conversation_store = create_conversation_store()
        self._vanna_pipeline = None  # Lazy init

    def _get_vanna_pipeline(self):
        """Lazy initialization of the Vanna pipeline."""
        if self._vanna_pipeline is None:
            from src.pipelines.inmate_data.vanna_agent import AgentPipeline

            self._vanna_pipeline = AgentPipeline(
                session_store=self._session_store,
                conversation_store=self._conversation_store,
            )
        return self._vanna_pipeline

    async def process(
        self,
        question: str,
        session: Session,
        scope_context: ScopeContext,
    ) -> dict[str, Any]:
        """Process a data query."""
        from src.tenant.tenant_router import resolve_tenant

        # Get tenant context
        tenant = resolve_tenant(session.customer_key)

        # Use existing Vanna pipeline
        pipeline = self._get_vanna_pipeline()
        response = await pipeline.process_question(
            question=question,
            session=session,
            tenant=tenant,
        )

        # Update scope context with entities
        self._extract_entities(response, scope_context)

        return response

    async def process_stream(
        self,
        question: str,
        session: Session,
        scope_context: ScopeContext,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a data query response."""
        from src.tenant.tenant_router import resolve_tenant

        tenant = resolve_tenant(session.customer_key)
        pipeline = self._get_vanna_pipeline()

        async for event in pipeline.process_question_stream(
            question=question,
            session=session,
            tenant=tenant,
        ):
            yield event

    async def health(self) -> dict[str, Any]:
        """Check pipeline health."""
        from src.pipelines.inmate_data.vanna_agent import get_agent_memory, get_llm_service

        llm_ok = get_llm_service() is not None
        memory_ok = get_agent_memory() is not None

        return {
            "status": "healthy" if (llm_ok and memory_ok) else "degraded",
            "llm": "ok" if llm_ok else "unavailable",
            "memory": "ok" if memory_ok else "unavailable",
        }

    def _extract_entities(self, response: dict, scope_context: ScopeContext) -> None:
        """Extract entities (inmate names, etc.) from response for context."""
        summary = response.get("summary", "")

        # Extract inmate names (bold pattern)
        names = re.findall(r"\*\*([A-Z][a-z]+ [A-Z][a-z]+)\*\*", summary)
        if names:
            scope_context.update_entity("inmate_name", names[0])

        # Extract facility names
        facilities = re.findall(
            r"(?:Dorm|Facility|Building)\s+([A-Z0-9]+)", summary
        )
        if facilities:
            scope_context.update_entity("facility", facilities[0])

        # Extract row count
        row_count = response.get("row_count", 0)
        if row_count:
            scope_context.update_entity("last_row_count", row_count)

    def get_welcome_message(self, is_returning: bool = False) -> str:
        """Get welcome message when entering this scope."""
        if is_returning:
            return (
                "Welcome back to Inmate Data. "
                "I remember your previous queries. What would you like to know?"
            )
        return (
            "Now helping with Inmate Data. "
            "You can ask about notes, inmates, officers, facilities, "
            "keywords, movements, and more. What would you like to know?"
        )
