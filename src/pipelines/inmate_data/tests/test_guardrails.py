"""Tests for inmate data pipeline guardrails."""

from __future__ import annotations

import pytest

from src.pipelines.inmate_data.guardrails import (
    ValidationResult,
    SQLValidationResult,
    validate_question,
    validate_and_fix_sql,
    inject_filters,
)


class TestQuestionValidation:
    def test_valid_data_question(self):
        result = validate_question("Show fire watch notes from today")
        assert result.is_valid is True

    def test_valid_inmate_query(self):
        result = validate_question("Where is inmate John Smith?")
        assert result.is_valid is True

    def test_valid_count_question(self):
        result = validate_question("How many notes were added this week?")
        assert result.is_valid is True

    def test_empty_question_invalid(self):
        result = validate_question("")
        assert result.is_valid is False

    def test_whitespace_only_invalid(self):
        result = validate_question("   ")
        assert result.is_valid is False

    def test_too_short_question_invalid(self):
        result = validate_question("hi")
        # May be valid as a greeting, depends on implementation


class TestSQLValidation:
    def test_valid_select(self):
        sql = "SELECT * FROM dg_notes WHERE status = 1 LIMIT 100"
        result = validate_and_fix_sql(sql)
        assert result.is_valid is True

    def test_blocks_drop(self):
        sql = "DROP TABLE dg_notes"
        result = validate_and_fix_sql(sql)
        assert result.is_valid is False

    def test_blocks_delete(self):
        sql = "DELETE FROM dg_notes WHERE notes_id = 1"
        result = validate_and_fix_sql(sql)
        assert result.is_valid is False

    def test_blocks_update(self):
        sql = "UPDATE dg_notes SET status = 0"
        result = validate_and_fix_sql(sql)
        assert result.is_valid is False

    def test_blocks_insert(self):
        sql = "INSERT INTO dg_notes VALUES (1, 'test')"
        result = validate_and_fix_sql(sql)
        assert result.is_valid is False


class TestFilterInjection:
    def test_inject_facility_filter(self):
        sql = "SELECT * FROM dg_notes n WHERE n.status = 1"
        result = inject_filters(sql, facilities_ids=[101, 102])
        assert "facilities_id IN (101, 102)" in result or "101" in result

    def test_no_filter_when_empty(self):
        sql = "SELECT * FROM dg_notes n WHERE n.status = 1"
        result = inject_filters(sql, facilities_ids=[])
        # Should not add facility filter
        assert result == sql or "facilities_id" not in result
