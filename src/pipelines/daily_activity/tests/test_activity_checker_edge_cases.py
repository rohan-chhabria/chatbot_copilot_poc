"""
Comprehensive edge case tests for the Activity Checker module.

Tests cover:
- Midnight crossing tasks
- Multi-day time ranges
- Day transitions
- Time range boundaries
- Record matching with tolerance
- Status/substatus matching
- Keyword lookup resolution
- Response structure validation
- Error scenarios
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import pytest

from src.pipelines.daily_activity import activity_checker


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def timetable_with_midnight_crossing() -> list[dict[str, Any]]:
    """Timetable with tasks that cross midnight."""
    return [
        {
            "day": "Friday",
            "tasks": [
                {
                    "task": "Night Count",
                    "start_time": "23:00:00",
                    "end_time": "00:30:00",  # Crosses midnight
                    "keywords": "Night Count |",
                    "statuses": {},
                },
                {
                    "task": "Night Shift Change",
                    "start_time": "23:30:00",
                    "end_time": "00:15:00",  # Crosses midnight
                    "keywords": "Shift Change |",
                    "statuses": {},
                },
                {
                    "task": "Morning Prep",
                    "start_time": "05:00:00",
                    "end_time": "06:00:00",
                    "keywords": "Prep |",
                    "statuses": {},
                },
            ],
        },
        {
            "day": "Saturday",
            "tasks": [
                {
                    "task": "Weekend Count",
                    "start_time": "06:00:00",
                    "end_time": "07:00:00",
                    "keywords": "Weekend Count |",
                    "statuses": {},
                },
                {
                    "task": "Late Night Watch",
                    "start_time": "23:45:00",
                    "end_time": "01:00:00",  # Crosses midnight into Sunday
                    "keywords": "Night Watch |",
                    "statuses": {},
                },
            ],
        },
        {
            "day": "Sunday",
            "tasks": [
                {
                    "task": "Sunday Count",
                    "start_time": "08:00:00",
                    "end_time": "09:00:00",
                    "keywords": "Sunday Count |",
                    "statuses": {},
                },
            ],
        },
    ]


@pytest.fixture
def timetable_with_status_tasks() -> list[dict[str, Any]]:
    """Timetable with status-based tasks."""
    return [
        {
            "day": "Monday",
            "tasks": [
                {
                    "task": "Fire Watch Check",
                    "start_time": "06:00:00",
                    "end_time": "06:30:00",
                    "keywords": "",
                    "statuses": {"Fire Watch": []},  # Empty = any substatus
                },
                {
                    "task": "Suicide Watch Check",
                    "start_time": "07:00:00",
                    "end_time": "07:30:00",
                    "keywords": "",
                    "statuses": {"Suicide Watch": ["SW-15", "SW-30"]},  # Specific substatuses
                },
                {
                    "task": "Medical Check",
                    "start_time": "08:00:00",
                    "end_time": "08:30:00",
                    "keywords": "Medical |",
                    "statuses": {"Medical Hold": []},  # Both keyword and status
                },
            ],
        },
    ]


@pytest.fixture
def keyword_status_lookup() -> dict[str, dict[str, int]]:
    """Sample lookup for keyword_id and tag_status_id resolution."""
    return {
        "keywords": {
            "Official Count |": 101,
            "Night Count |": 102,
            "Medical |": 103,
            "Chow |": 104,
            "Recreation |": 105,
        },
        "statuses": {
            "Fire Watch": 201,
            "Suicide Watch": 202,
            "Medical Hold": 203,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# MIDNIGHT CROSSING TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestMidnightCrossing:
    """Tests for tasks that cross midnight."""

    def test_task_crossing_midnight_detected_in_range(
        self, timetable_with_midnight_crossing: list[dict]
    ):
        """Test that a task starting before midnight and ending after is detected."""
        # Friday 22:00 to Saturday 02:00 (crosses midnight)
        start_dt = datetime(2026, 3, 27, 22, 0)  # Friday
        end_dt = datetime(2026, 3, 28, 2, 0)     # Saturday

        tasks = activity_checker.get_tasks_in_range(
            timetable_with_midnight_crossing, start_dt, end_dt
        )

        task_names = [t["task"] for t in tasks]
        assert "Night Count" in task_names
        assert "Night Shift Change" in task_names

    def test_midnight_task_correct_end_datetime(
        self, timetable_with_midnight_crossing: list[dict]
    ):
        """Test that midnight-crossing task has correct end datetime (next day)."""
        start_dt = datetime(2026, 3, 27, 22, 0)  # Friday
        end_dt = datetime(2026, 3, 28, 2, 0)     # Saturday

        tasks = activity_checker.get_tasks_in_range(
            timetable_with_midnight_crossing, start_dt, end_dt
        )

        night_count = next(t for t in tasks if t["task"] == "Night Count")

        # Task starts Friday 23:00, ends Saturday 00:30
        assert night_count["task_start_dt"] == datetime(2026, 3, 27, 23, 0)
        assert night_count["task_end_dt"] == datetime(2026, 3, 28, 0, 30)

    def test_lookback_crossing_midnight(
        self, timetable_with_midnight_crossing: list[dict]
    ):
        """Test lookback window that crosses midnight finds previous day tasks."""
        # Saturday 01:00, looking back 4 hours to Friday 21:00
        given_dt = datetime(2026, 3, 28, 1, 0)
        cached_records = pd.DataFrame()

        result = activity_checker.get_missed_activities(
            timetable=timetable_with_midnight_crossing,
            cached_records=cached_records,
            given_dt=given_dt,
            lookback_hours=-4,  # 4 hours back = Friday 21:00
            tolerance_minutes=0,
            lookup=None,
        )

        # Should find Friday's midnight-crossing tasks
        task_names = [a["name"] for a in result["activities"]]
        assert "Night Count" in task_names or "Night Shift Change" in task_names

    def test_lookahead_crossing_midnight(
        self, timetable_with_midnight_crossing: list[dict]
    ):
        """Test lookahead window that crosses midnight finds next day tasks."""
        # Saturday 23:00, looking ahead 4 hours to Sunday 03:00
        given_dt = datetime(2026, 3, 28, 23, 0)

        result = activity_checker.get_upcoming_activities(
            timetable=timetable_with_midnight_crossing,
            given_dt=given_dt,
            lookahead_hours=4,
            lookup=None,
        )

        # Should find Saturday's midnight-crossing task
        task_names = [a["name"] for a in result["activities"]]
        assert "Late Night Watch" in task_names

    def test_no_duplicate_midnight_tasks(
        self, timetable_with_midnight_crossing: list[dict]
    ):
        """Test that midnight-crossing tasks are not duplicated."""
        # Wide range that could catch same task twice
        start_dt = datetime(2026, 3, 27, 20, 0)  # Friday
        end_dt = datetime(2026, 3, 28, 6, 0)     # Saturday

        tasks = activity_checker.get_tasks_in_range(
            timetable_with_midnight_crossing, start_dt, end_dt
        )

        # Count occurrences of Night Count
        night_count_count = sum(1 for t in tasks if t["task"] == "Night Count")
        assert night_count_count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# TIME RANGE BOUNDARY TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestTimeRangeBoundaries:
    """Tests for time range edge cases and boundaries."""

    def test_task_at_exact_start_boundary(self, sample_timetable: list[dict]):
        """Test task starting exactly at range start is included."""
        # Monday 03:00 - Count-Official starts at 03:00
        start_dt = datetime(2026, 3, 23, 3, 0)
        end_dt = datetime(2026, 3, 23, 4, 0)

        tasks = activity_checker.get_tasks_in_range(sample_timetable, start_dt, end_dt)

        task_names = [t["task"] for t in tasks]
        assert "Count-Official" in task_names

    def test_task_at_exact_end_boundary(self, sample_timetable: list[dict]):
        """Test task ending exactly at range end - overlap logic."""
        # Range ends at 04:00, Count-Official ends at 04:00
        start_dt = datetime(2026, 3, 23, 2, 0)
        end_dt = datetime(2026, 3, 23, 4, 0)

        tasks = activity_checker.get_tasks_in_range(sample_timetable, start_dt, end_dt)

        task_names = [t["task"] for t in tasks]
        assert "Count-Official" in task_names

    def test_task_partial_overlap_start(self, sample_timetable: list[dict]):
        """Test task that starts before range but overlaps."""
        # Range starts at 03:30, Count-Official runs 03:00-04:00
        start_dt = datetime(2026, 3, 23, 3, 30)
        end_dt = datetime(2026, 3, 23, 5, 0)

        tasks = activity_checker.get_tasks_in_range(sample_timetable, start_dt, end_dt)

        task_names = [t["task"] for t in tasks]
        assert "Count-Official" in task_names

    def test_task_partial_overlap_end(self, sample_timetable: list[dict]):
        """Test task that ends after range but overlaps."""
        # Range ends at 05:15, Chow Call runs 05:00-07:00
        start_dt = datetime(2026, 3, 23, 4, 0)
        end_dt = datetime(2026, 3, 23, 5, 15)

        tasks = activity_checker.get_tasks_in_range(sample_timetable, start_dt, end_dt)

        task_names = [t["task"] for t in tasks]
        assert "Chow Call" in task_names

    def test_task_completely_outside_range(self, sample_timetable: list[dict]):
        """Test task completely outside range is not included."""
        # Range 08:00-09:00, Recreation is 10:00-11:00
        start_dt = datetime(2026, 3, 23, 8, 0)
        end_dt = datetime(2026, 3, 23, 9, 0)

        tasks = activity_checker.get_tasks_in_range(sample_timetable, start_dt, end_dt)

        task_names = [t["task"] for t in tasks]
        assert "Recreation" not in task_names

    def test_fractional_hours_lookback(self, sample_timetable: list[dict]):
        """Test lookback with fractional hours (e.g., 1.5 hours)."""
        given_dt = datetime(2026, 3, 23, 5, 0)
        start_dt, end_dt = activity_checker.calculate_time_range(given_dt, -1.5)

        assert start_dt == datetime(2026, 3, 23, 3, 30)
        assert end_dt == given_dt

    def test_fractional_hours_lookahead(self, sample_timetable: list[dict]):
        """Test lookahead with fractional hours."""
        given_dt = datetime(2026, 3, 23, 9, 0)
        start_dt, end_dt = activity_checker.calculate_time_range(given_dt, 2.5)

        assert start_dt == given_dt
        assert end_dt == datetime(2026, 3, 23, 11, 30)

    def test_multi_day_range(self, timetable_with_midnight_crossing: list[dict]):
        """Test time range spanning multiple days."""
        # Friday 04:00 to Sunday 12:00 (include Morning Prep at 05:00)
        start_dt = datetime(2026, 3, 27, 4, 0)   # Friday
        end_dt = datetime(2026, 3, 29, 12, 0)    # Sunday

        tasks = activity_checker.get_tasks_in_range(
            timetable_with_midnight_crossing, start_dt, end_dt
        )

        task_names = [t["task"] for t in tasks]
        # Should include tasks from Friday, Saturday, and Sunday
        assert "Morning Prep" in task_names     # Friday 05:00-06:00
        assert "Weekend Count" in task_names    # Saturday 06:00-07:00
        assert "Sunday Count" in task_names     # Sunday 08:00-09:00


# ═══════════════════════════════════════════════════════════════════════════════
# RECORD MATCHING TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecordMatching:
    """Tests for record-to-task matching logic."""

    def test_record_matches_with_tolerance(self, sample_timetable: list[dict]):
        """Test that tolerance_minutes extends the matching window."""
        # Task ends at 04:00, record at 04:05 should match with 10min tolerance
        task_end = datetime(2026, 3, 23, 4, 0)
        record_time = datetime(2026, 3, 23, 4, 5)

        cached_records = pd.DataFrame([{
            "date_added": record_time,
            "Status_Keyword": "Keyword",
            "keyword_name": "Official Count |",
            "tag_status_name": "",
            "tag_status_ids": "",
        }])

        given_dt = datetime(2026, 3, 23, 5, 0)

        # With 10 minute tolerance
        result = activity_checker.get_missed_activities(
            timetable=sample_timetable,
            cached_records=cached_records,
            given_dt=given_dt,
            lookback_hours=-3,
            tolerance_minutes=10,
            lookup=None,
        )

        # Count-Official should NOT be in missed (record matched with tolerance)
        missed_names = [a["name"] for a in result["activities"]]
        assert "Count-Official" not in missed_names

    def test_record_outside_tolerance_is_missed(self, sample_timetable: list[dict]):
        """Test that record outside tolerance window results in missed activity."""
        # Task ends at 04:00, record at 04:15 should NOT match with 10min tolerance
        record_time = datetime(2026, 3, 23, 4, 15)

        cached_records = pd.DataFrame([{
            "date_added": record_time,
            "Status_Keyword": "Keyword",
            "keyword_name": "Official Count |",
            "tag_status_name": "",
            "tag_status_ids": "",
        }])

        given_dt = datetime(2026, 3, 23, 5, 0)

        result = activity_checker.get_missed_activities(
            timetable=sample_timetable,
            cached_records=cached_records,
            given_dt=given_dt,
            lookback_hours=-3,
            tolerance_minutes=10,
            lookup=None,
        )

        # Count-Official SHOULD be in missed (record outside tolerance)
        missed_names = [a["name"] for a in result["activities"]]
        assert "Count-Official" in missed_names

    def test_status_with_any_substatus(self, timetable_with_status_tasks: list[dict]):
        """Test status matching with empty substatus list (any substatus)."""
        record = {
            "Status_Keyword": "Status",
            "tag_status_name": "Fire Watch",
            "tag_status_ids": "FW-Custom",  # Any substatus should match
        }
        task = {
            "keywords": "",
            "statuses": {"Fire Watch": []},  # Empty = any substatus
        }

        assert activity_checker.record_matches_task(record, task) is True

    def test_status_with_specific_substatus_match(
        self, timetable_with_status_tasks: list[dict]
    ):
        """Test status matching with specific substatus that matches."""
        record = {
            "Status_Keyword": "Status",
            "tag_status_name": "Suicide Watch",
            "tag_status_ids": "SW-15",  # Matches one of the specified
        }
        task = {
            "keywords": "",
            "statuses": {"Suicide Watch": ["SW-15", "SW-30"]},
        }

        assert activity_checker.record_matches_task(record, task) is True

    def test_status_with_specific_substatus_no_match(
        self, timetable_with_status_tasks: list[dict]
    ):
        """Test status matching with specific substatus that doesn't match."""
        record = {
            "Status_Keyword": "Status",
            "tag_status_name": "Suicide Watch",
            "tag_status_ids": "SW-60",  # Doesn't match specified substatuses
        }
        task = {
            "keywords": "",
            "statuses": {"Suicide Watch": ["SW-15", "SW-30"]},
        }

        assert activity_checker.record_matches_task(record, task) is False

    def test_multiple_keywords_first_match(self):
        """Test that any matching keyword from multiple satisfies the match."""
        record = {
            "Status_Keyword": "Keyword",
            "keyword_name": "Meal |",  # Second keyword in list
        }
        task = {
            "keywords": "Chow |, Meal |, Lunch |",
            "statuses": {},
        }

        assert activity_checker.record_matches_task(record, task) is True

    def test_record_type_keyword_vs_status(self):
        """Test that record type determines matching path."""
        # Keyword record should only check keywords
        keyword_record = {
            "Status_Keyword": "Keyword",
            "keyword_name": "Fire Watch",  # Same name as status
            "tag_status_name": "",
        }
        task = {
            "keywords": "",
            "statuses": {"Fire Watch": []},
        }

        # Should NOT match because it's a Keyword record, not Status
        assert activity_checker.record_matches_task(keyword_record, task) is False


# ═══════════════════════════════════════════════════════════════════════════════
# KEYWORD/STATUS LOOKUP TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestKeywordStatusLookup:
    """Tests for keyword_id and tag_status_id resolution."""

    def test_resolve_keyword_id(self, keyword_status_lookup: dict):
        """Test resolving keyword_id from lookup."""
        task = {
            "keywords": "Official Count |, Roll Call |",
            "statuses": {},
        }

        keyword_id, tag_status_id = activity_checker.resolve_ids_from_lookup(
            task, keyword_status_lookup
        )

        assert keyword_id == 101  # First matching keyword
        assert tag_status_id is None

    def test_resolve_status_id(self, keyword_status_lookup: dict):
        """Test resolving tag_status_id from lookup."""
        task = {
            "keywords": "",
            "statuses": {"Fire Watch": []},
        }

        keyword_id, tag_status_id = activity_checker.resolve_ids_from_lookup(
            task, keyword_status_lookup
        )

        assert keyword_id is None
        assert tag_status_id == 201

    def test_resolve_both_keyword_and_status(self, keyword_status_lookup: dict):
        """Test task with both keyword and status resolves both."""
        task = {
            "keywords": "Medical |",
            "statuses": {"Medical Hold": []},
        }

        keyword_id, tag_status_id = activity_checker.resolve_ids_from_lookup(
            task, keyword_status_lookup
        )

        assert keyword_id == 103
        assert tag_status_id == 203

    def test_resolve_with_none_lookup(self):
        """Test resolve returns None when lookup is None."""
        task = {
            "keywords": "Official Count |",
            "statuses": {},
        }

        keyword_id, tag_status_id = activity_checker.resolve_ids_from_lookup(
            task, None
        )

        assert keyword_id is None
        assert tag_status_id is None

    def test_resolve_keyword_not_in_lookup(self, keyword_status_lookup: dict):
        """Test keyword not in lookup returns None for keyword_id."""
        task = {
            "keywords": "Unknown Keyword |",
            "statuses": {},
        }

        keyword_id, tag_status_id = activity_checker.resolve_ids_from_lookup(
            task, keyword_status_lookup
        )

        assert keyword_id is None

    def test_resolve_first_matching_keyword(self, keyword_status_lookup: dict):
        """Test that first matching keyword is used when multiple present."""
        task = {
            "keywords": "Unknown |, Night Count |, Official Count |",
            "statuses": {},
        }

        keyword_id, tag_status_id = activity_checker.resolve_ids_from_lookup(
            task, keyword_status_lookup
        )

        # Night Count | should match first (102)
        assert keyword_id == 102


# ═══════════════════════════════════════════════════════════════════════════════
# RESPONSE STRUCTURE VALIDATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestResponseStructure:
    """Tests for validating response structure and content."""

    def test_missed_response_has_correct_period(self, sample_timetable: list[dict]):
        """Test that missed response has correct period dates."""
        given_dt = datetime(2026, 3, 23, 10, 0)
        cached_records = pd.DataFrame()

        result = activity_checker.get_missed_activities(
            timetable=sample_timetable,
            cached_records=cached_records,
            given_dt=given_dt,
            lookback_hours=-8,
            tolerance_minutes=0,
            lookup=None,
        )

        assert result["period"]["start"] == "03-23-2026 02:00"
        assert result["period"]["end"] == "03-23-2026 10:00"

    def test_upcoming_response_has_correct_period(self, sample_timetable: list[dict]):
        """Test that upcoming response has correct period dates."""
        given_dt = datetime(2026, 3, 23, 9, 0)

        result = activity_checker.get_upcoming_activities(
            timetable=sample_timetable,
            given_dt=given_dt,
            lookahead_hours=4,
            lookup=None,
        )

        assert result["period"]["start"] == "03-23-2026 09:00"
        assert result["period"]["end"] == "03-23-2026 13:00"

    def test_activity_time_format_is_hhmm(self, sample_timetable: list[dict]):
        """Test that activity times are formatted as HH:MM."""
        given_dt = datetime(2026, 3, 23, 9, 0)

        result = activity_checker.get_upcoming_activities(
            timetable=sample_timetable,
            given_dt=given_dt,
            lookahead_hours=4,
            lookup=None,
        )

        if result["activities"]:
            activity = result["activities"][0]
            # Check format is HH:MM (5 characters with colon in middle)
            assert len(activity["start_time"]) == 5
            assert activity["start_time"][2] == ":"
            assert len(activity["end_time"]) == 5
            assert activity["end_time"][2] == ":"

    def test_insights_structure_when_activities_exist(
        self, sample_timetable: list[dict]
    ):
        """Test insights are populated when activities exist."""
        given_dt = datetime(2026, 3, 23, 9, 0)
        cached_records = pd.DataFrame()

        result = activity_checker.get_missed_activities(
            timetable=sample_timetable,
            cached_records=cached_records,
            given_dt=given_dt,
            lookback_hours=-8,
            tolerance_minutes=0,
            lookup=None,
        )

        if result["total_missed_activities"] > 0:
            assert result["insights"]["first_missed"] is not None
            assert result["insights"]["last_missed"] is not None
            assert len(result["insights"]["missed_types"]) > 0
            # Check format includes duration
            assert "-" in result["insights"]["first_missed"]

    def test_insights_structure_when_no_activities(self, sample_timetable: list[dict]):
        """Test insights are None/empty when no activities."""
        given_dt = datetime(2026, 3, 23, 9, 0)

        result = activity_checker.get_upcoming_activities(
            timetable=sample_timetable,
            given_dt=given_dt,
            lookahead_hours=0,  # Zero lookahead = no activities
            lookup=None,
        )

        assert result["insights"]["first_upcoming"] is None
        assert result["insights"]["last_upcoming"] is None
        assert result["insights"]["upcoming_types"] == []

    def test_activities_by_type_populated(self, sample_timetable: list[dict]):
        """Test activities_by_type is correctly populated."""
        given_dt = datetime(2026, 3, 23, 8, 0)
        cached_records = pd.DataFrame()

        result = activity_checker.get_missed_activities(
            timetable=sample_timetable,
            cached_records=cached_records,
            given_dt=given_dt,
            lookback_hours=-6,
            tolerance_minutes=0,
            lookup=None,
        )

        if result["total_missed_activities"] > 0:
            # Should have categorized activities
            all_types = list(result["activities_by_type"].keys())
            # Check at least one type exists
            assert len(all_types) > 0
            # Check format of entries
            for type_name, activities in result["activities_by_type"].items():
                for activity_str in activities:
                    assert "(" in activity_str
                    assert "-" in activity_str  # Time range format

    def test_total_count_matches_activities_length(self, sample_timetable: list[dict]):
        """Test that total count matches actual activities list length."""
        given_dt = datetime(2026, 3, 23, 9, 0)

        result = activity_checker.get_upcoming_activities(
            timetable=sample_timetable,
            given_dt=given_dt,
            lookahead_hours=4,
            lookup=None,
        )

        assert result["total_upcoming_activities"] == len(result["activities"])


# ═══════════════════════════════════════════════════════════════════════════════
# ERROR AND EDGE CASE TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestErrorAndEdgeCases:
    """Tests for error scenarios and edge cases."""

    def test_empty_timetable(self):
        """Test handling empty timetable."""
        empty_timetable: list[dict] = []
        given_dt = datetime(2026, 3, 23, 9, 0)

        result = activity_checker.get_upcoming_activities(
            timetable=empty_timetable,
            given_dt=given_dt,
            lookahead_hours=4,
            lookup=None,
        )

        assert result["total_upcoming_activities"] == 0
        assert result["activities"] == []

    def test_no_tasks_for_day(self):
        """Test when timetable has no tasks for the queried day."""
        # Timetable only has Monday, query for Wednesday
        timetable = [
            {
                "day": "Monday",
                "tasks": [
                    {
                        "task": "Count",
                        "start_time": "08:00:00",
                        "end_time": "09:00:00",
                        "keywords": "Count |",
                        "statuses": {},
                    }
                ],
            }
        ]

        # Wednesday
        given_dt = datetime(2026, 3, 25, 9, 0)

        result = activity_checker.get_upcoming_activities(
            timetable=timetable,
            given_dt=given_dt,
            lookahead_hours=4,
            lookup=None,
        )

        assert result["total_upcoming_activities"] == 0

    def test_empty_cached_records_dataframe(self, sample_timetable: list[dict]):
        """Test with explicitly empty DataFrame."""
        cached_records = pd.DataFrame(columns=[
            "date_added", "Status_Keyword", "keyword_name",
            "tag_status_name", "tag_status_ids"
        ])
        given_dt = datetime(2026, 3, 23, 9, 0)

        result = activity_checker.get_missed_activities(
            timetable=sample_timetable,
            cached_records=cached_records,
            given_dt=given_dt,
            lookback_hours=-6,
            tolerance_minutes=0,
            lookup=None,
        )

        # All scheduled tasks should be missed
        assert result["total_missed_activities"] > 0

    def test_task_with_empty_keywords_and_statuses(self):
        """Test task with both empty keywords and statuses."""
        record = {
            "Status_Keyword": "Keyword",
            "keyword_name": "Something |",
        }
        task = {
            "keywords": "",
            "statuses": {},
        }

        # Should not match - no keywords or statuses to match against
        assert activity_checker.record_matches_task(record, task) is False

    def test_very_long_time_range(self):
        """Test handling very long time ranges (48 hours)."""
        timetable = [
            {
                "day": "Monday",
                "tasks": [
                    {
                        "task": "Daily Count",
                        "start_time": "08:00:00",
                        "end_time": "09:00:00",
                        "keywords": "Count |",
                        "statuses": {},
                    }
                ],
            },
            {
                "day": "Tuesday",
                "tasks": [
                    {
                        "task": "Daily Count",
                        "start_time": "08:00:00",
                        "end_time": "09:00:00",
                        "keywords": "Count |",
                        "statuses": {},
                    }
                ],
            },
        ]

        # Monday 00:00 to Wednesday 00:00 (48 hours)
        start_dt = datetime(2026, 3, 23, 0, 0)   # Monday
        end_dt = datetime(2026, 3, 25, 0, 0)     # Wednesday

        tasks = activity_checker.get_tasks_in_range(timetable, start_dt, end_dt)

        # Should find tasks from both Monday and Tuesday
        assert len(tasks) == 2

    def test_same_task_different_days_not_duplicated(self):
        """Test same task on different days are properly distinguished."""
        timetable = [
            {
                "day": "Monday",
                "tasks": [
                    {
                        "task": "Daily Count",
                        "start_time": "08:00:00",
                        "end_time": "09:00:00",
                        "keywords": "Count |",
                        "statuses": {},
                    }
                ],
            },
            {
                "day": "Tuesday",
                "tasks": [
                    {
                        "task": "Daily Count",  # Same name
                        "start_time": "08:00:00",
                        "end_time": "09:00:00",
                        "keywords": "Count |",
                        "statuses": {},
                    }
                ],
            },
        ]

        start_dt = datetime(2026, 3, 23, 0, 0)   # Monday
        end_dt = datetime(2026, 3, 25, 0, 0)     # Wednesday

        tasks = activity_checker.get_tasks_in_range(timetable, start_dt, end_dt)

        # Both should be present with different start datetimes
        assert len(tasks) == 2
        start_times = [t["task_start_dt"] for t in tasks]
        assert start_times[0] != start_times[1]

    def test_overlapping_tasks_same_time(self, sample_timetable: list[dict]):
        """Test handling of overlapping tasks (Pill Call and Chow Call overlap)."""
        # Both start around 05:00 - should both be detected
        start_dt = datetime(2026, 3, 23, 4, 30)
        end_dt = datetime(2026, 3, 23, 5, 30)

        tasks = activity_checker.get_tasks_in_range(sample_timetable, start_dt, end_dt)

        task_names = [t["task"] for t in tasks]
        assert "Pill Call" in task_names
        assert "Chow Call" in task_names


# ═══════════════════════════════════════════════════════════════════════════════
# DAY OF WEEK TRANSITION TESTS
# ═══════════════════════════════════════════════════════════════════════════════


class TestDayOfWeekTransitions:
    """Tests for day of week calculations and transitions."""

    def test_correct_day_name_monday(self):
        """Test Monday is correctly identified."""
        dt = datetime(2026, 3, 23, 10, 0)  # March 23, 2026 is Monday
        assert dt.strftime("%A") == "Monday"

    def test_correct_day_name_sunday(self):
        """Test Sunday is correctly identified."""
        dt = datetime(2026, 3, 29, 10, 0)  # March 29, 2026 is Sunday
        assert dt.strftime("%A") == "Sunday"

    def test_week_boundary_saturday_to_sunday(
        self, timetable_with_midnight_crossing: list[dict]
    ):
        """Test tasks spanning Saturday to Sunday are found."""
        # Saturday 23:00 to Sunday 03:00
        start_dt = datetime(2026, 3, 28, 23, 0)
        end_dt = datetime(2026, 3, 29, 3, 0)

        tasks = activity_checker.get_tasks_in_range(
            timetable_with_midnight_crossing, start_dt, end_dt
        )

        task_names = [t["task"] for t in tasks]
        # Should find Saturday's late night task
        assert "Late Night Watch" in task_names

    def test_previous_day_midnight_task_included(
        self, timetable_with_midnight_crossing: list[dict]
    ):
        """Test that previous day's midnight-crossing task is included when it extends into range."""
        # Query Saturday 00:00 to 02:00
        # Should include Friday's midnight-crossing tasks that extend into Saturday
        start_dt = datetime(2026, 3, 28, 0, 0)
        end_dt = datetime(2026, 3, 28, 2, 0)

        tasks = activity_checker.get_tasks_in_range(
            timetable_with_midnight_crossing, start_dt, end_dt
        )

        task_names = [t["task"] for t in tasks]
        # Friday's Night Count (23:00-00:30) extends into Saturday
        assert "Night Count" in task_names


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
