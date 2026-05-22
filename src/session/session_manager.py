"""
Session Manager — short-term conversation session storage.

Runtime policy:
  - prod/staging: valkey
  - local/dev: redis
No silent runtime fallback is allowed.
"""

from __future__ import annotations

import json
import time
from typing import Any

# Re-export models from the new location for backward compatibility
from src.session.models import (
    ConversationTurn,
    ScopeContext,
    Session,
    create_session,
)
from src.shared.config import (
    IS_PRODUCTION_ENV,
    LOCAL_SESSION_BACKEND,
    PROD_SESSION_BACKEND,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PORT,
    SESSION_BACKEND,
    SESSION_TTL_SECONDS,
    VALKEY_DB,
    VALKEY_HOST,
    VALKEY_PORT,
)
from src.shared.logger import get_logger

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
        self._store = RedisSessionStore(
            host=VALKEY_HOST,
            port=VALKEY_PORT,
            db=VALKEY_DB,
            backend_label="valkey",
        )

    @property
    def _client(self):
        return self._store._client

    def get(self, session_id: str) -> Session | None:
        return self._store.get(session_id)

    def save(self, session: Session) -> None:
        self._store.save(session)

    def delete(self, session_id: str) -> None:
        self._store.delete(session_id)


class RedisSessionStore(SessionStore):

    def __init__(
        self,
        host: str,
        port: int,
        db: int,
        backend_label: str = "redis",
    ) -> None:
        import redis

        self._backend_label = backend_label
        self._client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        logger.info(
            "%s session store connected: %s:%d/%d",
            self._backend_label,
            host,
            port,
            db,
        )

    def get(self, session_id: str) -> Session | None:
        key = f"session:{session_id}"
        logger.debug("%s.get: %s", self._backend_label, session_id[:12])
        data = self._client.get(key)
        if not data:
            logger.debug("Session not found: %s", session_id[:12])
            return None
        logger.debug("Session loaded: %s", session_id[:12])
        return Session.from_dict(json.loads(data))

    def save(self, session: Session) -> None:
        key = f"session:{session.session_id}"
        logger.debug(
            "%s.save: %s (scope=%s, turns=%d)",
            self._backend_label,
            session.session_id[:12],
            session.active_scope,
            len(session.turns),
        )
        self._client.setex(key, SESSION_TTL_SECONDS, json.dumps(session.to_dict()))

    def delete(self, session_id: str) -> None:
        key = f"session:{session_id}"
        logger.debug("%s.delete: %s", self._backend_label, session_id[:12])
        self._client.delete(key)


class InMemorySessionStore(SessionStore):
    """Test-only in-memory session backend."""

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


def _resolve_session_backend() -> str:
    if SESSION_BACKEND != "auto":
        return SESSION_BACKEND
    return PROD_SESSION_BACKEND if IS_PRODUCTION_ENV else LOCAL_SESSION_BACKEND


def _build_redis_store(host: str, port: int, db: int, label: str) -> SessionStore:
    store = RedisSessionStore(host=host, port=port, db=db, backend_label=label)
    store._client.ping()
    return store


def create_session_store() -> SessionStore:
    backend = _resolve_session_backend()
    try:
        if backend == "valkey":
            return _build_redis_store(VALKEY_HOST, VALKEY_PORT, VALKEY_DB, "valkey")
        if backend == "redis":
            return _build_redis_store(REDIS_HOST, REDIS_PORT, REDIS_DB, "redis")
        if backend == "memory":
            logger.warning("Using in-memory session backend (test-only mode)")
            return InMemorySessionStore()
        raise ValueError(f"Unsupported SESSION_BACKEND: {backend}")
    except Exception as e:
        raise RuntimeError(f"Session backend '{backend}' is unavailable: {e}") from e


__all__ = [
    "Session",
    "ConversationTurn",
    "ScopeContext",
    "SessionStore",
    "RedisSessionStore",
    "ValkeySessionStore",
    "create_session",
    "create_session_store",
]
