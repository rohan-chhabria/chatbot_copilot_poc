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
    
    async def process(self, question, session, scope_context):
        return {"summary": f"Mock response to: {question}", "row_count": 0}
    
    async def process_stream(self, question, session, scope_context):
        yield {"event": "result", "data": {"summary": "Mock"}}
    
    async def health(self):
        return {"status": "healthy"}


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
        
        # Switch away and back
        session.active_scope = None
        result = state_machine.select_scope("mock_scope", session)
        
        assert "Welcome back" in result["summary"]
        assert "Previous query" in result["summary"]


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
