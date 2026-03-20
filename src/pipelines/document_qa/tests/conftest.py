"""Test configuration for document_qa pipeline tests."""

import os

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "DEBUG")

import pytest

from src.session.models import Session, create_session


@pytest.fixture
def session() -> Session:
    return create_session(
        customer_key="demo",
        user_id="Test.Officer",
        facility_ids=[101, 102],
        role="officer",
    )
