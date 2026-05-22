"""
Document and Chunk dataclasses for the Document QA pipeline.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Document:
    """Represents a source document."""

    doc_id: str
    filename: str
    file_type: str  # "pdf", "docx", "txt"
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    indexed_at: float = field(default_factory=time.time)

    @classmethod
    def create(
        cls,
        filename: str,
        file_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> Document:
        """Factory to create a new document with generated ID."""
        return cls(
            doc_id=str(uuid.uuid4()),
            filename=filename,
            file_type=file_type,
            content=content,
            metadata=metadata or {},
        )


@dataclass
class Chunk:
    """Represents a chunk of a document for retrieval."""

    chunk_id: str
    doc_id: str
    text: str
    index: int  # Position within document
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        doc_id: str,
        text: str,
        index: int,
        metadata: dict[str, Any] | None = None,
    ) -> Chunk:
        """Factory to create a new chunk with generated ID."""
        return cls(
            chunk_id=str(uuid.uuid4()),
            doc_id=doc_id,
            text=text,
            index=index,
            metadata=metadata or {},
        )

    def to_store_metadata(self) -> dict[str, Any]:
        """Convert to metadata format for ChromaDB storage."""
        return {
            "doc_id": self.doc_id,
            "chunk_index": self.index,
            **self.metadata,
        }
