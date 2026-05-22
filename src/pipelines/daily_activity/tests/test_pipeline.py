"""Integration tests for the Daily Activity Pipeline."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.pipelines.daily_activity import response_formatter
from src.pipelines.daily_activity.pipeline import DailyActivityPipeline


class TestDailyActivityPipeline:
    """Tests for the DailyActivityPipeline class."""

    @pytest.fixture
    def pipeline(self):
        """Create pipeline instance."""
        return DailyActivityPipeline()

    @pytest.fixture
    def mock_scope_context(self):
        """Mock scope context."""
        return MagicMock()

    def test_supports_auto_execute(self, pipeline: DailyActivityPipeline):
        """Test that pipeline has auto-execute enabled."""
        assert pipeline.supports_auto_execute is True

    def test_scope_id(self, pipeline: DailyActivityPipeline):
        """Test scope ID is set correctly."""
        assert pipeline.scope_id == "daily_activity"

    def test_scope_label(self, pipeline: DailyActivityPipeline):
        """Test scope label is set correctly."""
        assert pipeline.scope_label == "Daily Activity"

    @pytest.mark.asyncio
    async def test_process_non_refresh_returns_instruction(
        self,
        pipeline: DailyActivityPipeline,
        mock_session: MagicMock,
        mock_scope_context: MagicMock,
    ):
        """Test that non-refresh input returns instruction message."""
        result = await pipeline.process(
            question="what is the weather?",
            session=mock_session,
            scope_context=mock_scope_context,
        )

        assert result["row_count"] == 0
        assert 'refresh' in result["summary"].lower()

    @pytest.mark.asyncio
    async def test_process_refresh_keyword(
        self,
        pipeline: DailyActivityPipeline,
        mock_session: MagicMock,
        mock_scope_context: MagicMock,
        sample_activity_result: dict[str, Any],
    ):
        """Test that 'refresh' keyword triggers activity check."""
        with patch.object(
            pipeline, "_run_activity_check", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = {
                "summary": "Test summary",
                "row_count": 5,
            }

            result = await pipeline.process(
                question="refresh",
                session=mock_session,
                scope_context=mock_scope_context,
            )

            mock_check.assert_called_once_with(mock_session)
            assert result["row_count"] == 5

    @pytest.mark.asyncio
    async def test_process_empty_question_triggers_check(
        self,
        pipeline: DailyActivityPipeline,
        mock_session: MagicMock,
        mock_scope_context: MagicMock,
    ):
        """Test that empty question triggers activity check (auto-execute)."""
        with patch.object(
            pipeline, "_run_activity_check", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = {
                "summary": "Test summary",
                "row_count": 5,
            }

            await pipeline.process(
                question="",
                session=mock_session,
                scope_context=mock_scope_context,
            )

            mock_check.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_activity_check_no_tenant(
        self,
        pipeline: DailyActivityPipeline,
        mock_session: MagicMock,
    ):
        """Test error handling when tenant cannot be resolved."""
        with patch(
            "src.tenant.tenant_router.resolve_tenant", return_value=None
        ):
            result = await pipeline._run_activity_check(mock_session)

            assert "error" in result["summary"].lower() or "unable" in result["summary"].lower()
            assert result["row_count"] == 0

    @pytest.mark.asyncio
    async def test_run_activity_check_no_facilities(
        self,
        pipeline: DailyActivityPipeline,
        mock_session: MagicMock,
        mock_tenant: MagicMock,
    ):
        """Test error handling when user has no facilities."""
        mock_session.facility_ids = []

        with patch(
            "src.tenant.tenant_router.resolve_tenant",
            return_value=mock_tenant,
        ):
            result = await pipeline._run_activity_check(mock_session)

            assert "no facilities" in result["summary"].lower()
            assert result["row_count"] == 0

    @pytest.mark.asyncio
    async def test_health_check(self, pipeline: DailyActivityPipeline):
        """Test health check returns expected structure."""
        result = await pipeline.health()

        assert result["status"] == "healthy"
        assert "lookback_hours" in result
        assert "lookahead_hours" in result

    def test_welcome_message_first_time(self, pipeline: DailyActivityPipeline):
        """Test welcome message for first-time users."""
        message = pipeline.get_welcome_message(is_returning=False)

        assert "activity status" in message.lower()

    def test_welcome_message_returning(self, pipeline: DailyActivityPipeline):
        """Test welcome message for returning users."""
        message = pipeline.get_welcome_message(is_returning=True)

        assert "welcome back" in message.lower()


class TestResponseFormatter:
    """Tests for the response formatter."""

    def test_format_instruction_message(self):
        """Test instruction message formatting."""
        message = response_formatter.format_instruction_message()
        assert "refresh" in message.lower()

    def test_format_no_facilities_error(self):
        """Test no facilities error message."""
        message = response_formatter.format_no_facilities_error()
        assert "no facilities" in message.lower()

    def test_format_error_response(self):
        """Test error response formatting."""
        message = response_formatter.format_error_response("Test error")
        assert "test error" in message.lower()
        assert "refresh" in message.lower()

    def test_format_single_facility_all_clear(self):
        """Test formatting when all activities are clear."""
        result = response_formatter.format_single_facility_response(
            facility_name="Main Block",
            missed={
                "total_missed_activities": 0,
                "activities": [],
            },
            upcoming={
                "total_upcoming_activities": 3,
                "activities": [
                    {"name": "Count", "start_time": "11:00", "end_time": "12:00"},
                    {"name": "Chow", "start_time": "12:00", "end_time": "14:00"},
                    {"name": "Pill", "start_time": "13:00", "end_time": "13:30"},
                ],
            },
            lookback_hours=8.0,
            lookahead_hours=4.0,
        )

        assert "no missed" in result.lower()
        assert "3 upcoming" in result.lower()
        assert "refresh" in result.lower()

    def test_format_single_facility_nothing_scheduled(self):
        """Test formatting when nothing is scheduled."""
        result = response_formatter.format_single_facility_response(
            facility_name="Main Block",
            missed={"total_missed_activities": 0, "activities": []},
            upcoming={"total_upcoming_activities": 0, "activities": []},
            lookback_hours=8.0,
            lookahead_hours=4.0,
        )

        assert "no missed or upcoming" in result.lower()

    def test_format_single_facility_both_missed_and_upcoming(
        self, sample_activity_result: dict[str, Any]
    ):
        """Test formatting with both missed and upcoming activities."""
        facility_data = sample_activity_result["by_facility"]["63"]

        result = response_formatter.format_single_facility_response(
            facility_name="Main Block",
            missed=facility_data["missed"],
            upcoming=facility_data["upcoming"],
            lookback_hours=8.0,
            lookahead_hours=4.0,
        )

        assert "3 missed" in result.lower()
        assert "5 upcoming" in result.lower()
        assert "missed" in result.lower()
        assert "upcoming" in result.lower()

    def test_format_multi_facility_response(
        self, multi_facility_result: dict[str, Any]
    ):
        """Test formatting multi-facility response."""
        result = response_formatter.format_multi_facility_response(
            by_facility=multi_facility_result["by_facility"],
            total_missed=5,
            total_upcoming=8,
            lookback_hours=8.0,
            lookahead_hours=4.0,
        )

        assert "2 facilities" in result.lower()
        assert "5 missed" in result.lower()
        assert "8 upcoming" in result.lower()
        assert "main block" in result.lower()
        assert "east wing" in result.lower()

    def test_format_activity_response_single_facility(
        self, sample_activity_result: dict[str, Any]
    ):
        """Test main format function for single facility."""
        result = response_formatter.format_activity_response(sample_activity_result)

        assert "refresh" in result.lower()
        assert "main block" in result.lower()

    def test_format_activity_response_multi_facility(
        self, multi_facility_result: dict[str, Any]
    ):
        """Test main format function for multiple facilities."""
        result = response_formatter.format_activity_response(multi_facility_result)

        assert "2 facilities" in result.lower()

    def test_format_activity_response_no_facilities(self):
        """Test main format function with no facilities."""
        result = response_formatter.format_activity_response({"by_facility": {}})

        assert "no facilities" in result.lower()


class TestStreamProcess:
    """Tests for streaming process."""

    @pytest.fixture
    def pipeline(self):
        return DailyActivityPipeline()

    @pytest.mark.asyncio
    async def test_process_stream_non_refresh(
        self,
        pipeline: DailyActivityPipeline,
        mock_session: MagicMock,
        mock_scope_context: MagicMock,
    ):
        """Test streaming non-refresh input returns instruction."""
        events = []
        async for event in pipeline.process_stream(
            question="hello",
            session=mock_session,
            scope_context=mock_scope_context,
        ):
            events.append(event)

        assert len(events) == 1
        assert events[0]["event"] == "result"
        assert "refresh" in events[0]["data"]["summary"].lower()

    @pytest.mark.asyncio
    async def test_process_stream_refresh(
        self,
        pipeline: DailyActivityPipeline,
        mock_session: MagicMock,
        mock_scope_context: MagicMock,
    ):
        """Test streaming refresh triggers activity check with status events."""
        with patch.object(
            pipeline, "_run_activity_check", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = {"summary": "Test", "row_count": 5}

            events = []
            async for event in pipeline.process_stream(
                question="refresh",
                session=mock_session,
                scope_context=mock_scope_context,
            ):
                events.append(event)

            status_events = [e for e in events if e.get("event") == "status"]
            result_events = [e for e in events if e.get("event") == "result"]

            assert len(status_events) >= 2  # "Checking missed..." and "Checking upcoming..."
            assert len(result_events) == 1
