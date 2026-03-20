"""
Document Q&A Pipeline using RAG.

Flow:
  1. Validate question
  2. Retrieve relevant chunks (hybrid search)
  3. Synthesize answer (LLM)
  4. Format response with sources
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, AsyncGenerator

from src.orchestrator.scope_registry import register_pipeline
from src.pipelines.base import Pipeline
from src.pipelines.document_qa.documents.store import TenantDocumentStore
from src.pipelines.document_qa.retriever import DocumentRetriever
from src.pipelines.document_qa.synthesizer import ResponseSynthesizer
from src.shared.logger import get_logger

if TYPE_CHECKING:
    from src.session.models import ScopeContext, Session

logger = get_logger(__name__)


@register_pipeline(
    scope_id="document_qa",
    label="Documents",
    icon="📄",
    description="Search manuals, guides, and policies",
    category="Information",
)
class DocumentQAPipeline(Pipeline):
    """
    Document Q&A Pipeline using RAG.

    Flow:
      1. Validate question
      2. Retrieve relevant chunks (hybrid search)
      3. Synthesize answer (LLM)
      4. Format response with sources
    """

    def __init__(self):
        self._stores: dict[str, TenantDocumentStore] = {}
        self._retriever = DocumentRetriever()
        self._synthesizer = ResponseSynthesizer()

    def _get_store(self, customer_key: str) -> TenantDocumentStore:
        """Get or create tenant-specific document store."""
        if customer_key not in self._stores:
            self._stores[customer_key] = TenantDocumentStore(customer_key)
        return self._stores[customer_key]

    async def process(
        self,
        question: str,
        session: Session,
        scope_context: ScopeContext,
    ) -> dict[str, Any]:
        """Process a document question."""
        store = self._get_store(session.customer_key)

        # Check if any documents indexed
        if store.count() == 0:
            return {
                "summary": (
                    "No documents have been indexed yet. "
                    "Please contact your administrator to add documents."
                ),
                "sources": [],
                "row_count": 0,
            }

        # Retrieve relevant chunks
        chunks = await self._retriever.retrieve(
            question=question,
            store=store,
            context=scope_context,
        )

        if not chunks:
            return {
                "summary": (
                    "I couldn't find any relevant information in the documents. "
                    "Try rephrasing your question or check if the topic is covered."
                ),
                "sources": [],
                "row_count": 0,
            }

        # Synthesize response
        response = await self._synthesizer.synthesize(
            question=question,
            chunks=chunks,
        )

        # Update scope context
        scope_context.add_query(question)
        scope_context.update_entity(
            "last_docs",
            [c["metadata"].get("filename") for c in chunks[:3]],
        )

        return {
            "summary": response["answer"],
            "sources": response["sources"],
            "row_count": len(chunks),
            "chunks_used": len(chunks),
        }

    async def process_stream(
        self,
        question: str,
        session: Session,
        scope_context: ScopeContext,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream document QA response."""
        yield {"event": "status", "data": "Searching documents..."}

        store = self._get_store(session.customer_key)

        if store.count() == 0:
            yield {"event": "error", "data": "No documents indexed."}
            return

        chunks = await self._retriever.retrieve(
            question=question,
            store=store,
            context=scope_context,
        )

        if not chunks:
            yield {
                "event": "result",
                "data": {
                    "summary": "No relevant documents found.",
                    "sources": [],
                },
            }
            return

        yield {
            "event": "status",
            "data": f"Found {len(chunks)} relevant sections...",
        }

        async for event in self._synthesizer.synthesize_stream(question, chunks):
            yield event

        # Update context
        scope_context.add_query(question)

    async def health(self) -> dict[str, Any]:
        """Health check."""
        return {
            "status": "healthy",
            "stores_loaded": len(self._stores),
        }

    def get_welcome_message(self, is_returning: bool = False) -> str:
        """Get welcome message when entering this scope."""
        if is_returning:
            return (
                "Welcome back to Documents. "
                "I remember your previous searches. What would you like to find?"
            )
        return (
            "Now helping with Documents. "
            "You can search manuals, policies, guides, and other documents. "
            "What would you like to find?"
        )
