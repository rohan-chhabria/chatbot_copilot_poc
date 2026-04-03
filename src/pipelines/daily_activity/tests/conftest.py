"""Test fixtures for Daily Activity Pipeline tests."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def sample_timetable() -> list[dict[str, Any]]:
    """Sample timetable data for testing."""
    return [
        {
            "day": "Monday",
            "tasks": [
                {
                    "task": "Count-Official",
                    "start_time": "03:00:00",
                    "end_time": "04:00:00",
                    "keywords": "Official Count |",
                    "statuses": {},
                },
                {
                    "task": "Pill Call",
                    "start_time": "04:45:00",
                    "end_time": "05:30:00",
                    "keywords": "Pill Call |, Medical |",
                    "statuses": {},
                },
                {
                    "task": "Chow Call",
                    "start_time": "05:00:00",
                    "end_time": "07:00:00",
                    "keywords": "Chow |, Meal |",
                    "statuses": {},
                },
                {
                    "task": "Recreation",
                    "start_time": "10:00:00",
                    "end_time": "11:00:00",
                    "keywords": "Recreation |, Yard |",
                    "statuses": {},
                },
            ],
        },
        {
            "day": "Tuesday",
            "tasks": [
                {
                    "task": "Count-Official",
                    "start_time": "03:00:00",
                    "end_time": "04:00:00",
                    "keywords": "Official Count |",
                    "statuses": {},
                },
            ],
        },
    ]


@pytest.fixture
def mock_session() -> MagicMock:
    """Mock session object for testing."""
    session = MagicMock()
    session.session_id = "test-session-123"
    session.customer_key = "demo"
    session.user_id = "test-user"
    session.facility_ids = [63, 164]
    return session


@pytest.fixture
def mock_tenant() -> MagicMock:
    """Mock tenant context for testing."""
    tenant = MagicMock()
    tenant.customer_key = "demo"
    tenant.db_host = "localhost"
    tenant.db_name = "test_db"
    return tenant


@pytest.fixture
def mock_scope_context() -> MagicMock:
    """Mock scope context for testing."""
    context = MagicMock()
    context.recent_queries = []
    context.last_entity = None
    return context


@pytest.fixture
def sample_activity_result() -> dict[str, Any]:
    """Sample activity check result for testing formatters."""
    return {
        "total_missed": 3,
        "total_upcoming": 5,
        "facility_count": 1,
        "lookback_hours": 8.0,
        "lookahead_hours": 4.0,
        "given_date_time": "2026-03-20 09:30:00",
        "by_facility": {
            "63": {
                "facility_name": "Main Block",
                "missed": {
                    "period": {"start": "03-20-2026 01:30", "end": "03-20-2026 09:30"},
                    "total_missed_activities": 3,
                    "activities": [
                        {
                            "name": "Count-Official",
                            "start_time": "03:00",
                            "end_time": "04:00",
                            "keywords": ["Official Count |"],
                            "keyword_id": 123,
                            "statuses": {},
                            "tag_status_id": None,
                        },
                        {
                            "name": "Pill Call",
                            "start_time": "04:45",
                            "end_time": "05:30",
                            "keywords": ["Pill Call |"],
                            "keyword_id": 124,
                            "statuses": {},
                            "tag_status_id": None,
                        },
                        {
                            "name": "Chow Call",
                            "start_time": "05:00",
                            "end_time": "07:00",
                            "keywords": ["Chow |"],
                            "keyword_id": 125,
                            "statuses": {},
                            "tag_status_id": None,
                        },
                    ],
                    "activities_by_type": {},
                },
                "upcoming": {
                    "period": {"start": "03-20-2026 09:30", "end": "03-20-2026 13:30"},
                    "total_upcoming_activities": 5,
                    "activities": [
                        {
                            "name": "Recreation",
                            "start_time": "10:00",
                            "end_time": "11:00",
                            "keywords": ["Recreation |"],
                            "keyword_id": 126,
                            "statuses": {},
                            "tag_status_id": None,
                        },
                        {
                            "name": "Count-Official",
                            "start_time": "11:00",
                            "end_time": "12:00",
                            "keywords": ["Official Count |"],
                            "keyword_id": 123,
                            "statuses": {},
                            "tag_status_id": None,
                        },
                        {
                            "name": "Chow Call",
                            "start_time": "12:00",
                            "end_time": "14:00",
                            "keywords": ["Chow |"],
                            "keyword_id": 125,
                            "statuses": {},
                            "tag_status_id": None,
                        },
                        {
                            "name": "1st Block/Program",
                            "start_time": "09:30",
                            "end_time": "11:30",
                            "keywords": ["Program |"],
                            "keyword_id": 127,
                            "statuses": {},
                            "tag_status_id": None,
                        },
                        {
                            "name": "Pill Call",
                            "start_time": "13:00",
                            "end_time": "13:30",
                            "keywords": ["Pill Call |"],
                            "keyword_id": 124,
                            "statuses": {},
                            "tag_status_id": None,
                        },
                    ],
                    "activities_by_type": {},
                },
            },
        },
    }


@pytest.fixture
def multi_facility_result(sample_activity_result: dict[str, Any]) -> dict[str, Any]:
    """Sample multi-facility activity check result."""
    result = sample_activity_result.copy()
    result["facility_count"] = 2
    result["total_missed"] = 5
    result["total_upcoming"] = 8
    result["by_facility"]["164"] = {
        "facility_name": "East Wing",
        "missed": {
            "period": {"start": "03-20-2026 01:30", "end": "03-20-2026 09:30"},
            "total_missed_activities": 2,
            "activities": [
                {
                    "name": "Count-Official",
                    "start_time": "03:00",
                    "end_time": "04:00",
                    "keywords": ["Official Count |"],
                    "keyword_id": 123,
                    "statuses": {},
                    "tag_status_id": None,
                },
                {
                    "name": "Sanitation Check",
                    "start_time": "06:00",
                    "end_time": "06:30",
                    "keywords": ["Sanitation |"],
                    "keyword_id": 128,
                    "statuses": {},
                    "tag_status_id": None,
                },
            ],
            "activities_by_type": {},
        },
        "upcoming": {
            "period": {"start": "03-20-2026 09:30", "end": "03-20-2026 13:30"},
            "total_upcoming_activities": 3,
            "activities": [
                {
                    "name": "Medical Rounds",
                    "start_time": "09:45",
                    "end_time": "10:15",
                    "keywords": ["Medical |"],
                    "keyword_id": 129,
                    "statuses": {},
                    "tag_status_id": None,
                },
                {
                    "name": "Count-Official",
                    "start_time": "11:00",
                    "end_time": "12:00",
                    "keywords": ["Official Count |"],
                    "keyword_id": 123,
                    "statuses": {},
                    "tag_status_id": None,
                },
                {
                    "name": "Chow Call",
                    "start_time": "12:00",
                    "end_time": "14:00",
                    "keywords": ["Chow |"],
                    "keyword_id": 125,
                    "statuses": {},
                    "tag_status_id": None,
                },
            ],
            "activities_by_type": {},
        },
    }
    return result
