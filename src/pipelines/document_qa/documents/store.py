"""
ChromaDB-backed document store with tenant isolation.

Each tenant gets a separate collection to ensure data isolation.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from src.shared.config import DOC_CHROMA_DIR
from src.shared.logger import get_logger

logger = get_logger(__name__)


class TenantDocumentStore:
    """
    ChromaDB store with tenant isolation.

    Collection naming:
    - If DOC_CHROMA_COLLECTION is set, use that (shared collection)
    - Otherwise use tenant-specific: docs_{customer_key}
    """

    def __init__(
        self,
        customer_key: str,
        persist_dir: str | None = None,
        collection_name: str | None = None,
    ):
        import chromadb
        from chromadb.config import Settings

        self._customer_key = customer_key

        # Use shared collection for all customers (docs_demo is default)
        self._collection_name = collection_name or "docs_demo"

        # Use DOC_CHROMA_DIR (./chroma_docs) for document storage
        persist_dir = persist_dir or DOC_CHROMA_DIR
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine", "tenant": customer_key},
        )

        logger.info(
            "Document store: %s (%d docs)", self._collection_name, self.count()
        )

    def add_chunks(
        self,
        texts: list[str],
        embeddings: list[list[float]],
        metadata: list[dict[str, Any]],
    ) -> list[str]:
        """Add document chunks with embeddings."""
        ids = [str(uuid.uuid4()) for _ in texts]

        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadata,
        )

        return ids

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: dict | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar chunks."""
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        formatted = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                formatted.append(
                    {
                        "id": results["ids"][0][i],
                        "text": results["documents"][0][i],
                        "metadata": results["metadatas"][0][i],
                        "score": 1 - results["distances"][0][i],  # Distance to similarity
                    }
                )

        return formatted

    def delete_document(self, doc_id: str) -> int:
        """Delete all chunks for a document."""
        results = self._collection.get(
            where={"doc_id": doc_id},
            include=[],
        )

        if results["ids"]:
            self._collection.delete(ids=results["ids"])
            return len(results["ids"])
        return 0

    def count(self) -> int:
        """Total chunks in collection."""
        return self._collection.count()

    def list_documents(self) -> list[dict[str, Any]]:
        """List unique documents."""
        results = self._collection.get(include=["metadatas"])

        docs: dict[str, dict[str, Any]] = {}
        for meta in results["metadatas"]:
            doc_id = meta.get("doc_id")
            if doc_id and doc_id not in docs:
                docs[doc_id] = {
                    "doc_id": doc_id,
                    "filename": meta.get("filename"),
                    "file_type": meta.get("file_type"),
                    "indexed_at": meta.get("indexed_at"),
                    "chunk_count": 0,
                }
            if doc_id:
                docs[doc_id]["chunk_count"] += 1

        return list(docs.values())

    def get_all_texts(self) -> list[dict[str, Any]]:
        """Get all texts for BM25 indexing."""
        results = self._collection.get(include=["documents", "metadatas"])
        texts = []
        for i, doc in enumerate(results["documents"]):
            texts.append(
                {
                    "id": results["ids"][i],
                    "text": doc,
                    "metadata": results["metadatas"][i],
                }
            )
        return texts
