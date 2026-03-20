"""
SQL Validator — Security checks and syntax fixes for generated SQL.

Ensures all generated SQL is safe, read-only, and respects data access policies.
Applies mandatory status filters and facility-level data isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.shared.constants import (
    DANGEROUS_SQL_KEYWORDS,
    SCHEMA_PATTERNS,
    SCHEMA_REGEX_PATTERNS,
    SENSITIVE_COLUMNS,
    STATUS_FILTER_TABLES,
)


@dataclass(frozen=True)
class SQLValidationResult:
    is_valid: bool
    sql: str = ""
    error: str = ""


def validate_and_fix_sql(sql: str) -> SQLValidationResult:
    if not sql or not sql.strip():
        return SQLValidationResult(is_valid=False, error="Empty SQL generated.")

    cleaned = _clean_sql(sql)

    security = _check_security(cleaned)
    if not security.is_valid:
        return security

    schema = _check_schema_access(cleaned)
    if not schema.is_valid:
        return schema

    sensitive = _check_sensitive_columns(cleaned)
    if not sensitive.is_valid:
        return sensitive

    fixed = _fix_syntax(cleaned)
    fixed = _remove_select_star_wrapper(fixed)

    if not _has_balanced_parens(fixed):
        return SQLValidationResult(is_valid=False, error="Unbalanced parentheses in SQL.")

    return SQLValidationResult(is_valid=True, sql=fixed)


def inject_filters(
    sql: str,
    facilities_ids: list[int] | None = None,
) -> str:
    result = _inject_status_filters(sql)

    if facilities_ids:
        result = _inject_facility_filter(result, facilities_ids)

    return result


def _clean_sql(sql: str) -> str:
    text = sql.strip()
    for prefix in ("```sql", "```mysql", "```", "sql", "SQL"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    if text.endswith(";"):
        text = text[:-1].strip()
    return text


def _check_security(sql: str) -> SQLValidationResult:
    upper = sql.upper()

    if not (upper.lstrip().startswith("SELECT") or upper.lstrip().startswith("WITH")):
        return SQLValidationResult(
            is_valid=False, error="Only SELECT queries are allowed."
        )

    for keyword in DANGEROUS_SQL_KEYWORDS:
        pattern = rf"\b{keyword}\b"
        if re.search(pattern, upper):
            return SQLValidationResult(
                is_valid=False, error=f"Prohibited SQL keyword: {keyword}"
            )

    return SQLValidationResult(is_valid=True, sql=sql)


def _check_schema_access(sql: str) -> SQLValidationResult:
    lower = sql.lower()
    for pattern in SCHEMA_PATTERNS:
        if pattern.lower() in lower:
            return SQLValidationResult(
                is_valid=False, error="Schema/metadata queries are not allowed."
            )
    for rx in SCHEMA_REGEX_PATTERNS:
        if re.search(rx, sql, re.IGNORECASE):
            return SQLValidationResult(
                is_valid=False, error="Schema/metadata queries are not allowed."
            )
    return SQLValidationResult(is_valid=True, sql=sql)


def _check_sensitive_columns(sql: str) -> SQLValidationResult:
    select_match = re.match(r"(?i)(SELECT\s+)(.*?)(\s+FROM\s+)", sql, re.DOTALL)
    if not select_match:
        return SQLValidationResult(is_valid=True, sql=sql)

    select_clause = select_match.group(2).lower()
    for col in SENSITIVE_COLUMNS:
        if re.search(rf"\b{col}\b", select_clause):
            return SQLValidationResult(
                is_valid=False, error=f"Sensitive column not allowed in SELECT: {col}"
            )

    return SQLValidationResult(is_valid=True, sql=sql)


def _fix_syntax(sql: str) -> str:
    sql = _fix_regexp_to_like(sql)
    sql = re.sub(r"\s+", " ", sql).strip()
    return sql


def _fix_regexp_to_like(sql: str) -> str:
    def _replace(match: re.Match) -> str:
        col = match.group(1)
        pattern = match.group(2)
        clean = pattern.strip("'^$.*")
        return f"{col} LIKE '%{clean}%'"

    return re.sub(
        r"(\w+)\s+REGEXP\s+'([^']+)'",
        _replace,
        sql,
        flags=re.IGNORECASE,
    )


def _remove_select_star_wrapper(sql: str) -> str:
    match = re.match(
        r"(?i)^SELECT\s+\*\s+FROM\s*\(\s*(SELECT\s+.+)\s*\)\s*(?:AS\s+\w+)?$",
        sql,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return sql


def _has_balanced_parens(sql: str) -> bool:
    depth = 0
    for char in sql:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if depth < 0:
            return False
    return depth == 0


def _inject_status_filters(sql: str) -> str:
    lower = sql.lower()
    result = sql

    for table, filter_clause in STATUS_FILTER_TABLES.items():
        alias = filter_clause.split(".")[0]
        table_pattern = rf"\b{table}\b\s+(?:AS\s+)?{alias}\b"

        if re.search(table_pattern, lower, re.IGNORECASE):
            if filter_clause.lower() not in lower:
                left_join_pattern = rf"LEFT\s+(?:OUTER\s+)?JOIN\s+{table}\b"
                if re.search(left_join_pattern, lower, re.IGNORECASE):
                    continue
                result = _append_where_condition(result, filter_clause)

    return result


def _inject_facility_filter(sql: str, facilities_ids: list[int]) -> str:
    if not facilities_ids:
        return sql

    lower = sql.lower()

    if re.search(r"facilities_id\s+in\s*\(", lower, re.IGNORECASE):
        return sql

    has_notes = bool(re.search(r"\bdg_notes\b\s+(?:AS\s+)?n\b", lower, re.IGNORECASE))
    has_movement = bool(re.search(r"\bdg_tags_movement\b", lower, re.IGNORECASE))
    has_tags_direct = bool(re.search(r"\bdg_tags\b\s+(?:AS\s+)?t\b", lower, re.IGNORECASE))

    if has_movement:
        return sql

    if has_tags_direct and not has_notes:
        return sql

    if not has_notes:
        return sql

    _CROSS_FACILITY_SIGNALS = [
        "logged into", "logged in", "login",
        "all facilities", "cross facility",
    ]
    if any(sig in lower for sig in _CROSS_FACILITY_SIGNALS):
        return sql

    ids_str = ", ".join(str(fid) for fid in facilities_ids)
    filter_clause = f"n.facilities_id IN ({ids_str})"
    return _append_where_condition(sql, filter_clause)


def _append_where_condition(sql: str, condition: str) -> str:
    upper = sql.upper()

    group_pos = _find_keyword_position(upper, "GROUP BY")
    order_pos = _find_keyword_position(upper, "ORDER BY")
    limit_pos = _find_keyword_position(upper, "LIMIT")
    having_pos = _find_keyword_position(upper, "HAVING")

    insert_pos = len(sql)
    for pos in [group_pos, order_pos, limit_pos, having_pos]:
        if pos != -1 and pos < insert_pos:
            insert_pos = pos

    where_pos = _find_keyword_position(upper, "WHERE")

    if where_pos != -1:
        return f"{sql[:insert_pos]} AND {condition} {sql[insert_pos:]}"

    return f"{sql[:insert_pos]} WHERE {condition} {sql[insert_pos:]}"


def _find_keyword_position(sql_upper: str, keyword: str) -> int:
    pattern = rf"\b{keyword}\b"
    match = re.search(pattern, sql_upper)
    return match.start() if match else -1
