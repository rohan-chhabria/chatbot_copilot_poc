"""Tests for document management components."""

from __future__ import annotations

import pytest

from src.pipelines.document_qa.documents.models import Document, Chunk
from src.pipelines.document_qa.documents.chunker import RecursiveChunker, chunk_document


class TestDocumentModel:
    def test_create_document(self):
        doc = Document(
            doc_id="doc1",
            filename="test.pdf",
            file_type="pdf",
            content="This is test content.",
        )
        assert doc.doc_id == "doc1"
        assert doc.filename == "test.pdf"
        assert doc.file_type == "pdf"

    def test_document_with_metadata(self):
        doc = Document(
            doc_id="doc2",
            filename="test.txt",
            file_type="txt",
            content="Content",
            metadata={"author": "Test User"},
        )
        assert doc.metadata["author"] == "Test User"


class TestChunkModel:
    def test_create_chunk(self):
        chunk = Chunk(
            chunk_id="chunk1",
            doc_id="doc1",
            text="This is chunk text.",
            index=0,
        )
        assert chunk.chunk_id == "chunk1"
        assert chunk.doc_id == "doc1"
        assert chunk.index == 0


class TestRecursiveChunker:
    def test_chunk_short_text(self):
        chunker = RecursiveChunker(chunk_size=100, chunk_overlap=20)
        text = "This is a short text."
        chunks = chunker.split_text(text)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_chunk_long_text(self):
        chunker = RecursiveChunker(chunk_size=50, chunk_overlap=10)
        text = "A" * 200  # 200 characters
        chunks = chunker.split_text(text)
        assert len(chunks) > 1

    def test_chunk_with_paragraphs(self):
        chunker = RecursiveChunker(chunk_size=100, chunk_overlap=20)
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunker.split_text(text)
        assert len(chunks) >= 1


class TestChunkDocument:
    def test_chunk_document_basic(self):
        doc = Document(
            doc_id="doc1",
            filename="test.txt",
            file_type="txt",
            content="This is test content for chunking. " * 10,
        )
        chunks = chunk_document(doc, chunk_size=100, chunk_overlap=20)
        assert len(chunks) >= 1
        assert all(c.doc_id == "doc1" for c in chunks)
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_chunk_ids_are_unique(self):
        doc = Document(
            doc_id="doc1",
            filename="test.txt",
            file_type="txt",
            content="Content " * 100,
        )
        chunks = chunk_document(doc, chunk_size=50, chunk_overlap=10)
        chunk_ids = [c.chunk_id for c in chunks]
        assert len(chunk_ids) == len(set(chunk_ids))
