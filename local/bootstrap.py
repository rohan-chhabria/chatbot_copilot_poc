"""
Local Bootstrap — Wires moto DynamoDB + in-memory session store for local dev.

Production code in src/ uses abstract factories (create_session_store,
create_conversation_store) which auto-detect available backends. This module
pre-configures the local environment so those factories resolve correctly.

Usage:
    from local.bootstrap import bootstrap_local
    stores = bootstrap_local()
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("USE_LOCAL_DYNAMO", "true")

import boto3
from moto import mock_aws

from src.memory.conversation_store import ConversationStore, DynamoConversationStore
from src.session.session_manager import InMemorySessionStore, SessionStore
from src.shared.config import CONVERSATION_TABLE
from src.shared.logger import get_logger

logger = get_logger(__name__)

_mock_ctx = None

LOCAL_DIR = Path(__file__).resolve().parent
USERS_PATH = LOCAL_DIR / "users.json"


@dataclass
class LocalStores:
    session_store: SessionStore
    conversation_store: ConversationStore


def bootstrap_local() -> LocalStores:
    """Set up moto DynamoDB + in-memory session store for local dev."""
    global _mock_ctx

    _mock_ctx = mock_aws()
    _mock_ctx.start()

    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    dynamodb.create_table(
        TableName=CONVERSATION_TABLE,
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    logger.info("Local moto DynamoDB table '%s' created", CONVERSATION_TABLE)

    conversation_store = DynamoConversationStore()
    session_store = InMemorySessionStore()

    logger.info("Local bootstrap complete: InMemory sessions + Moto DynamoDB")
    return LocalStores(
        session_store=session_store,
        conversation_store=conversation_store,
    )


def load_local_users() -> dict[str, Any]:
    if not USERS_PATH.exists():
        return {"users": []}
    return json.loads(USERS_PATH.read_text())


def shutdown_local() -> None:
    global _mock_ctx
    if _mock_ctx:
        _mock_ctx.stop()
        _mock_ctx = None
        logger.info("Local moto context stopped")
