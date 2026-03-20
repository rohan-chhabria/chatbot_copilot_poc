"""
Facility Tool — Pre-built queries for facility-level summaries and officer activity.

Provides quick snapshot queries for facility operations, officer performance,
and inmate status distribution.
"""

from __future__ import annotations

from typing import Any

from src.shared.logger import get_logger
from src.tenant.db_registry import execute_query
from src.tenant.tenant_router import TenantContext

logger = get_logger(__name__)


FACILITY_SUMMARY_SQL = """
SELECT
    f.facilities_id,
    f.facility AS facility_name,
    COUNT(DISTINCT n.notes_id) AS note_count,
    COUNT(DISTINCT n.user_id) AS active_officers,
    COUNT(DISTINCT ntg.tags_id) AS unique_inmates,
    MIN(n.date_added) AS earliest_note,
    MAX(n.date_added) AS latest_note
FROM dg_facilities f
LEFT JOIN dg_notes n ON f.facilities_id = n.facilities_id AND n.status = 1
    AND n.date_added >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
LEFT JOIN dg_notes_tags ntg ON n.notes_id = ntg.notes_id
WHERE f.status = 1
    {facility_filter}
GROUP BY f.facilities_id, f.facility
HAVING note_count > 0
ORDER BY note_count DESC
"""

OFFICER_ACTIVITY_SQL = """
SELECT
    n.user_id AS officer,
    f.facility AS facility_name,
    COUNT(DISTINCT n.notes_id) AS note_count,
    COUNT(DISTINCT ntg.tags_id) AS inmates_tagged,
    COUNT(DISTINCT DATE(n.note_date)) AS active_days,
    MAX(n.date_added) AS last_activity
FROM dg_notes n
INNER JOIN dg_facilities f ON n.facilities_id = f.facilities_id AND f.status = 1
LEFT JOIN dg_notes_tags ntg ON n.notes_id = ntg.notes_id
WHERE n.status = 1
    AND n.user_id != 'System Generated'
    AND n.date_added >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
    {facility_filter}
GROUP BY n.user_id, f.facility
ORDER BY note_count DESC
LIMIT 50
"""

INMATE_STATUS_SQL = """
SELECT
    ts.name AS status_name,
    COUNT(DISTINCT t.tags_id) AS inmate_count,
    f.facility AS facility_name
FROM dg_tags t
INNER JOIN dg_tag_status ts ON t.role_call = ts.tag_status_id AND ts.status = 1
INNER JOIN dg_facilities f ON t.facilities_id = f.facilities_id AND f.status = 1
WHERE t.status = 1
    {facility_filter}
GROUP BY ts.name, f.facility
ORDER BY inmate_count DESC
"""

KEYWORD_TREND_SQL = """
SELECT
    DATE(knw.date_added) AS report_date,
    knw.keyword_name,
    COUNT(*) AS entry_count
FROM dg_notes_by_keyword knw
INNER JOIN dg_notes n ON knw.notes_id = n.notes_id AND n.status = 1
WHERE knw.date_added >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
    {facility_filter}
GROUP BY DATE(knw.date_added), knw.keyword_name
ORDER BY report_date DESC, entry_count DESC
"""


def get_facility_summary(
    tenant: TenantContext,
    days: int = 7,
    facility_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    sql = _build_sql(FACILITY_SUMMARY_SQL, days, facility_ids)
    return execute_query(tenant, sql)


def get_officer_activity(
    tenant: TenantContext,
    days: int = 7,
    facility_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    sql = _build_sql(OFFICER_ACTIVITY_SQL, days, facility_ids)
    return execute_query(tenant, sql)


def get_inmate_status_distribution(
    tenant: TenantContext,
    facility_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    sql = _build_sql(INMATE_STATUS_SQL, 0, facility_ids)
    return execute_query(tenant, sql)


def get_keyword_trends(
    tenant: TenantContext,
    days: int = 14,
    facility_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    sql = _build_sql(KEYWORD_TREND_SQL, days, facility_ids)
    return execute_query(tenant, sql)


def _build_sql(template: str, days: int, facility_ids: list[int] | None) -> str:
    sql = template.replace(":days", str(max(days, 1)))

    if facility_ids:
        ids_str = ", ".join(str(fid) for fid in facility_ids)
        facility_clause = f"AND n.facilities_id IN ({ids_str})"
        tag_clause = f"AND t.facilities_id IN ({ids_str})"
        if "dg_tags t" in template:
            sql = sql.replace("{facility_filter}", tag_clause)
        else:
            sql = sql.replace("{facility_filter}", facility_clause)
    else:
        sql = sql.replace("{facility_filter}", "")

    return sql
