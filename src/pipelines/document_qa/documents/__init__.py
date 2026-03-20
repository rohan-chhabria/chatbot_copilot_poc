"""
Document management components.

- store: ChromaDB-backed tenant-isolated document store
- loader: PDF, DOCX, TXT parsing
- chunker: Recursive text chunking
- models: Document, Chunk dataclasses
"""

from src.pipelines.document_qa.documents.models import Chunk, Document
from src.pipelines.document_qa.documents.store import TenantDocumentStore

__all__ = ["Document", "Chunk", "TenantDocumentStore"]
