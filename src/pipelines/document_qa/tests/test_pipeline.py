"""Tests for the Document QA pipeline."""

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
        assert ScopeRegistry.is_valid_scope("document_qa")

    def test_pipeline_metadata(self):
        _ensure_registered()
        from src.orchestrator.scope_registry import ScopeRegistry
        defn = ScopeRegistry.get_definition("document_qa")
        assert defn is not None
        assert defn.label == "Documents"
        assert defn.icon == "📄"
        assert defn.category == "Information"

    def test_get_instance(self):
        _ensure_registered()
        from src.orchestrator.scope_registry import ScopeRegistry
        from src.pipelines.base import Pipeline
        pipeline = ScopeRegistry.get("document_qa")
        assert pipeline is not None
        assert isinstance(pipeline, Pipeline)


class TestPipelineInterface:
    def test_welcome_message(self):
        _ensure_registered()
        from src.orchestrator.scope_registry import ScopeRegistry
        pipeline = ScopeRegistry.get("document_qa")
        msg = pipeline.get_welcome_message()
        assert "document" in msg.lower() or "upload" in msg.lower()

    def test_welcome_message_returning(self):
        _ensure_registered()
        from src.orchestrator.scope_registry import ScopeRegistry
        pipeline = ScopeRegistry.get("document_qa")
        msg = pipeline.get_welcome_message(is_returning=True)
        assert len(msg) > 0


class TestScopeContextIntegration:
    def test_context_created_on_switch(self):
        _ensure_registered()
        session = create_session(customer_key="demo", user_id="Test")
        session.switch_scope("document_qa")
        ctx = session.get_scope_context()

        assert ctx is not None
        assert ctx.scope == "document_qa"
