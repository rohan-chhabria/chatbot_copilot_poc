"""
Response synthesizer for Document QA.

Uses LLM to generate answers from retrieved chunks.
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from openai import AsyncOpenAI

from src.shared.config import LLM_TEMPERATURE, OPENAI_API_KEY, OPENAI_MODEL
from src.shared.logger import get_logger

logger = get_logger(__name__)

SYNTHESIS_SYSTEM_PROMPT = """You are a helpful assistant that answers questions based on provided document excerpts.

RULES:
1. Answer ONLY using information from the provided excerpts.
2. If the excerpts don't contain enough information, say so clearly.
3. Cite which document each piece of information comes from.
4. Be concise and direct - correctional officers need quick, actionable answers.
5. If the question is about policies or procedures, emphasize key requirements.
6. Format answers for easy scanning: use bullet points for multiple items.

NEVER make up information not present in the excerpts."""


class ResponseSynthesizer:
    """
    Synthesizes answers from retrieved document chunks using LLM.
    """

    def __init__(self):
        self._openai = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self._model = OPENAI_MODEL

    async def synthesize(
        self,
        question: str,
        chunks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate an answer from retrieved chunks."""
        logger.debug(
            "Synthesizing answer: question=%r, num_chunks=%d",
            question[:100],
            len(chunks),
        )

        context = self._build_context(chunks)
        logger.debug("Built context: %d chars", len(context))

        # Log chunks being sent to LLM
        for i, chunk in enumerate(chunks):
            logger.debug(
                "  Chunk[%d]: file=%s, text=%r",
                i,
                chunk.get("metadata", {}).get("filename", "?"),
                chunk.get("text", "")[:100],
            )

        messages = [
            {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"QUESTION: {question}\n\nDOCUMENT EXCERPTS:\n{context}\n\nAnswer the question based on the excerpts above.",
            },
        ]

        logger.debug("Calling LLM: model=%s, temp=%.2f", self._model, LLM_TEMPERATURE)

        response = await self._openai.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=LLM_TEMPERATURE,
            max_tokens=1024,
        )

        answer = response.choices[0].message.content or ""
        logger.debug("LLM response: %d chars", len(answer))

        # Extract sources
        sources = self._extract_sources(chunks)

        return {
            "answer": answer,
            "sources": sources,
        }

    async def synthesize_stream(
        self,
        question: str,
        chunks: list[dict[str, Any]],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream answer generation."""
        logger.debug(
            "Synthesizing (stream): question=%r, num_chunks=%d",
            question[:100],
            len(chunks),
        )

        context = self._build_context(chunks)
        logger.debug("Built context: %d chars", len(context))

        # Log chunks being sent to LLM
        for i, chunk in enumerate(chunks):
            logger.debug(
                "  Chunk[%d]: file=%s, text=%r",
                i,
                chunk.get("metadata", {}).get("filename", "?"),
                chunk.get("text", "")[:100],
            )

        messages = [
            {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"QUESTION: {question}\n\nDOCUMENT EXCERPTS:\n{context}\n\nAnswer the question based on the excerpts above.",
            },
        ]

        yield {"event": "status", "data": "Generating answer..."}

        logger.debug("Calling LLM stream: model=%s", self._model)

        stream = await self._openai.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=LLM_TEMPERATURE,
            max_tokens=1024,
            stream=True,
        )

        full_answer = ""
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                full_answer += token
                yield {"event": "token", "data": token}

        logger.debug("LLM stream complete: %d chars", len(full_answer))

        sources = self._extract_sources(chunks)

        yield {
            "event": "result",
            "data": {
                "summary": full_answer,
                "sources": sources,
                "chunks_used": len(chunks),
            },
        }

    def _build_context(self, chunks: list[dict[str, Any]]) -> str:
        """Build context string from chunks."""
        parts = []
        for i, chunk in enumerate(chunks, 1):
            filename = chunk.get("metadata", {}).get("filename", "Unknown")
            text = chunk.get("text", "")
            parts.append(f"[{i}] From: {filename}\n{text}")
        return "\n\n---\n\n".join(parts)

    def _extract_sources(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Extract unique sources from chunks."""
        seen = set()
        sources = []

        for chunk in chunks:
            filename = chunk.get("metadata", {}).get("filename", "Unknown")
            if filename not in seen:
                seen.add(filename)
                sources.append(
                    {
                        "filename": filename,
                        "doc_id": chunk.get("metadata", {}).get("doc_id"),
                        "relevance": chunk.get("score", chunk.get("rrf_score", 0)),
                    }
                )

        return sources
