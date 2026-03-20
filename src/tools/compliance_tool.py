"""
Compliance Tool — Pre-built queries for compliance monitoring.

Provides structured SQL queries for 30-minute rounds, Fire Watch,
Suicide Watch, and bed check compliance metrics.
"""

from __future__ import annotations

from typing import Any

from src.shared.logger import get_logger
from src.tenant.db_registry import execute_query
from src.tenant.tenant_router import TenantContext

logger = get_logger(__name__)


ROUND_COMPLIANCE_SQL = """
SELECT
    f.facility AS facility_name,
    knw.keyword_name,
    COUNT(DISTINCT knw.notes_by_keyword_id) AS total_entries,
    COUNT(DISTINCT DATE(knw.date_added)) AS active_days,
    MIN(knw.date_added) AS earliest_entry,
    MAX(knw.date_added) AS latest_entry
FROM dg_notes_by_keyword knw
INNER JOIN dg_notes n ON knw.notes_id = n.notes_id AND n.status = 1
INNER JOIN dg_facilities f ON n.facilities_id = f.facilities_id AND f.status = 1
WHERE knw.keyword_name IN ('Rounds', 'Fire Watch', 'Fire Watch I', 'Suicide Watch')
    AND knw.date_added >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
    {facility_filter}
GROUP BY f.facility, knw.keyword_name
ORDER BY f.facility, knw.keyword_name
"""

ROUND_GAP_SQL = """
SELECT
    f.facility AS facility_name,
    knw.keyword_name,
    knw.date_added AS check_time,
    TIMESTAMPDIFF(
        MINUTE,
        LAG(knw.date_added) OVER (
            PARTITION BY n.facilities_id, knw.keyword_name
            ORDER BY knw.date_added
        ),
        knw.date_added
    ) AS gap_minutes
FROM dg_notes_by_keyword knw
INNER JOIN dg_notes n ON knw.notes_id = n.notes_id AND n.status = 1
INNER JOIN dg_facilities f ON n.facilities_id = f.facilities_id AND f.status = 1
WHERE knw.keyword_name IN ('Rounds', 'Fire Watch', 'Fire Watch I', 'Suicide Watch')
    AND knw.date_added >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
    {facility_filter}
HAVING gap_minutes > 35
ORDER BY gap_minutes DESC
LIMIT 100
"""

REFUSAL_SUMMARY_SQL = """
SELECT
    f.facility AS facility_name,
    COUNT(*) AS refusal_count,
    COUNT(DISTINCT ntg.tags_id) AS unique_inmates,
    COUNT(DISTINCT n.user_id) AS officers_involved
FROM dg_notes_tags ntg
INNER JOIN dg_notes n ON ntg.notes_id = n.notes_id AND n.status = 1
INNER JOIN dg_facilities f ON n.facilities_id = f.facilities_id AND f.status = 1
WHERE ntg.refused_status_id = 278
    AND n.date_added >= DATE_SUB(CURDATE(), INTERVAL :days DAY)
    {facility_filter}
GROUP BY f.facility
ORDER BY refusal_count DESC
"""


def get_round_compliance(
    tenant: TenantContext,
    days: int = 7,
    facility_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    sql = _build_sql(ROUND_COMPLIANCE_SQL, days, facility_ids)
    return execute_query(tenant, sql)


def get_round_gaps(
    tenant: TenantContext,
    days: int = 7,
    facility_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    sql = _build_sql(ROUND_GAP_SQL, days, facility_ids)
    return execute_query(tenant, sql)


def get_refusal_summary(
    tenant: TenantContext,
    days: int = 7,
    facility_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    sql = _build_sql(REFUSAL_SUMMARY_SQL, days, facility_ids)
    return execute_query(tenant, sql)


def _build_sql(template: str, days: int, facility_ids: list[int] | None) -> str:
    sql = template.replace(":days", str(days))

    if facility_ids:
        ids_str = ", ".join(str(fid) for fid in facility_ids)
        sql = sql.replace("{facility_filter}", f"AND n.facilities_id IN ({ids_str})")
    else:
        sql = sql.replace("{facility_filter}", "")

    return sql
