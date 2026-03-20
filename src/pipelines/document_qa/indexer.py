"""
Document Indexer — Handles document ingestion and indexing.

Provides both async and sync methods for indexing documents into ChromaDB.
Can index files from paths, bytes, or directories.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, BinaryIO

from openai import AsyncOpenAI

from src.pipelines.document_qa.documents.chunker import RecursiveChunker
from src.pipelines.document_qa.documents.loader import DocumentLoader
from src.pipelines.document_qa.documents.models import Document
from src.pipelines.document_qa.documents.store import TenantDocumentStore
from src.shared.config import DOC_EMBEDDING_MODEL, OPENAI_API_KEY
from src.shared.logger import get_logger

logger = get_logger(__name__)


class DocumentIndexer:
    """
    Indexes documents for the Document QA pipeline.

    Handles:
    - Loading documents (PDF, DOCX, TXT, MD)
    - Chunking with overlap
    - Embedding generation
    - Storage in tenant-isolated ChromaDB
    """

    def __init__(
        self,
        customer_key: str,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        embedding_model: str | None = None,
    ):
        self._customer_key = customer_key
        self._store = TenantDocumentStore(customer_key)
        self._loader = DocumentLoader()
        self._chunker = RecursiveChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self._openai = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self._embedding_model = embedding_model or DOC_EMBEDDING_MODEL

    async def index_file(self, file_path: str | Path) -> dict[str, Any]:
        """
        Index a single file.

        Args:
            file_path: Path to the file to index

        Returns:
            Result dict with doc_id, chunks_indexed, etc.
        """
        path = Path(file_path)
        logger.info("Indexing file: %s", path.name)

        try:
            # Load document
            doc = self._loader.load_file(path)
            return await self._index_document(doc)

        except Exception as e:
            logger.error("Failed to index %s: %s", path.name, e)
            return {
                "success": False,
                "filename": path.name,
                "error": str(e),
                "chunks_indexed": 0,
            }

    async def index_bytes(
        self,
        data: bytes | BinaryIO,
        filename: str,
        file_type: str,
    ) -> dict[str, Any]:
        """
        Index a document from bytes.

        Args:
            data: File content as bytes or file-like object
            filename: Original filename
            file_type: File extension (pdf, docx, txt, md)

        Returns:
            Result dict with doc_id, chunks_indexed, etc.
        """
        logger.info("Indexing bytes: %s (%s)", filename, file_type)

        try:
            doc = self._loader.load_bytes(data, filename, file_type)
            return await self._index_document(doc)

        except Exception as e:
            logger.error("Failed to index %s: %s", filename, e)
            return {
                "success": False,
                "filename": filename,
                "error": str(e),
                "chunks_indexed": 0,
            }

    async def index_directory(
        self,
        directory: str | Path,
        recursive: bool = True,
    ) -> dict[str, Any]:
        """
        Index all supported documents in a directory.

        Args:
            directory: Path to directory
            recursive: Whether to search subdirectories

        Returns:
            Summary dict with total files, chunks, failures
        """
        dir_path = Path(directory)
        if not dir_path.is_dir():
            raise ValueError(f"Not a directory: {directory}")

        logger.info("Indexing directory: %s (recursive=%s)", dir_path, recursive)

        # Find supported files
        supported = {".pdf", ".docx", ".txt", ".md"}
        if recursive:
            files = [f for f in dir_path.rglob("*") if f.suffix.lower() in supported]
        else:
            files = [f for f in dir_path.glob("*") if f.suffix.lower() in supported]

        results = {
            "success": True,
            "directory": str(dir_path),
            "files_found": len(files),
            "files_indexed": 0,
            "files_failed": 0,
            "total_chunks": 0,
            "details": [],
        }

        for file_path in files:
            result = await self.index_file(file_path)
            results["details"].append(result)

            if result.get("success"):
                results["files_indexed"] += 1
                results["total_chunks"] += result.get("chunks_indexed", 0)
            else:
                results["files_failed"] += 1

        results["success"] = results["files_failed"] == 0
        logger.info(
            "Directory indexing complete: %d/%d files, %d chunks",
            results["files_indexed"],
            results["files_found"],
            results["total_chunks"],
        )

        return results

    async def _index_document(self, doc: Document) -> dict[str, Any]:
        """Internal method to index a loaded document."""
        # Chunk the document
        chunks = self._chunker.chunk_document(doc)

        if not chunks:
            return {
                "success": True,
                "doc_id": doc.doc_id,
                "filename": doc.filename,
                "chunks_indexed": 0,
                "message": "Document has no content to index",
            }

        # Generate embeddings
        texts = [c.text for c in chunks]
        embeddings = await self._generate_embeddings(texts)

        # Prepare metadata
        metadata = [
            {
                "doc_id": doc.doc_id,
                "filename": doc.filename,
                "file_type": doc.file_type,
                "chunk_index": c.index,
                "indexed_at": doc.indexed_at,
                **c.metadata,
            }
            for c in chunks
        ]

        # Store in ChromaDB
        ids = self._store.add_chunks(texts, embeddings, metadata)

        logger.info(
            "Indexed %s: %d chunks",
            doc.filename,
            len(ids),
        )

        return {
            "success": True,
            "doc_id": doc.doc_id,
            "filename": doc.filename,
            "file_type": doc.file_type,
            "chunks_indexed": len(ids),
            "content_length": len(doc.content),
        }

    async def _generate_embeddings(
        self,
        texts: list[str],
        batch_size: int = 100,
    ) -> list[list[float]]:
        """Generate embeddings for texts in batches."""
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            response = await self._openai.embeddings.create(
                model=self._embedding_model,
                input=batch,
            )
            batch_embeddings = [e.embedding for e in response.data]
            all_embeddings.extend(batch_embeddings)

        return all_embeddings

    def list_documents(self) -> list[dict[str, Any]]:
        """List all indexed documents."""
        return self._store.list_documents()

    def delete_document(self, doc_id: str) -> int:
        """Delete a document and all its chunks."""
        deleted = self._store.delete_document(doc_id)
        logger.info("Deleted document %s: %d chunks removed", doc_id, deleted)
        return deleted

    def get_stats(self) -> dict[str, Any]:
        """Get indexing statistics."""
        docs = self._store.list_documents()
        return {
            "tenant": self._customer_key,
            "total_documents": len(docs),
            "total_chunks": self._store.count(),
            "documents": docs,
        }


# ── Convenience Functions ────────────────────────────────────────────────────


async def index_file_async(
    file_path: str | Path,
    customer_key: str = "demo",
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> dict[str, Any]:
    """Async convenience function to index a single file."""
    indexer = DocumentIndexer(
        customer_key=customer_key,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return await indexer.index_file(file_path)


def index_file(
    file_path: str | Path,
    customer_key: str = "demo",
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> dict[str, Any]:
    """Sync convenience function to index a single file."""
    return asyncio.run(
        index_file_async(file_path, customer_key, chunk_size, chunk_overlap)
    )


async def index_directory_async(
    directory: str | Path,
    customer_key: str = "demo",
    recursive: bool = True,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> dict[str, Any]:
    """Async convenience function to index a directory."""
    indexer = DocumentIndexer(
        customer_key=customer_key,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return await indexer.index_directory(directory, recursive=recursive)


def index_directory(
    directory: str | Path,
    customer_key: str = "demo",
    recursive: bool = True,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> dict[str, Any]:
    """Sync convenience function to index a directory."""
    return asyncio.run(
        index_directory_async(
            directory, customer_key, recursive, chunk_size, chunk_overlap
        )
    )


def get_index_stats(customer_key: str = "demo") -> dict[str, Any]:
    """Get indexing statistics for a tenant."""
    indexer = DocumentIndexer(customer_key=customer_key)
    return indexer.get_stats()
