"""
Trainer — Manages ChromaDB training data for the Vanna 2.0 agent.

All Vanna 2.0 ChromaAgentMemory methods are async. This module provides
both async and sync wrappers for training.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from src.shared.config import TRAINING_DOCUMENTATION_PATH, TRAINING_EXAMPLES_PATH
from src.shared.logger import get_logger

logger = get_logger(__name__)


def _get_memory():
    from src.pipelines.inmate_data.vanna_agent import get_agent_memory
    return get_agent_memory()


def _make_context():
    from src.pipelines.inmate_data.vanna_agent import _make_tool_context
    return _make_tool_context(user_id="trainer")


async def _train_examples_async(path: str) -> int:
    if not os.path.exists(path):
        logger.warning("Training examples file not found: %s", path)
        return 0

    memory = _get_memory()
    if memory is None:
        logger.warning("No agent memory available for training")
        return 0

    ctx = _make_context()
    with open(path) as f:
        examples = json.load(f)

    count = 0
    for item in examples:
        question = item.get("question", "")
        sql = item.get("sql", "")
        if question and sql:
            try:
                text = f"Question: {question}\nSQL: {sql}"
                await memory.save_text_memory(content=text, context=ctx)
                count += 1
            except Exception as e:
                logger.error("Failed to train example: %s — %s", question[:50], str(e))

    logger.info("Trained %d question-SQL pairs from %s", count, path)
    return count


async def _train_documentation_async(path: str) -> int:
    if not os.path.exists(path):
        logger.warning("Training documentation file not found: %s", path)
        return 0

    memory = _get_memory()
    if memory is None:
        logger.warning("No agent memory available for training")
        return 0

    ctx = _make_context()
    with open(path) as f:
        docs = json.load(f)

    count = 0
    for item in docs:
        doc = item.get("documentation", "") or item.get("content", "")
        if doc:
            try:
                await memory.save_text_memory(content=doc, context=ctx)
                count += 1
            except Exception as e:
                logger.error("Failed to train doc: %s — %s", doc[:50], str(e))

    logger.info("Trained %d documentation entries from %s", count, path)
    return count


async def _train_ddl_async(ddl_statements: list[str]) -> int:
    memory = _get_memory()
    if memory is None:
        logger.warning("No agent memory available for training")
        return 0

    ctx = _make_context()
    count = 0
    for ddl in ddl_statements:
        if ddl.strip():
            try:
                await memory.save_text_memory(content=ddl, context=ctx)
                count += 1
            except Exception as e:
                logger.error("Failed to train DDL: %s — %s", ddl[:50], str(e))

    logger.info("Trained %d DDL statements", count)
    return count


async def _get_training_stats_async() -> dict[str, Any]:
    memory = _get_memory()
    if memory is None:
        return {"total_entries": 0, "status": "no_memory"}
    try:
        ctx = _make_context()
        recent = await memory.get_recent_text_memories(ctx, limit=1000)
        return {"total_entries": len(recent) if recent else 0, "status": "active"}
    except Exception as e:
        logger.error("Failed to get training stats: %s", str(e))
        return {"total_entries": 0, "status": "error", "error": str(e)}


async def train_from_defaults_async() -> dict[str, int]:
    examples = await _train_examples_async(TRAINING_EXAMPLES_PATH)
    docs = await _train_documentation_async(TRAINING_DOCUMENTATION_PATH)
    return {"examples": examples, "documentation": docs}


def train_from_defaults() -> dict[str, int]:
    """Sync wrapper — safe to call from scripts or non-async contexts."""
    return asyncio.run(train_from_defaults_async())


def train_examples(path: str) -> int:
    return asyncio.run(_train_examples_async(path))


def train_documentation(path: str) -> int:
    return asyncio.run(_train_documentation_async(path))


def train_ddl(ddl_statements: list[str]) -> int:
    return asyncio.run(_train_ddl_async(ddl_statements))


def get_training_stats() -> dict[str, Any]:
    return asyncio.run(_get_training_stats_async())
