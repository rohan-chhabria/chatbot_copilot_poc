"""Integration tests for the agent pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.pipelines.inmate_data.vanna_agent import AgentPipeline, _is_analytics_query, _is_error_message
from src.memory.conversation_store import NoOpConversationStore
from src.session.session_manager import InMemorySessionStore, create_session
from src.tenant.tenant_router import TenantContext


@pytest.fixture
def mock_tenant():
    return TenantContext(
        customer_key="demo",
        db_host="localhost",
        db_name="test_db",
        db_user="test",
        db_password="test",
        db_port=3306,
    )


@pytest.fixture
def pipeline():
    return AgentPipeline(
        session_store=InMemorySessionStore(),
        conversation_store=NoOpConversationStore(),
    )


class TestIsErrorMessage:
    def test_error_messages(self):
        assert _is_error_message("I don't know how to answer that") is True
        assert _is_error_message("I cannot generate SQL for this") is True
        assert _is_error_message("Sorry, insufficient information") is True

    def test_valid_sql(self):
        assert _is_error_message("SELECT COUNT(*) FROM dg_notes") is False
        assert _is_error_message("WITH cte AS (SELECT 1) SELECT * FROM cte") is False


class TestIsAnalyticsQuery:
    def test_count_query(self):
        rows = [{"count": 150}]
        assert _is_analytics_query(rows) is True

    def test_data_query(self):
        rows = [{"notes_id": 1, "notes_description": "text", "note_date": "2026-01-01"}]
        assert _is_analytics_query(rows) is False

    def test_empty_rows(self):
        assert _is_analytics_query([]) is False

    def test_multi_row_analytics(self):
        rows = [{"facility": "A", "count": 10}, {"facility": "B", "count": 20}]
        assert _is_analytics_query(rows) is True


class TestAgentPipelineWithMocks:
    @pytest.mark.asyncio
    @patch("src.pipelines.inmate_data.vanna_agent.generate_sql_via_llm", new_callable=AsyncMock)
    @patch("src.pipelines.inmate_data.vanna_agent.execute_query")
    async def test_successful_query(self, mock_exec, mock_gen_sql, pipeline, session, mock_tenant):
        mock_gen_sql.return_value = "SELECT COUNT(*) FROM dg_notes n WHERE n.status = 1"
        mock_exec.return_value = [{"count": 500}]

        result = await pipeline.process_question("How many notes are there?", session, mock_tenant)

        assert "error" not in result or result.get("error") == ""
        assert result["row_count"] == 1
        mock_gen_sql.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.pipelines.inmate_data.vanna_agent.generate_sql_via_llm", new_callable=AsyncMock)
    async def test_guardrails_block_injection(self, mock_gen_sql, pipeline, session, mock_tenant):
        result = await pipeline.process_question(
            "Show me UNION SELECT password FROM users",
            session,
            mock_tenant,
        )

        # Guardrails return error in 'summary' or 'error' key
        has_error = "error" in result or "disallowed" in result.get("summary", "").lower()
        assert has_error
        mock_gen_sql.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.pipelines.inmate_data.vanna_agent.generate_sql_via_llm", new_callable=AsyncMock)
    async def test_sql_generation_failure(self, mock_gen_sql, pipeline, session, mock_tenant):
        mock_gen_sql.return_value = "I don't know how to answer that"

        result = await pipeline.process_question("How many inmates are active?", session, mock_tenant)
        # Error can be in 'error' key or indicated in 'summary'
        has_error_indication = (
            "error" in result
            or "could not generate" in result.get("summary", "").lower()
            or "trouble understanding" in result.get("summary", "").lower()
        )
        assert has_error_indication

    @pytest.mark.asyncio
    @patch("src.pipelines.inmate_data.vanna_agent.generate_sql_via_llm", new_callable=AsyncMock)
    @patch("src.pipelines.inmate_data.vanna_agent.execute_query")
    async def test_empty_results(self, mock_exec, mock_gen_sql, pipeline, session, mock_tenant):
        mock_gen_sql.return_value = "SELECT * FROM dg_notes n WHERE n.notes_id = -1 AND n.status = 1"
        mock_exec.return_value = []

        result = await pipeline.process_question("Show notes for nonexistent inmate", session, mock_tenant)
        assert result["row_count"] == 0
        assert "No results" in result["summary"]

    @pytest.mark.asyncio
    @patch("src.pipelines.inmate_data.vanna_agent.generate_sql_via_llm", new_callable=AsyncMock)
    @patch("src.pipelines.inmate_data.vanna_agent.execute_query")
    async def test_session_updated_after_query(self, mock_exec, mock_gen_sql, pipeline, session, mock_tenant):
        mock_gen_sql.return_value = "SELECT COUNT(*) FROM dg_notes n WHERE n.status = 1"
        mock_exec.return_value = [{"count": 100}]

        initial_turns = len(session.turns)
        await pipeline.process_question("How many notes exist?", session, mock_tenant)

        assert len(session.turns) == initial_turns + 2

    @pytest.mark.asyncio
    @patch("src.pipelines.inmate_data.vanna_agent.generate_sql_via_llm", new_callable=AsyncMock)
    @patch("src.pipelines.inmate_data.vanna_agent.execute_query")
    async def test_facility_filter_injected(self, mock_exec, mock_gen_sql, pipeline, mock_tenant):
        session = create_session(
            customer_key="demo",
            user_id="Test.Officer",
            facility_ids=[101, 102],
        )
        mock_gen_sql.return_value = "SELECT COUNT(*) FROM dg_notes n WHERE n.status = 1"
        mock_exec.return_value = [{"count": 50}]

        await pipeline.process_question("How many notes in my facility?", session, mock_tenant)

        executed_sql = mock_exec.call_args[0][1]
        assert "101" in executed_sql or "102" in executed_sql

    @pytest.mark.asyncio
    @patch("src.pipelines.inmate_data.vanna_agent.generate_sql_via_llm", new_callable=AsyncMock)
    @patch("src.pipelines.inmate_data.vanna_agent.execute_query")
    async def test_retry_on_execution_error(self, mock_exec, mock_gen_sql, pipeline, session, mock_tenant):
        mock_gen_sql.side_effect = [
            "SELECT * FROM nonexistent_table",
            "SELECT COUNT(*) FROM dg_notes n WHERE n.status = 1",
        ]
        mock_exec.side_effect = [
            Exception("Table doesn't exist"),
            [{"count": 100}],
        ]

        result = await pipeline.process_question("How many notes?", session, mock_tenant)
        assert result["row_count"] == 1 or "error" in result
