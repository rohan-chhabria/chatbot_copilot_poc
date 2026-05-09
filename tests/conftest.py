"""
Test Configuration — Shared fixtures for unit and integration tests.

Sets up mock AWS services (DynamoDB via moto), fake Redis, and test sessions.
"""

from __future__ import annotations

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("CONVERSATION_TABLE", "InmateCopilot-Conversations-test")
os.environ.setdefault("VALKEY_HOST", "localhost")
os.environ.setdefault("ENABLE_GUARDRAILS", "true")
os.environ.setdefault("LOG_LEVEL", "DEBUG")
os.environ.setdefault("SESSION_BACKEND", "memory")
os.environ.setdefault("LTM_BACKEND", "noop")

import boto3
import pytest
from moto import mock_aws

from src.session.session_manager import (
    ConversationTurn,
    InMemorySessionStore,
    Session,
    create_session,
)
from src.tenant.tenant_router import TenantContext


@pytest.fixture
def tenant_context() -> TenantContext:
    return TenantContext(
        customer_key="demo",
        db_host="localhost",
        db_name="test_db",
        db_user="test_user",
        db_password="test_pass",
        db_port=3306,
    )


@pytest.fixture
def session() -> Session:
    return create_session(
        customer_key="demo",
        user_id="Test.Officer",
        facility_ids=[101, 102, 103],
        role="officer",
    )


@pytest.fixture
def session_with_history(session: Session) -> Session:
    session.add_turn(ConversationTurn(
        role="user",
        content="How many inmates are on Fire Watch?",
    ))
    session.add_turn(ConversationTurn(
        role="assistant",
        content="There are 45 inmates on Fire Watch across 3 facilities.",
        sql="SELECT COUNT(*) FROM dg_notes_by_keyword WHERE keyword_name = 'Fire Watch'",
        row_count=1,
    ))
    return session


@pytest.fixture
def memory_session_store() -> InMemorySessionStore:
    return InMemorySessionStore()


@pytest.fixture
def dynamodb_table():
    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName="InmateCopilot-Conversations-test",
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield client
