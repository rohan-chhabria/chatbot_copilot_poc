"""Test configuration for inmate_data pipeline tests."""

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("ENABLE_GUARDRAILS", "true")
os.environ.setdefault("LOG_LEVEL", "DEBUG")

import pytest

from src.session.models import ConversationTurn, Session, create_session


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
