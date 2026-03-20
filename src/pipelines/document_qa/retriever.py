"""
Hybrid retriever: Semantic + BM25 with RRF fusion.

Combines:
- Semantic search (ChromaDB embeddings)
- BM25 keyword search
- Reciprocal Rank Fusion (RRF)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

from src.shared.config import (
    DOC_EMBEDDING_MODEL,
    DOC_HYBRID_SEARCH,
    DOC_RETRIEVAL_TOP_K,
    OPENAI_API_KEY,
)
from src.shared.logger import get_logger

if TYPE_CHECKING:
    from src.pipelines.document_qa.documents.store import TenantDocumentStore
    from src.session.models import ScopeContext

logger = get_logger(__name__)


class DocumentRetriever:
    """
    Retrieves relevant document chunks via hybrid search.

    Combines:
    - Semantic search (ChromaDB embeddings)
    - BM25 keyword search
    - Reciprocal Rank Fusion (RRF)
    """

    def __init__(self):
        self._openai = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self._embedding_model = DOC_EMBEDDING_MODEL
        self._bm25_indices: dict[str, Any] = {}
        self._bm25_docs: dict[str, list[dict]] = {}

    async def retrieve(
        self,
        question: str,
        store: TenantDocumentStore,
        top_k: int | None = None,
        context: ScopeContext | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant chunks for a question."""
        top_k = top_k or DOC_RETRIEVAL_TOP_K

        # Get query embedding
        embedding = await self._get_embedding(question)

        # Semantic search
        semantic_results = store.search(
            query_embedding=embedding,
            top_k=top_k * 4,  # Get more for fusion
        )

        if not DOC_HYBRID_SEARCH or store.count() == 0:
            return semantic_results[:top_k]

        # BM25 search
        bm25_results = self._bm25_search(question, store, top_k * 4)

        # RRF fusion
        fused = self._reciprocal_rank_fusion(
            semantic_results,
            bm25_results,
            top_k,
        )

        # Context-aware boosting
        if context and context.recent_entities.get("last_docs"):
            fused = self._boost_recent_docs(
                fused,
                context.recent_entities["last_docs"],
            )

        # Deduplicate
        fused = self._deduplicate(fused)

        return fused[:top_k]

    async def _get_embedding(self, text: str) -> list[float]:
        """Generate embedding for text."""
        response = await self._openai.embeddings.create(
            model=self._embedding_model,
            input=text,
        )
        return response.data[0].embedding

    def _bm25_search(
        self,
        question: str,
        store: TenantDocumentStore,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """BM25 keyword search."""
        tenant = store._customer_key

        # Build/update BM25 index if needed
        if tenant not in self._bm25_indices:
            self._build_bm25_index(store)

        if tenant not in self._bm25_indices:
            return []

        # Tokenize query
        tokens = self._tokenize(question)

        # Score documents
        scores = self._bm25_indices[tenant].get_scores(tokens)

        # Rank
        ranked = sorted(
            enumerate(scores),
            key=lambda x: x[1],
            reverse=True,
        )[:top_k]

        # Return with scores
        results = []
        for idx, score in ranked:
            if score > 0 and idx < len(self._bm25_docs.get(tenant, [])):
                doc = self._bm25_docs[tenant][idx].copy()
                doc["bm25_score"] = float(score)
                results.append(doc)

        return results

    def _build_bm25_index(self, store: TenantDocumentStore) -> None:
        """Build BM25 index for a tenant's documents."""
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            logger.warning("rank_bm25 not installed, skipping BM25 index")
            return

        tenant = store._customer_key

        # Get all documents
        all_texts = store.get_all_texts()

        if not all_texts:
            return

        docs = []
        tokenized = []

        for item in all_texts:
            docs.append(
                {
                    "id": item["id"],
                    "text": item["text"],
                    "metadata": item["metadata"],
                    "score": 0,
                }
            )
            tokenized.append(self._tokenize(item["text"]))

        self._bm25_docs[tenant] = docs
        self._bm25_indices[tenant] = BM25Okapi(tokenized)

        logger.info("Built BM25 index for %s: %d docs", tenant, len(docs))

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenizer for BM25."""
        return re.findall(r"\w+", text.lower())

    def _reciprocal_rank_fusion(
        self,
        semantic: list[dict],
        keyword: list[dict],
        top_k: int,
        k: int = 60,
    ) -> list[dict]:
        """
        Merge two ranked lists with RRF.

        RRF score = sum(1 / (k + rank)) for each list
        """
        scores: dict[str, float] = {}
        docs_by_id: dict[str, dict] = {}

        # Score semantic results
        for rank, doc in enumerate(semantic):
            doc_id = doc["id"]
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
            docs_by_id[doc_id] = doc

        # Score keyword results
        for rank, doc in enumerate(keyword):
            doc_id = doc["id"]
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
            if doc_id not in docs_by_id:
                docs_by_id[doc_id] = doc

        # Sort by RRF score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Build result list
        results = []
        for doc_id, rrf_score in ranked[:top_k]:
            doc = docs_by_id[doc_id].copy()
            doc["rrf_score"] = rrf_score
            results.append(doc)

        return results

    def _boost_recent_docs(
        self,
        results: list[dict],
        recent_docs: list[str],
        boost: float = 0.1,
    ) -> list[dict]:
        """Boost scores for chunks from recently accessed documents."""
        for r in results:
            if r["metadata"].get("filename") in recent_docs:
                r["score"] = min(1.0, r.get("score", 0) + boost)

        return sorted(results, key=lambda x: x.get("score", 0), reverse=True)

    def _deduplicate(
        self,
        results: list[dict],
        threshold: float = 0.8,
    ) -> list[dict]:
        """Remove near-duplicate chunks."""
        unique = []
        seen_texts: list[str] = []

        for r in results:
            text = r["text"]
            is_duplicate = False

            for seen in seen_texts:
                if self._text_overlap(text, seen) > threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique.append(r)
                seen_texts.append(text)

        return unique

    def _text_overlap(self, text1: str, text2: str) -> float:
        """Calculate word overlap ratio."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union
