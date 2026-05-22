"""
Document QA Pipeline — RAG-based document search.

This pipeline handles document-related queries using:
- ChromaDB for vector storage (tenant-isolated)
- Hybrid search (semantic + BM25)
- LLM-based answer synthesis

Auto-registers with ScopeRegistry on import.
"""

from src.pipelines.document_qa.indexer import (
    DocumentIndexer,
    get_index_stats,
    index_directory,
    index_directory_async,
    index_file,
    index_file_async,
)
from src.pipelines.document_qa.pipeline import DocumentQAPipeline

__all__ = [
    "DocumentQAPipeline",
    "DocumentIndexer",
    "index_file",
    "index_file_async",
    "index_directory",
    "index_directory_async",
    "get_index_stats",
]
