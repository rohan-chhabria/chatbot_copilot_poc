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


class MockConversationStore:
    def __init__(self, turns=None):
        self._turns = turns or []

    def get_user_turns(self, customer_key, user_id, limit=50, scope=None):
        _ = customer_key
        _ = user_id
        turns = self._turns
        if scope is not None:
            turns = [t for t in turns if t.get("scope") == scope]
        return turns[:limit]


@pytest.fixture(autouse=True)
def setup_registry():
    # Don't clear - just register if not already registered
    scopes = [
        ("test_scope", "Test"),
        ("daily_activity", "Daily Activity"),
        ("document_qa", "Documents"),
        ("inmate_data", "Inmate Data"),
    ]
    for scope_id, scope_label in scopes:
        if not ScopeRegistry.is_valid_scope(scope_id):
            ScopeRegistry.register(ScopeDefinition(
                id=scope_id, label=scope_label, icon="🧪",
                description=f"{scope_label} scope", category="Test",
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

    def test_greeting_with_embedded_query_not_intercepted(self, handler, session):
        session.switch_scope("test_scope")
        result = handler.handle("hello show fire watch notes today", session)
        assert result is None


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

    def test_recall_with_active_scope_defaults_to_recent_scoped_stm(self, session):
        session.switch_scope("test_scope")
        session.add_turn(ConversationTurn(role="user", content="Current scoped question", scope="test_scope"))
        store = MockConversationStore(
            turns=[
                {"content": "Earlier scoped question", "scope": "test_scope", "timestamp": 1700000000},
                {"content": "Other scope question", "scope": "document_qa", "timestamp": 1700000001},
            ]
        )
        handler = CrossScopeHandler(conversation_store=store)

        result = handler.handle("what did i ask earlier?", session)
        assert "Current scoped question" in result["summary"]
        assert "Earlier scoped question" not in result["summary"]
        assert "Other scope question" not in result["summary"]

    def test_recall_current_scope_past_includes_ltm(self, session):
        session.switch_scope("test_scope")
        session.add_turn(ConversationTurn(role="user", content="Current scoped question", scope="test_scope"))
        store = MockConversationStore(
            turns=[
                {"content": "Earlier scoped question", "scope": "test_scope", "timestamp": 1700000000},
                {"content": "Other scope question", "scope": "document_qa", "timestamp": 1700000001},
            ]
        )
        handler = CrossScopeHandler(conversation_store=store)

        result = handler.handle("what all have i asked in the past?", session)
        assert "Current scoped question" in result["summary"]
        assert "Earlier scoped question" in result["summary"]
        assert "Other scope question" not in result["summary"]

    @pytest.mark.parametrize(
        "prompt",
        [
            "what had i asked?",
            "what all i had asked?",
            "is that all i have asked?",
            "what have i asked as of this moment?",
            "what have i asked as of date?",
            "what all have i asked totally",
            "history?",
            "history of what we have discussed?",
            "what is my history?",
            "what's my history?",
            "what have i asked till date?",
        ],
    )
    def test_recall_real_world_phrase_variants(self, handler, session, prompt):
        session.add_turn(ConversationTurn(role="user", content="top 5 officers this month", scope="test_scope"))
        session.add_turn(ConversationTurn(role="assistant", content="A response", scope="test_scope"))
        session.switch_scope("test_scope")

        result = handler.handle(prompt, session)
        assert result is not None
        assert result.get("is_recall") is True
        assert "top 5 officers this month" in result["summary"]

    def test_recall_without_active_scope_uses_current_session_only(self, session):
        session.add_turn(ConversationTurn(role="user", content="Current session question"))
        store = MockConversationStore(
            turns=[{"content": "Long term question", "scope": "test_scope", "timestamp": 1700000000}]
        )
        handler = CrossScopeHandler(conversation_store=store)

        result = handler.handle("what did i ask?", session)
        assert "Current session question" in result["summary"]
        assert "Long term question" not in result["summary"]

    def test_recall_all_scopes_includes_all_ltm_scopes(self, session):
        session.switch_scope("test_scope")
        session.add_turn(ConversationTurn(role="user", content="Current scope prompt", scope="test_scope"))
        store = MockConversationStore(
            turns=[
                {"content": "Inmate scope question", "scope": "inmate_data", "timestamp": 1700000000},
                {"content": "Document scope question", "scope": "document_qa", "timestamp": 1700000001},
            ]
        )
        handler = CrossScopeHandler(conversation_store=store)

        result = handler.handle("show my conversation history across all scopes", session)
        assert "Current scope prompt" in result["summary"]
        assert "Inmate scope question" in result["summary"]
        assert "Document scope question" in result["summary"]

    def test_recall_in_general_includes_all_scopes(self, session):
        session.switch_scope("daily_activity")
        session.add_turn(ConversationTurn(role="user", content="Daily refresh", scope="daily_activity"))
        store = MockConversationStore(
            turns=[
                {"content": "Documents census count", "scope": "document_qa", "timestamp": 1700000000},
                {"content": "Top officers", "scope": "inmate_data", "timestamp": 1700000001},
            ]
        )
        handler = CrossScopeHandler(conversation_store=store)

        result = handler.handle("what have i asked in general?", session)
        assert "Daily refresh" in result["summary"]
        assert "Documents census count" in result["summary"]
        assert "Top officers" in result["summary"]


class TestSelfIdentity:
    def test_recognizes_self_identity(self, handler, session):
        result = handler.handle("who am i", session)
        assert result is not None
        assert result.get("is_self_identity") is True


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
