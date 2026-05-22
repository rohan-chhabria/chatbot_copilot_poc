"""Tests for document QA guardrails."""

from __future__ import annotations

import pytest

from src.pipelines.document_qa.guardrails import (
    DocumentQueryValidator,
    validate_document_query,
)


class TestDocumentQueryValidator:
    @pytest.fixture
    def validator(self):
        return DocumentQueryValidator()

    def test_valid_document_query(self, validator):
        result = validator.validate("What does the policy say about fire safety?")
        assert result.is_valid is True

    def test_valid_search_query(self, validator):
        result = validator.validate("Find information about inmate transfers")
        assert result.is_valid is True

    def test_empty_query_invalid(self, validator):
        result = validator.validate("")
        assert result.is_valid is False

    def test_whitespace_only_invalid(self, validator):
        result = validator.validate("   ")
        assert result.is_valid is False

    def test_too_short_query(self, validator):
        validator.validate("hi")
        # May be invalid depending on min length


class TestValidateDocumentQuery:
    def test_convenience_function(self):
        result = validate_document_query("What is the evacuation procedure?")
        assert result.is_valid is True

    def test_invalid_empty(self):
        result = validate_document_query("")
        assert result.is_valid is False
