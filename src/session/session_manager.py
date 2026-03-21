"""
Session Manager — Valkey-backed short-term conversation sessions.

Stores active conversation context: user identity, facility scope, and
recent turns. Falls back to in-memory dict when Valkey is unavailable.

Session lifecycle:
  1. Created on first request (or resumed from existing session_id)
  2. Updated after each turn (question + response appended)
  3. Expires after SESSION_TTL_SECONDS of inactivity
"""

from __future__ import annotations

import json
import time
from typing import Any

from src.shared.config import SESSION_TTL_SECONDS, VALKEY_DB, VALKEY_HOST, VALKEY_PORT
from src.shared.logger import get_logger

# Re-export models from the new location for backward compatibility
from src.session.models import (
    ConversationTurn,
    Session,
    ScopeContext,
    create_session,
)

logger = get_logger(__name__)


class SessionStore:
    """Abstract session storage interface."""

    def get(self, session_id: str) -> Session | None:
        raise NotImplementedError

    def save(self, session: Session) -> None:
        raise NotImplementedError

    def delete(self, session_id: str) -> None:
        raise NotImplementedError


class ValkeySessionStore(SessionStore):

    def __init__(self) -> None:
        import redis
        self._client = redis.Redis(
            host=VALKEY_HOST,
            port=VALKEY_PORT,
            db=VALKEY_DB,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        logger.info("Valkey session store connected: %s:%d", VALKEY_HOST, VALKEY_PORT)

    def get(self, session_id: str) -> Session | None:
        key = f"session:{session_id}"
        logger.debug("ValkeySessionStore.get: %s", session_id[:12])
        data = self._client.get(key)
        if not data:
            logger.debug("Session not found: %s", session_id[:12])
            return None
        logger.debug("Session loaded: %s", session_id[:12])
        return Session.from_dict(json.loads(data))

    def save(self, session: Session) -> None:
        key = f"session:{session.session_id}"
        logger.debug(
            "ValkeySessionStore.save: %s (scope=%s, turns=%d)",
            session.session_id[:12],
            session.active_scope,
            len(session.turns),
        )
        self._client.setex(key, SESSION_TTL_SECONDS, json.dumps(session.to_dict()))

    def delete(self, session_id: str) -> None:
        key = f"session:{session_id}"
        logger.debug("ValkeySessionStore.delete: %s", session_id[:12])
        self._client.delete(key)


class InMemorySessionStore(SessionStore):

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}
        logger.info("Using in-memory session store (dev mode)")

    def get(self, session_id: str) -> Session | None:
        logger.debug("InMemorySessionStore.get: %s", session_id[:12])
        data = self._store.get(session_id)
        if not data:
            logger.debug("Session not found: %s", session_id[:12])
            return None
        if time.time() - data.get("last_active", 0) > SESSION_TTL_SECONDS:
            logger.debug("Session expired: %s", session_id[:12])
            self.delete(session_id)
            return None
        logger.debug("Session loaded: %s (scope=%s)", session_id[:12], data.get("active_scope"))
        return Session.from_dict(data)

    def save(self, session: Session) -> None:
        logger.debug(
            "InMemorySessionStore.save: %s (scope=%s, turns=%d)",
            session.session_id[:12],
            session.active_scope,
            len(session.turns),
        )
        self._store[session.session_id] = session.to_dict()

    def delete(self, session_id: str) -> None:
        logger.debug("InMemorySessionStore.delete: %s", session_id[:12])
        self._store.pop(session_id, None)


def create_session_store() -> SessionStore:
    try:
        store = ValkeySessionStore()
        store._client.ping()
        return store
    except Exception as e:
        logger.warning("Valkey unavailable (%s), falling back to in-memory", str(e))
        return InMemorySessionStore()


__all__ = [
    "Session",
    "ConversationTurn",
    "ScopeContext",
    "SessionStore",
    "ValkeySessionStore",
    "InMemorySessionStore",
    "create_session",
    "create_session_store",
]
