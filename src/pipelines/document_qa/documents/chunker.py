"""
Text chunker for document processing.

Uses recursive character-based splitting with overlap.
"""

from __future__ import annotations

from src.pipelines.document_qa.documents.models import Chunk, Document


class RecursiveChunker:
    """
    Recursively chunks text using separators.

    Tries to split on paragraphs, then sentences, then words.
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        separators: list[str] | None = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", ". ", " ", ""]

    def split_text(self, text: str) -> list[str]:
        """Split text into chunks (public interface)."""
        return self._split_text(text, self.separators)

    def chunk_document(self, document: Document) -> list[Chunk]:
        """Split document into chunks."""
        text = document.content
        if not text.strip():
            return []

        texts = self._split_text(text, self.separators)
        chunks = []

        for i, text_chunk in enumerate(texts):
            chunk = Chunk.create(
                doc_id=document.doc_id,
                text=text_chunk,
                index=i,
                metadata={
                    "filename": document.filename,
                    "file_type": document.file_type,
                    **document.metadata,
                },
            )
            chunks.append(chunk)

        return chunks

    def _split_text(self, text: str, separators: list[str]) -> list[str]:
        """Recursively split text using separators."""
        if not separators:
            return [text[i : i + self.chunk_size] for i in range(0, len(text), self.chunk_size - self.chunk_overlap)]

        sep = separators[0]
        remaining_seps = separators[1:]

        if sep:
            parts = text.split(sep)
        else:
            parts = list(text)

        chunks = []
        current_chunk = ""

        for part in parts:
            test_chunk = current_chunk + (sep if current_chunk else "") + part

            if len(test_chunk) <= self.chunk_size:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                if len(part) > self.chunk_size:
                    sub_chunks = self._split_text(part, remaining_seps)
                    chunks.extend(sub_chunks)
                    current_chunk = ""
                else:
                    current_chunk = part

        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        # Add overlap by merging small chunks
        merged = self._merge_small_chunks(chunks)
        return merged

    def _merge_small_chunks(self, chunks: list[str]) -> list[str]:
        """Merge chunks that are too small."""
        if not chunks:
            return []

        min_size = self.chunk_size // 4
        merged = []
        current = ""

        for chunk in chunks:
            if len(chunk) < min_size and current:
                current = current + " " + chunk
            elif len(current) + len(chunk) < self.chunk_size:
                current = (current + " " + chunk).strip() if current else chunk
            else:
                if current:
                    merged.append(current)
                current = chunk

        if current:
            merged.append(current)

        return merged


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> list[str]:
    """Simple function interface for chunking text."""
    chunker = RecursiveChunker(chunk_size=chunk_size, chunk_overlap=overlap)
    doc = Document.create(filename="temp", file_type="txt", content=text)
    chunks = chunker.chunk_document(doc)
    return [c.text for c in chunks]


def chunk_document(
    document: Document,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> list[Chunk]:
    """Convenience function to chunk a document."""
    chunker = RecursiveChunker(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return chunker.chunk_document(document)
