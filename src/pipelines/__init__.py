"""
Pipelines package — modular capability pipelines.

Each pipeline handles a specific type of query:
- inmate_data: SQL-based queries via Vanna
- document_qa: RAG-based document search
"""

from src.pipelines.base import Pipeline

__all__ = ["Pipeline"]
