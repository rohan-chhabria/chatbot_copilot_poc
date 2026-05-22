"""Unit tests for the Activity Checker module."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from src.pipelines.daily_activity import activity_checker


class TestTimeHelpers:
    """Tests for time parsing and formatting helpers."""

    def test_parse_time_to_timedelta(self):
        """Test parsing time strings to timedelta."""
        result = activity_checker.parse_time_to_timedelta("03:00:00")
        assert result == timedelta(hours=3, minutes=0, seconds=0)

        result = activity_checker.parse_time_to_timedelta("14:30:45")
        assert result == timedelta(hours=14, minutes=30, seconds=45)

    def test_parse_time_without_seconds(self):
        """Test parsing time strings without seconds."""
        result = activity_checker.parse_time_to_timedelta("03:00")
        assert result == timedelta(hours=3, minutes=0, seconds=0)

    def test_format_time(self):
        """Test formatting datetime to HH:MM."""
        dt = datetime(2026, 3, 20, 14, 30, 45)
        assert activity_checker.format_time(dt) == "14:30"

    def test_format_datetime(self):
        """Test formatting datetime to MM-DD-YYYY HH:MM."""
        dt = datetime(2026, 3, 20, 14, 30)
        assert activity_checker.format_datetime(dt) == "03-20-2026 14:30"

    def test_calculate_time_range_lookback(self):
        """Test calculating time range for lookback."""
        given_dt = datetime(2026, 3, 20, 10, 0)
        start_dt, end_dt = activity_checker.calculate_time_range(given_dt, -8)

        assert start_dt == datetime(2026, 3, 20, 2, 0)
        assert end_dt == given_dt

    def test_calculate_time_range_lookahead(self):
        """Test calculating time range for lookahead."""
        given_dt = datetime(2026, 3, 20, 10, 0)
        start_dt, end_dt = activity_checker.calculate_time_range(given_dt, 4)

        assert start_dt == given_dt
        assert end_dt == datetime(2026, 3, 20, 14, 0)


class TestGetTasksInRange:
    """Tests for get_tasks_in_range function."""

    def test_get_tasks_in_range_basic(self, sample_timetable: list[dict]):
        """Test getting tasks in a basic time range."""
        start_dt = datetime(2026, 3, 23, 3, 0)  # Monday
        end_dt = datetime(2026, 3, 23, 6, 0)

        tasks = activity_checker.get_tasks_in_range(sample_timetable, start_dt, end_dt)

        assert len(tasks) >= 2
        task_names = [t["task"] for t in tasks]
        assert "Count-Official" in task_names
        assert "Pill Call" in task_names

    def test_get_tasks_in_range_empty(self, sample_timetable: list[dict]):
        """Test getting tasks when none are scheduled."""
        start_dt = datetime(2026, 3, 23, 20, 0)  # Monday evening
        end_dt = datetime(2026, 3, 23, 22, 0)

        tasks = activity_checker.get_tasks_in_range(sample_timetable, start_dt, end_dt)
        assert len(tasks) == 0

    def test_get_tasks_sorted_chronologically(self, sample_timetable: list[dict]):
        """Test that tasks are sorted by start time."""
        start_dt = datetime(2026, 3, 23, 3, 0)  # Monday
        end_dt = datetime(2026, 3, 23, 12, 0)

        tasks = activity_checker.get_tasks_in_range(sample_timetable, start_dt, end_dt)

        start_times = [t["task_start_dt"] for t in tasks]
        assert start_times == sorted(start_times)


class TestParseKeywords:
    """Tests for keyword parsing."""

    def test_parse_task_keywords(self):
        """Test parsing comma-separated keywords."""
        result = activity_checker.parse_task_keywords("Official Count |, Roll Call |")
        assert result == ["Official Count |", "Roll Call |"]

    def test_parse_empty_keywords(self):
        """Test parsing empty keywords string."""
        assert activity_checker.parse_task_keywords("") == []
        assert activity_checker.parse_task_keywords(None) == []


class TestRecordMatchesTask:
    """Tests for record-task matching logic."""

    def test_record_matches_keyword(self):
        """Test matching record to task by keyword."""
        record = {
            "Status_Keyword": "Keyword",
            "keyword_name": "Official Count |",
        }
        task = {
            "keywords": "Official Count |, Roll Call |",
            "statuses": {},
        }

        assert activity_checker.record_matches_task(record, task) is True

    def test_record_no_match_keyword(self):
        """Test non-matching keyword."""
        record = {
            "Status_Keyword": "Keyword",
            "keyword_name": "Chow |",
        }
        task = {
            "keywords": "Official Count |, Roll Call |",
            "statuses": {},
        }

        assert activity_checker.record_matches_task(record, task) is False

    def test_record_matches_status(self):
        """Test matching record to task by status."""
        record = {
            "Status_Keyword": "Status",
            "tag_status_name": "Fire Watch",
            "tag_status_ids": "",
        }
        task = {
            "keywords": "",
            "statuses": {"Fire Watch": []},
        }

        assert activity_checker.record_matches_task(record, task) is True


class TestCategorizeTask:
    """Tests for task categorization."""

    def test_categorize_count(self):
        """Test categorizing count-related tasks."""
        assert activity_checker.categorize_task("Count-Official") == "Count"
        assert activity_checker.categorize_task("Roll Count") == "Count"

    def test_categorize_program(self):
        """Test categorizing program-related tasks."""
        assert activity_checker.categorize_task("1st Block/Program") == "Program"

    def test_categorize_medical(self):
        """Test categorizing medical-related tasks."""
        assert activity_checker.categorize_task("Pill Call") == "Medical"
        assert activity_checker.categorize_task("Insulin Distribution") == "Medical"

    def test_categorize_meal(self):
        """Test categorizing meal-related tasks."""
        assert activity_checker.categorize_task("Chow Call") == "Meal/Kitchen"

    def test_categorize_recreation(self):
        """Test categorizing recreation-related tasks."""
        assert activity_checker.categorize_task("Recreation") == "Recreation"
        assert activity_checker.categorize_task("Yard Time") == "Recreation"

    def test_categorize_other(self):
        """Test categorizing unknown tasks."""
        assert activity_checker.categorize_task("Unknown Task") == "Other"


class TestBuildEmptySections:
    """Tests for empty section builders."""

    def test_build_empty_missed_section(self):
        """Test building empty missed section."""
        result = activity_checker._build_empty_missed_section()

        assert result["period"] is None
        assert result["total_missed_activities"] == 0
        assert result["activities"] == []
        assert result["activities_by_type"] == {}

    def test_build_empty_upcoming_section(self):
        """Test building empty upcoming section."""
        result = activity_checker._build_empty_upcoming_section()

        assert result["period"] is None
        assert result["total_upcoming_activities"] == 0
        assert result["activities"] == []
        assert result["activities_by_type"] == {}


class TestGetMissedActivities:
    """Tests for get_missed_activities function."""

    def test_missed_with_no_records(self, sample_timetable: list[dict]):
        """Test detecting missed activities when no DB records exist."""
        cached_records = pd.DataFrame()
        given_dt = datetime(2026, 3, 23, 9, 30)  # Monday

        result = activity_checker.get_missed_activities(
            timetable=sample_timetable,
            cached_records=cached_records,
            given_dt=given_dt,
            lookback_hours=-8,
            tolerance_minutes=0,
            lookup=None,
        )

        assert result["total_missed_activities"] > 0
        assert len(result["activities"]) > 0

    def test_missed_with_zero_lookback(self, sample_timetable: list[dict]):
        """Test with zero lookback hours returns empty."""
        cached_records = pd.DataFrame()
        given_dt = datetime(2026, 3, 23, 9, 30)

        result = activity_checker.get_missed_activities(
            timetable=sample_timetable,
            cached_records=cached_records,
            given_dt=given_dt,
            lookback_hours=0,
            tolerance_minutes=0,
            lookup=None,
        )

        assert result["total_missed_activities"] == 0


class TestGetUpcomingActivities:
    """Tests for get_upcoming_activities function."""

    def test_upcoming_activities(self, sample_timetable: list[dict]):
        """Test getting upcoming activities."""
        given_dt = datetime(2026, 3, 23, 9, 30)  # Monday

        result = activity_checker.get_upcoming_activities(
            timetable=sample_timetable,
            given_dt=given_dt,
            lookahead_hours=4,
            lookup=None,
        )

        assert result["total_upcoming_activities"] >= 1
        assert "period" in result
        assert result["period"]["start"] is not None

    def test_upcoming_with_zero_lookahead(self, sample_timetable: list[dict]):
        """Test with zero lookahead hours returns empty."""
        given_dt = datetime(2026, 3, 23, 9, 30)

        result = activity_checker.get_upcoming_activities(
            timetable=sample_timetable,
            given_dt=given_dt,
            lookahead_hours=0,
            lookup=None,
        )

        assert result["total_upcoming_activities"] == 0
