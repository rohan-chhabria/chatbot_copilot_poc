"""
Conversation Store — DynamoDB-backed long-term conversation history.

Persists every conversation turn for audit trail and user behavior analytics.
Falls back to no-op storage when DynamoDB is unavailable (dev/testing).

DynamoDB schema:
  - Partition key: customer_key#user_id
  - Sort key: session_id#timestamp
"""

from __future__ import annotations

import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.session.session_manager import ConversationTurn, Session
from src.shared.config import CONVERSATION_TABLE
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
            "timestamp": int(turn.timestamp),
            "ttl": int(time.time()) + (90 * 24 * 3600),
        }

        try:
            self._table.put_item(Item=item)
        except ClientError as e:
            logger.error("Failed to save conversation turn: %s", str(e))

    def get_history(
        self,
        customer_key: str,
        user_id: str,
        limit: int = 50,
    ) -> list[dict]:
        pk = f"{customer_key}#{user_id}"

        try:
            response = self._table.query(
                KeyConditionExpression="pk = :pk",
                ExpressionAttributeValues={":pk": pk},
                ScanIndexForward=False,
                Limit=limit,
            )
            return response.get("Items", [])
        except ClientError as e:
            logger.error("Failed to fetch history: %s", str(e))
            return []

    def get_session_turns(self, session_id: str) -> list[dict]:
        try:
            response = self._table.scan(
                FilterExpression="session_id = :sid",
                ExpressionAttributeValues={":sid": session_id},
            )
            items = response.get("Items", [])
            return sorted(items, key=lambda x: x.get("timestamp", 0))
        except ClientError as e:
            logger.error("Failed to fetch session turns: %s", str(e))
            return []


class NoOpConversationStore(ConversationStore):

    def __init__(self) -> None:
        logger.info("Using no-op conversation store (DynamoDB disabled)")

    def save_turn(self, session: Session, turn: ConversationTurn) -> None:
        pass

    def get_history(self, customer_key: str, user_id: str, limit: int = 50) -> list[dict]:
        return []

    def get_session_turns(self, session_id: str) -> list[dict]:
        return []


def create_conversation_store() -> ConversationStore:
    """Factory: connect to real DynamoDB, fall back to no-op if unavailable."""
    try:
        store = DynamoConversationStore()
        store._table.table_status
        return store
    except Exception as e:
        logger.warning("DynamoDB unavailable (%s), using no-op store", str(e))
        return NoOpConversationStore()
