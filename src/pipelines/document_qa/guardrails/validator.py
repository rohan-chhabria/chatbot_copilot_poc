"""
Validator for Document QA queries.

Ensures questions are appropriate for document search.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationResult:
    """Result of query validation."""

    is_valid: bool
    error: str = ""
    cleaned_query: str = ""


class DocumentQueryValidator:
    """Validates document search queries."""

    MIN_QUERY_LENGTH = 3
    MAX_QUERY_LENGTH = 500

    def validate(self, query: str) -> ValidationResult:
        """Validate a document search query."""
        if not query or not query.strip():
            return ValidationResult(
                is_valid=False, error="Query cannot be empty."
            )

        cleaned = query.strip()

        if len(cleaned) < self.MIN_QUERY_LENGTH:
            return ValidationResult(
                is_valid=False,
                error=f"Query too short. Minimum {self.MIN_QUERY_LENGTH} characters.",
            )

        if len(cleaned) > self.MAX_QUERY_LENGTH:
            return ValidationResult(
                is_valid=False,
                error=f"Query too long. Maximum {self.MAX_QUERY_LENGTH} characters.",
            )

        return ValidationResult(is_valid=True, cleaned_query=cleaned)


def validate_document_query(query: str) -> ValidationResult:
    """Convenience function for query validation."""
    validator = DocumentQueryValidator()
    return validator.validate(query)
