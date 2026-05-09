"""Tests for the scope state machine."""

from __future__ import annotations

import asyncio

import pytest

from src.orchestrator.scope_registry import ScopeDefinition, ScopeRegistry
from src.orchestrator.state_machine import ScopeStateMachine
from src.pipelines.base import Pipeline
from src.session.models import create_session
from src.shared.exceptions import ScopeError


class MockPipeline(Pipeline):
    """Mock pipeline for testing."""
    
    scope_id = "mock"
    scope_label = "Mock"
    scope_icon = "🧪"
    scope_description = "Mock pipeline"
    process_calls: list[str] = []
    stream_calls: list[str] = []
    
    async def process(self, question, session, scope_context):
        _ = session
        _ = scope_context
        self.__class__.process_calls.append(question)
        return {"summary": f"Mock response to: {question}", "row_count": 0}
    
    async def process_stream(self, question, session, scope_context):
        _ = session
        _ = scope_context
        self.__class__.stream_calls.append(question)
        yield {"event": "result", "data": {"summary": "Mock"}}
    
    async def health(self):
        return {"status": "healthy"}


class RecordingConversationStore:
    def __init__(self):
        self.saved = []

    def save_turn(self, session, turn):
        self.saved.append((session.session_id, turn.role, turn.content))


def run_async(coro):
    """Helper to run async code in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(autouse=True)
def setup_registry():
    """Register mock pipeline before each test."""
    # Don't clear - just register if not already registered
    if not ScopeRegistry.is_valid_scope("mock_scope"):
        defn = ScopeDefinition(
            id="mock_scope",
            label="Mock Scope",
            icon="🧪",
            description="A mock scope for testing",
            category="Testing",
            pipeline_class=MockPipeline,
        )
        ScopeRegistry.register(defn)
    MockPipeline.process_calls.clear()
    MockPipeline.stream_calls.clear()
    yield


@pytest.fixture
def state_machine():
    return ScopeStateMachine(conversation_store=None)


@pytest.fixture
def session():
    return create_session(customer_key="demo", user_id="Test.Officer")


class TestScopeSelection:
    def test_select_valid_scope(self, state_machine, session):
        result = state_machine.select_scope("mock_scope", session)
        
        assert result["scope"] == "mock_scope"
        assert result["is_scope_change"] is True
        assert session.active_scope == "mock_scope"
        assert "mock_scope" in session.scope_history

    def test_select_invalid_scope_raises(self, state_machine, session):
        with pytest.raises(ScopeError, match="Invalid scope"):
            state_machine.select_scope("nonexistent", session)

    def test_select_scope_returns_welcome(self, state_machine, session):
        result = state_machine.select_scope("mock_scope", session)
        
        assert "summary" in result
        assert len(result["summary"]) > 0

    def test_returning_to_scope_shows_context(self, state_machine, session):
        # First visit
        state_machine.select_scope("mock_scope", session)
        session.get_scope_context().add_query("Previous query")
        session.get_scope_context().update_entity("last_assistant_summary", "Old summary")

        # Switch away and back
        session.active_scope = None
        result = state_machine.select_scope("mock_scope", session)

        assert "Welcome back" in result["summary"]
        assert "Previous query" in result["summary"]
        assert "I last shared" not in result["summary"]


class TestScopeOptions:
    def test_get_scope_options(self, state_machine, session):
        result = state_machine.get_scope_options(session)
        
        assert "options" in result
        assert len(result["options"]) > 0
        # Check mock_scope is in the options (could be any position)
        scope_ids = [o["id"] for o in result["options"]]
        assert "mock_scope" in scope_ids

    def test_options_mark_current_scope(self, state_machine, session):
        session.switch_scope("mock_scope")
        result = state_machine.get_scope_options(session)
        
        mock_opt = next(o for o in result["options"] if o["id"] == "mock_scope")
        assert mock_opt["is_current"] is True

    def test_options_mark_visited_scopes(self, state_machine, session):
        session.switch_scope("mock_scope")
        session.active_scope = None  # Clear active but keep visited
        
        result = state_machine.get_scope_options(session)
        
        mock_opt = next(o for o in result["options"] if o["id"] == "mock_scope")
        assert mock_opt["is_visited"] is True
        assert mock_opt["is_current"] is False


class TestMessageHandling:
    def test_no_scope_prompts_selection(self, state_machine, session):
        result = run_async(state_machine.handle_message("Hello", session))
        
        # Should either prompt for scope or handle greeting
        assert "summary" in result or "options" in result

    def test_greeting_handled_cross_scope(self, state_machine, session):
        result = run_async(state_machine.handle_message("Hello", session))
        
        assert "is_greeting" in result or "requires_scope" in result

    def test_help_handled_cross_scope(self, state_machine, session):
        result = run_async(state_machine.handle_message("What can you do?", session))
        
        assert "is_help" in result or "summary" in result

    def test_message_dispatched_to_pipeline(self, state_machine, session):
        session.switch_scope("mock_scope")
        
        result = run_async(state_machine.handle_message("Test question", session))
        
        assert "Mock response to: Test question" in result["summary"]
        assert result["scope"] == "mock_scope"

    def test_cross_scope_turns_are_persisted(self, session):
        store = RecordingConversationStore()
        machine = ScopeStateMachine(conversation_store=store)

        _ = run_async(machine.handle_message("hello", session))

        assert len(store.saved) == 2
        assert store.saved[0][1] == "user"
        assert store.saved[1][1] == "assistant"

    def test_pipeline_turns_are_persisted(self, session):
        store = RecordingConversationStore()
        machine = ScopeStateMachine(conversation_store=store)
        session.switch_scope("mock_scope")

        _ = run_async(machine.handle_message("check inmates", session))

        assert len(store.saved) == 2
        assert store.saved[0][2] == "check inmates"

    def test_continue_reuses_last_scoped_question(self, state_machine, session):
        session.switch_scope("mock_scope")
        _ = run_async(state_machine.handle_message("Where is inmate John?", session))

        result = run_async(state_machine.handle_message("continue", session))
        assert "Mock response to: Where is inmate John?" in result["summary"]
        assert session.turns[-2].content == "continue"

    def test_continue_on_that_reuses_last_scoped_question(self, state_machine, session):
        session.switch_scope("mock_scope")
        _ = run_async(state_machine.handle_message("tell me top 5 officers", session))

        result = run_async(state_machine.handle_message("continue on that", session))
        assert "Mock response to: tell me top 5 officers" in result["summary"]
        assert session.turns[-2].content == "continue on that"
        assert MockPipeline.process_calls[-1] == "tell me top 5 officers"

    def test_continue_without_scoped_history_returns_hint(self, state_machine, session):
        session.switch_scope("mock_scope")
        result = run_async(state_machine.handle_message("continue", session))
        assert "don't have a recent question in this scope yet" in result["summary"]

    def test_revisit_reuses_indexed_question(self, state_machine, session):
        session.switch_scope("mock_scope")
        _ = run_async(state_machine.handle_message("top 5 officers today?", session))
        _ = run_async(state_machine.handle_message("in last 7 days", session))
        _ = run_async(state_machine.handle_message("what have i asked?", session))

        result = run_async(state_machine.handle_message("revisit 1", session))
        assert "Mock response to: top 5 officers today?" in result["summary"]
        assert session.turns[-2].content == "revisit 1"
        assert MockPipeline.process_calls[-1] == "top 5 officers today?"

    def test_revisit_question_from_list_reuses_indexed_question(self, state_machine, session):
        session.switch_scope("mock_scope")
        _ = run_async(state_machine.handle_message("top 5 officers today?", session))
        _ = run_async(state_machine.handle_message("in last 7 days", session))
        _ = run_async(state_machine.handle_message("what have i asked till date?", session))

        result = run_async(state_machine.handle_message("revisit question 2 from list", session))
        assert "Mock response to: in last 7 days" in result["summary"]
        assert MockPipeline.process_calls[-1] == "in last 7 days"

    def test_revisit_invalid_index_returns_guidance_without_pipeline_fallback(self, state_machine, session):
        session.switch_scope("mock_scope")
        _ = run_async(state_machine.handle_message("top 5 officers today?", session))
        _ = run_async(state_machine.handle_message("what have i asked?", session))
        before_calls = len(MockPipeline.process_calls)

        result = run_async(state_machine.handle_message("revisit 9", session))
        assert "couldn't find item 9" in result["summary"]
        assert len(MockPipeline.process_calls) == before_calls

    def test_revisit_stale_map_after_new_query_returns_guidance(self, state_machine, session):
        session.switch_scope("mock_scope")
        _ = run_async(state_machine.handle_message("top 5 officers today?", session))
        _ = run_async(state_machine.handle_message("what have i asked?", session))
        _ = run_async(state_machine.handle_message("new query after recall", session))
        before_calls = len(MockPipeline.process_calls)

        result = run_async(state_machine.handle_message("revisit 1", session))
        assert "Ask 'what have i asked?' first" in result["summary"]
        assert len(MockPipeline.process_calls) == before_calls


class TestStreamDispatch:
    def test_stream_requires_scope(self, state_machine, session):
        async def collect_events():
            events = []
            async for event in state_machine.dispatch_stream("Test", session):
                events.append(event)
            return events
        
        events = run_async(collect_events())
        assert any(e.get("event") == "error" for e in events)

    def test_stream_with_scope(self, state_machine, session):
        session.switch_scope("mock_scope")
        
        async def collect_events():
            events = []
            async for event in state_machine.dispatch_stream("Test", session):
                events.append(event)
            return events
        
        events = run_async(collect_events())
        assert len(events) > 0

    def test_stream_greeting_handled_cross_scope(self, state_machine, session):
        session.switch_scope("mock_scope")

        async def collect_events():
            events = []
            async for event in state_machine.dispatch_stream("hello", session):
                events.append(event)
            return events

        events = run_async(collect_events())
        assert len(events) == 1
        assert events[0]["event"] == "result"
        assert events[0]["data"].get("is_greeting") is True

    def test_stream_continue_reuses_last_scoped_question(self, state_machine, session):
        session.switch_scope("mock_scope")
        run_async(state_machine.handle_message("Show inmates on fire watch", session))

        async def collect_events():
            events = []
            async for event in state_machine.dispatch_stream("continue", session):
                events.append(event)
            return events

        events = run_async(collect_events())
        assert events[-1]["event"] == "result"
        assert "Mock" in events[-1]["data"]["summary"]

    def test_stream_continue_on_that_reuses_last_scoped_question(self, state_machine, session):
        session.switch_scope("mock_scope")
        run_async(state_machine.handle_message("top 5 officers this month", session))

        async def collect_events():
            events = []
            async for event in state_machine.dispatch_stream("continue on that", session):
                events.append(event)
            return events

        events = run_async(collect_events())
        assert events[-1]["event"] == "result"
        assert "Mock" in events[-1]["data"]["summary"]
        assert MockPipeline.stream_calls[-1] == "top 5 officers this month"

    def test_stream_revisit_reuses_indexed_question(self, state_machine, session):
        session.switch_scope("mock_scope")
        run_async(state_machine.handle_message("census count", session))
        run_async(state_machine.handle_message("chow call", session))
        run_async(state_machine.handle_message("what is my history?", session))

        async def collect_events():
            events = []
            async for event in state_machine.dispatch_stream("revisit 2", session):
                events.append(event)
            return events

        events = run_async(collect_events())
        assert events[-1]["event"] == "result"
        assert MockPipeline.stream_calls[-1] == "chow call"

    @pytest.mark.parametrize("scope_id", ["daily_activity", "document_qa", "inmate_data"])
    def test_recall_phrase_matrix_non_stream(self, state_machine, session, scope_id):
        if not ScopeRegistry.is_valid_scope(scope_id):
            ScopeRegistry.register(ScopeDefinition(
                id=scope_id,
                label=scope_id.replace("_", " ").title(),
                icon="🧪",
                description=f"{scope_id} scope",
                category="Testing",
                pipeline_class=MockPipeline,
            ))
        session.switch_scope(scope_id)
        _ = run_async(state_machine.handle_message("seed question", session))

        result = run_async(state_machine.handle_message("what is my history?", session))
        assert result.get("is_recall") is True
        assert "seed question" in result["summary"]

    @pytest.mark.parametrize("scope_id", ["daily_activity", "document_qa", "inmate_data"])
    def test_recall_phrase_matrix_stream(self, state_machine, session, scope_id):
        if not ScopeRegistry.is_valid_scope(scope_id):
            ScopeRegistry.register(ScopeDefinition(
                id=scope_id,
                label=scope_id.replace("_", " ").title(),
                icon="🧪",
                description=f"{scope_id} scope",
                category="Testing",
                pipeline_class=MockPipeline,
            ))
        session.switch_scope(scope_id)
        _ = run_async(state_machine.handle_message("seed question", session))

        async def collect_events():
            events = []
            async for event in state_machine.dispatch_stream("what is my history?", session):
                events.append(event)
            return events

        events = run_async(collect_events())
        assert events[-1]["event"] == "result"
        assert events[-1]["data"].get("is_recall") is True
