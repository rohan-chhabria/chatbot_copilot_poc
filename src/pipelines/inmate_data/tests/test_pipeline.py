"""Tests for the Inmate Data pipeline."""

from __future__ import annotations

from src.session.models import create_session


def _ensure_registered():
    """Ensure pipelines are registered."""
    import src.pipelines.document_qa  # noqa: F401
    import src.pipelines.inmate_data  # noqa: F401


class TestPipelineRegistration:
    def test_pipeline_registered(self):
        _ensure_registered()
        from src.orchestrator.scope_registry import ScopeRegistry
        assert ScopeRegistry.is_valid_scope("inmate_data")

    def test_pipeline_metadata(self):
        _ensure_registered()
        from src.orchestrator.scope_registry import ScopeRegistry
        defn = ScopeRegistry.get_definition("inmate_data")
        assert defn is not None
        assert defn.label == "Inmate Data"
        assert defn.icon == "📊"
        assert defn.category == "Data & Analytics"

    def test_get_instance(self):
        _ensure_registered()
        from src.orchestrator.scope_registry import ScopeRegistry
        from src.pipelines.base import Pipeline
        pipeline = ScopeRegistry.get("inmate_data")
        assert pipeline is not None
        assert isinstance(pipeline, Pipeline)


class TestPipelineInterface:
    def test_welcome_message(self):
        _ensure_registered()
        from src.orchestrator.scope_registry import ScopeRegistry
        pipeline = ScopeRegistry.get("inmate_data")
        msg = pipeline.get_welcome_message()
        assert "Inmate Data" in msg or "notes" in msg.lower()

    def test_welcome_message_returning(self):
        _ensure_registered()
        from src.orchestrator.scope_registry import ScopeRegistry
        pipeline = ScopeRegistry.get("inmate_data")
        msg = pipeline.get_welcome_message(is_returning=True)
        assert "back" in msg.lower() or "remember" in msg.lower()


class TestScopeContextIntegration:
    def test_context_preserved_across_scope_switch(self):
        _ensure_registered()
        session = create_session(customer_key="demo", user_id="Test")
        session.switch_scope("inmate_data")
        ctx = session.get_scope_context()

        # Simulate adding context from pipeline response
        ctx.add_query("Show fire watch notes")
        ctx.update_entity("keyword", "Fire Watch")

        assert "Show fire watch notes" in ctx.recent_queries
        assert ctx.recent_entities["keyword"] == "Fire Watch"

        # Switch to another scope and back
        session.switch_scope("document_qa")
        session.switch_scope("inmate_data")

        # Context should be preserved
        restored = session.get_scope_context()
        assert "Show fire watch notes" in restored.recent_queries
        assert restored.recent_entities["keyword"] == "Fire Watch"
