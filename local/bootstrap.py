"""
Local Bootstrap — Wires runtime local backends for local dev.

Uses the same production factories with local defaults:
  - STM: redis
  - LTM: sqlite
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("SESSION_BACKEND", "redis")
os.environ.setdefault("LTM_BACKEND", "sqlite")
os.environ.setdefault("LOCAL_SESSION_BACKEND", "redis")
os.environ.setdefault("LOCAL_LTM_BACKEND", "sqlite")

from src.memory.conversation_store import ConversationStore, create_conversation_store
from src.session.session_manager import SessionStore, create_session_store
from src.shared.config import REDIS_HOST, REDIS_PORT
from src.shared.logger import get_logger

logger = get_logger(__name__)

LOCAL_DIR = Path(__file__).resolve().parent
USERS_PATH = LOCAL_DIR / "users.json"


@dataclass
class LocalStores:
    session_store: SessionStore
    conversation_store: ConversationStore


def bootstrap_local() -> LocalStores:
    """Set up local runtime stores via shared factories."""
    conversation_store = create_conversation_store()
    _assert_local_redis_reachable()
    session_store = create_session_store()

    logger.info("Local bootstrap complete")
    return LocalStores(
        session_store=session_store,
        conversation_store=conversation_store,
    )


def load_local_users() -> dict[str, Any]:
    if not USERS_PATH.exists():
        return {"users": []}
    return json.loads(USERS_PATH.read_text())


def shutdown_local() -> None:
    logger.info("Local shutdown complete")


def _assert_local_redis_reachable() -> None:
    backend = os.environ.get("SESSION_BACKEND", "redis").lower()
    local_backend = os.environ.get("LOCAL_SESSION_BACKEND", "redis").lower()
    if backend not in {"redis", "auto"}:
        return
    if backend == "auto" and local_backend != "redis":
        return

    host = os.environ.get("REDIS_HOST", REDIS_HOST)
    port = int(os.environ.get("REDIS_PORT", str(REDIS_PORT)))

    try:
        with socket.create_connection((host, port), timeout=1.0):
            return
    except OSError as exc:
        raise RuntimeError(
            "Local STM backend 'redis' is configured but unreachable at "
            f"{host}:{port}. Start Redis before running local.server.\n"
            "Example commands:\n"
            "  redis-server\n"
            "or\n"
            "  docker run --name copilot-redis -p 6379:6379 -d redis:7"
        ) from exc
