"""Tests for cross-scope handler."""

from __future__ import annotations

import pytest

from src.orchestrator.cross_scope import CrossScopeHandler
from src.orchestrator.scope_registry import ScopeDefinition, ScopeRegistry
from src.pipelines.base import Pipeline
from src.session.models import ConversationTurn, create_session


class MockPipeline(Pipeline):
    async def process(self, q, s, c):
        return {"summary": "Mock", "row_count": 0}
    
    async def process_stream(self, q, s, c):
        yield {"event": "result", "data": {}}
    
    async def health(self):
        return {"status": "healthy"}


@pytest.fixture(autouse=True)
def setup_registry():
    # Don't clear - just register if not already registered
    if not ScopeRegistry.is_valid_scope("test_scope"):
        ScopeRegistry.register(ScopeDefinition(
            id="test_scope", label="Test", icon="🧪",
            description="Test scope", category="Test",
            pipeline_class=MockPipeline,
        ))
    yield


@pytest.fixture
def handler():
    return CrossScopeHandler()


@pytest.fixture
def session():
    return create_session(customer_key="demo", user_id="Test.Officer")


class TestGreetings:
    def test_recognizes_hi(self, handler, session):
        result = handler.handle("hi", session)
        assert result is not None
        assert "is_greeting" in result

    def test_recognizes_hello(self, handler, session):
        result = handler.handle("hello", session)
        assert result is not None
        assert "is_greeting" in result

    def test_recognizes_good_morning(self, handler, session):
        result = handler.handle("good morning", session)
        assert result is not None
        assert "is_greeting" in result

    def test_greeting_without_scope_shows_options(self, handler, session):
        result = handler.handle("hello", session)
        assert result["requires_scope"] is True
        assert "options" in result

    def test_greeting_with_scope_mentions_scope(self, handler, session):
        session.switch_scope("test_scope")
        result = handler.handle("hello", session)
        assert "Test" in result["summary"]


class TestFarewells:
    def test_recognizes_bye(self, handler, session):
        result = handler.handle("bye", session)
        assert result is not None
        assert "is_farewell" in result

    def test_recognizes_thanks(self, handler, session):
        result = handler.handle("thanks", session)
        assert result is not None
        assert "is_farewell" in result

    def test_farewell_with_history_mentions_count(self, handler, session):
        session.add_turn(ConversationTurn(role="user", content="Q1"))
        session.add_turn(ConversationTurn(role="user", content="Q2"))
        result = handler.handle("goodbye", session)
        assert "2" in result["summary"]


class TestHelp:
    def test_recognizes_what_can_you_do(self, handler, session):
        result = handler.handle("what can you do?", session)
        assert result is not None
        assert "is_help" in result

    def test_recognizes_help(self, handler, session):
        result = handler.handle("help", session)
        assert result is not None
        assert "is_help" in result

    def test_help_lists_scopes(self, handler, session):
        result = handler.handle("what can you do", session)
        assert "Test" in result["summary"]


class TestRecall:
    def test_recognizes_what_did_i_ask(self, handler, session):
        session.add_turn(ConversationTurn(role="user", content="Test question"))
        result = handler.handle("what did i ask?", session)
        assert result is not None
        assert "is_recall" in result

    def test_recall_shows_history(self, handler, session):
        session.add_turn(ConversationTurn(role="user", content="First question"))
        session.add_turn(ConversationTurn(role="user", content="Second question"))
        result = handler.handle("what did I ask earlier?", session)
        assert "First question" in result["summary"]
        assert "Second question" in result["summary"]

    def test_recall_empty_history(self, handler, session):
        result = handler.handle("what did I ask?", session)
        assert "No questions yet" in result["summary"]


class TestNonCrossScopeMessages:
    def test_data_query_not_handled(self, handler, session):
        result = handler.handle("Show fire watch notes today", session)
        assert result is None

    def test_inmate_query_not_handled(self, handler, session):
        result = handler.handle("Where is inmate John?", session)
        assert result is None

    def test_random_text_not_handled(self, handler, session):
        result = handler.handle("Calculate the trajectory", session)
        assert result is None
