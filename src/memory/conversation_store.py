"""
Conversation Store — long-term conversation history backends.

Runtime policy:
  - prod/staging: dynamodb
  - local/dev: sqlite
No silent runtime fallback is allowed.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import boto3

from src.session.session_manager import ConversationTurn, Session
from src.shared.config import (
    CONVERSATION_TABLE,
    IS_PRODUCTION_ENV,
    LOCAL_LTM_BACKEND,
    LOCAL_LTM_SQLITE_PATH,
    LTM_BACKEND,
    PROD_LTM_BACKEND,
)
from src.shared.logger import get_logger

logger = get_logger(__name__)


class ConversationStore:
    """Abstract conversation persistence interface."""

    def save_turn(self, session: Session, turn: ConversationTurn) -> None:
        raise NotImplementedError

    def get_history(self, customer_key: str, user_id: str, limit: int = 50) -> list[dict]:
        raise NotImplementedError

    def get_session_turns(self, session_id: str) -> list[dict]:
        raise NotImplementedError

    def get_user_turns(
        self,
        customer_key: str,
        user_id: str,
        limit: int = 50,
        scope: str | None = None,
    ) -> list[dict]:
        raise NotImplementedError


class DynamoConversationStore(ConversationStore):

    def __init__(self) -> None:
        self._table_name = CONVERSATION_TABLE
        self._dynamodb = boto3.resource("dynamodb")
        self._table = self._dynamodb.Table(self._table_name)
        logger.info("DynamoDB conversation store: %s", self._table_name)

    def save_turn(self, session: Session, turn: ConversationTurn) -> None:
        pk = f"{session.customer_key}#{session.user_id}"
        sk = f"{session.session_id}#{turn.timestamp}"

        item: dict[str, Any] = {
            "pk": pk,
            "sk": sk,
            "session_id": session.session_id,
            "customer_key": session.customer_key,
            "user_id": session.user_id,
            "role": turn.role,
            "content": turn.content,
            "sql": turn.sql,
            "row_count": turn.row_count,
            "scope": turn.scope,
            "metadata": turn.metadata,
            "timestamp": int(turn.timestamp),
            "ttl": int(time.time()) + (90 * 24 * 3600),
        }

        self._table.put_item(Item=item)

    def get_history(
        self,
        customer_key: str,
        user_id: str,
        limit: int = 50,
    ) -> list[dict]:
        pk = f"{customer_key}#{user_id}"

        response = self._table.query(
            KeyConditionExpression="pk = :pk",
            ExpressionAttributeValues={":pk": pk},
            ScanIndexForward=False,
            Limit=limit,
        )
        return response.get("Items", [])

    def get_session_turns(self, session_id: str) -> list[dict]:
        response = self._table.scan(
            FilterExpression="session_id = :sid",
            ExpressionAttributeValues={":sid": session_id},
        )
        items = response.get("Items", [])
        return sorted(items, key=lambda x: x.get("timestamp", 0))

    def get_user_turns(
        self,
        customer_key: str,
        user_id: str,
        limit: int = 50,
        scope: str | None = None,
    ) -> list[dict]:
        history = self.get_history(customer_key=customer_key, user_id=user_id, limit=limit * 3)
        turns = [item for item in history if item.get("role") == "user"]
        if scope is not None:
            turns = [item for item in turns if item.get("scope") == scope]
        return turns[:limit]


class SQLiteConversationStore(ConversationStore):
    def __init__(self, db_path: str = LOCAL_LTM_SQLITE_PATH) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        logger.info("SQLite conversation store: %s", self._db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_key TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    sql TEXT NOT NULL DEFAULT '',
                    row_count INTEGER NOT NULL DEFAULT 0,
                    scope TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    timestamp REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_user_ts
                ON conversation_turns (customer_key, user_id, timestamp DESC)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_session_ts
                ON conversation_turns (session_id, timestamp ASC)
                """
            )
            conn.commit()

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "session_id": row["session_id"],
            "customer_key": row["customer_key"],
            "user_id": row["user_id"],
            "role": row["role"],
            "content": row["content"],
            "sql": row["sql"],
            "row_count": row["row_count"],
            "scope": row["scope"],
            "metadata": json.loads(row["metadata_json"] or "{}"),
            "timestamp": row["timestamp"],
        }

    def save_turn(self, session: Session, turn: ConversationTurn) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO conversation_turns (
                    customer_key, user_id, session_id, role, content, sql, row_count,
                    scope, metadata_json, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.customer_key,
                    session.user_id,
                    session.session_id,
                    turn.role,
                    turn.content,
                    turn.sql,
                    turn.row_count,
                    turn.scope,
                    json.dumps(turn.metadata or {}),
                    float(turn.timestamp),
                ),
            )
            conn.commit()

    def get_history(self, customer_key: str, user_id: str, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT customer_key, user_id, session_id, role, content, sql, row_count,
                       scope, metadata_json, timestamp
                FROM conversation_turns
                WHERE customer_key = ? AND user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (customer_key, user_id, limit),
            ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def get_session_turns(self, session_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT customer_key, user_id, session_id, role, content, sql, row_count,
                       scope, metadata_json, timestamp
                FROM conversation_turns
                WHERE session_id = ?
                ORDER BY timestamp ASC
                """,
                (session_id,),
            ).fetchall()
        return [self._row_to_item(r) for r in rows]

    def get_user_turns(
        self,
        customer_key: str,
        user_id: str,
        limit: int = 50,
        scope: str | None = None,
    ) -> list[dict]:
        with self._connect() as conn:
            if scope is None:
                rows = conn.execute(
                    """
                    SELECT customer_key, user_id, session_id, role, content, sql, row_count,
                           scope, metadata_json, timestamp
                    FROM conversation_turns
                    WHERE customer_key = ? AND user_id = ? AND role = 'user'
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (customer_key, user_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT customer_key, user_id, session_id, role, content, sql, row_count,
                           scope, metadata_json, timestamp
                    FROM conversation_turns
                    WHERE customer_key = ? AND user_id = ? AND role = 'user' AND scope = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (customer_key, user_id, scope, limit),
                ).fetchall()
        return [self._row_to_item(r) for r in rows]


class NoOpConversationStore(ConversationStore):
    """Test-only no-op LTM backend."""

    def __init__(self) -> None:
        logger.info("Using no-op conversation store (DynamoDB disabled)")

    def save_turn(self, session: Session, turn: ConversationTurn) -> None:
        pass

    def get_history(self, customer_key: str, user_id: str, limit: int = 50) -> list[dict]:
        return []

    def get_session_turns(self, session_id: str) -> list[dict]:
        return []

    def get_user_turns(
        self,
        customer_key: str,
        user_id: str,
        limit: int = 50,
        scope: str | None = None,
    ) -> list[dict]:
        return []


def _resolve_ltm_backend() -> str:
    if LTM_BACKEND != "auto":
        return LTM_BACKEND
    return PROD_LTM_BACKEND if IS_PRODUCTION_ENV else LOCAL_LTM_BACKEND


def create_conversation_store() -> ConversationStore:
    """Factory: deterministic backend selection by environment policy."""
    backend = _resolve_ltm_backend()
    try:
        if backend == "dynamodb":
            store = DynamoConversationStore()
            store._table.table_status
            return store
        if backend == "sqlite":
            return SQLiteConversationStore()
        if backend == "noop":
            logger.warning("Using no-op conversation backend (test-only mode)")
            return NoOpConversationStore()
        raise ValueError(f"Unsupported LTM_BACKEND: {backend}")
    except Exception as e:
        raise RuntimeError(f"Conversation backend '{backend}' is unavailable: {e}") from e
