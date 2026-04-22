"""
Question Validator — Input sanitization and relevance checking.

Validates user questions before they reach the SQL generation pipeline.
Checks for: injection attempts, domain relevance, length, and banned patterns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.shared.config import MAX_QUESTION_LENGTH, MIN_QUESTION_LENGTH
from src.shared.constants import (
    DOMAIN_KEYWORDS,
    IRRELEVANT_PATTERNS,
    QUERY_KEYWORDS,
    SCHEMA_PATTERNS,
    SQL_INJECTION_PATTERNS,
)


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    error: str = ""
    cleaned_question: str = ""


_LEET_MAP = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t"})


def validate_question(question: str) -> ValidationResult:
    if not question or not question.strip():
        return ValidationResult(is_valid=False, error="Question cannot be empty.")

    cleaned = _sanitize(question)

    length_check = _check_length(cleaned)
    if not length_check.is_valid:
        return length_check

    injection = _check_injection(cleaned)
    if not injection.is_valid:
        return injection

    schema = _check_schema_exposure(cleaned)
    if not schema.is_valid:
        return schema

    sensitive = _check_sensitive_data(cleaned)
    if not sensitive.is_valid:
        return sensitive

    irrelevant = _check_irrelevant(cleaned)
    if not irrelevant.is_valid:
        return irrelevant

    return ValidationResult(is_valid=True, cleaned_question=cleaned)


def _sanitize(question: str) -> str:
    text = question.strip()
    text = text.replace("\x00", "")
    text = re.sub(r"\s+", " ", text)
    return text


def _check_length(question: str) -> ValidationResult:
    if len(question) < MIN_QUESTION_LENGTH:
        return ValidationResult(
            is_valid=False,
            error=f"Question too short. Minimum {MIN_QUESTION_LENGTH} characters.",
        )
    if len(question) > MAX_QUESTION_LENGTH:
        return ValidationResult(
            is_valid=False,
            error=f"Question too long. Maximum {MAX_QUESTION_LENGTH} characters.",
        )
    return ValidationResult(is_valid=True, cleaned_question=question)


def _check_injection(question: str) -> ValidationResult:
    normalized = question.translate(_LEET_MAP).lower()

    for pattern in SQL_INJECTION_PATTERNS:
        if pattern.lower() in normalized:
            return ValidationResult(
                is_valid=False,
                error="Question contains disallowed patterns.",
            )

    if "' or " in normalized or "'or " in normalized or "='1" in normalized:
        return ValidationResult(
            is_valid=False,
            error="Question contains disallowed patterns.",
        )

    return ValidationResult(is_valid=True, cleaned_question=question)


def _check_schema_exposure(question: str) -> ValidationResult:
    lower = question.lower()
    for pattern in SCHEMA_PATTERNS:
        if pattern.lower() in lower:
            return ValidationResult(
                is_valid=False,
                error="Schema queries are not permitted.",
            )
    return ValidationResult(is_valid=True, cleaned_question=question)


def _check_sensitive_data(question: str) -> ValidationResult:
    lower = question.lower()
    sensitive_request_patterns = [
        "show me password", "get password", "list ssn",
        "show ssn", "get token", "show secret",
    ]
    for pattern in sensitive_request_patterns:
        if pattern in lower:
            return ValidationResult(
                is_valid=False,
                error="Requests for sensitive data are not permitted.",
            )
    return ValidationResult(is_valid=True, cleaned_question=question)


def _check_irrelevant(question: str) -> ValidationResult:
    import re as _re
    lower = question.lower()
    for pattern in IRRELEVANT_PATTERNS:
        if _re.search(r"\b" + _re.escape(pattern) + r"\b", lower):
            return ValidationResult(
                is_valid=False,
                error="Question is not related to inmate or facility operations.",
            )
    return ValidationResult(is_valid=True, cleaned_question=question)


def _check_domain_relevance(question: str) -> ValidationResult:
    lower = question.lower()
    words = set(re.findall(r"\w+", lower))

    has_domain = bool(words & DOMAIN_KEYWORDS)

    has_query = any(kw in lower for kw in QUERY_KEYWORDS)

    if has_domain or has_query:
        return ValidationResult(is_valid=True, cleaned_question=question)

    return ValidationResult(
        is_valid=False,
        error="Question doesn't appear related to inmate or facility operations. "
        "Try asking about notes, inmates, officers, facilities, or keywords.",
    )
