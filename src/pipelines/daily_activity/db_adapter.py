"""
DB Adapter for Daily Activity Pipeline.

Uses the chatbot's db_registry for multi-tenant database access.
Provides functions to fetch activity records and keyword/status lookups.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from src.shared.logger import get_logger
from src.tenant.db_registry import execute_procedure, execute_query
from src.tenant.tenant_router import TenantContext

logger = get_logger(__name__)


def _post_process(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and normalize DataFrame from DB results.

    - Converts date_added to datetime
    - Fills NaN values in string columns
    - Converts numeric columns to int
    """
    if df.empty:
        return df

    if "date_added" in df.columns:
        df["date_added"] = pd.to_datetime(df["date_added"])

    for col in ["tag_status_name", "tag_status_ids", "keyword_name", "Status_Keyword"]:
        if col in df.columns:
            df[col] = df[col].fillna("")

    for col in ["customer_key", "facilities_id", "notes_id", "keyword_id", "tag_status_id"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    return df


def get_records(
    tenant: TenantContext,
    facility_id: int,
    start_dt: datetime,
    end_dt: datetime,
) -> pd.DataFrame:
    """
    Get activity records within time range for a facility using stored procedure.

    Calls SP: p_ai_status_activenote_data with parameters:
        (start_dt, end_dt, customer_key, active_customer_id, facilities_ids, tag_status_ids, keyword_ids)

    Args:
        tenant: Tenant context with DB connection info
        facility_id: Facility ID to filter by
        start_dt: Start of time range
        end_dt: End of time range

    Returns:
        DataFrame with activity records
    """
    start_str = start_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_str = end_dt.strftime("%Y-%m-%d %H:%M:%S")
    facility_str = str(facility_id) if facility_id else ""

    logger.debug(
        "Fetching records for facility=%s from %s to %s",
        facility_id,
        start_str,
        end_str,
    )

    params = [
        start_str,              # n_note_date_from
        end_str,                # n_note_date_to
        tenant.customer_key,    # n_customer_key
        "",                     # n_active_customer_id (not used)
        facility_str,           # n_facilities_ids
        "",                     # n_tag_status_ids
        "",                     # n_keyword_ids
    ]

    try:
        rows = execute_procedure(tenant, "p_ai_status_activenote_data", params)
        df = pd.DataFrame(rows)
        logger.debug("Fetched %d records for facility=%s", len(df), facility_id)
        return _post_process(df)
    except Exception as e:
        logger.error("Failed to fetch records for facility=%s: %s", facility_id, str(e))
        raise


def get_keyword_status_lookup(
    tenant: TenantContext,
    facility_id: int,
) -> dict[str, dict[str, int]]:
    """
    Get keyword_name -> keyword_id and tag_status_name -> tag_status_id mappings.

    Uses UNION ALL query to fetch all keywords and statuses for the given
    customer_key and facility_id in a single efficient query.

    Args:
        tenant: Tenant context with DB connection info
        facility_id: Facility ID for filtering

    Returns:
        Dict with structure:
        {
            "keywords": {"keyword_name": keyword_id, ...},
            "statuses": {"status_name": tag_status_id, ...}
        }
    """
    sql = f"""
        SELECT keyword_id, keyword_name, tag_status_id, tag_status_name
        FROM (
            SELECT
                k.keyword_id    AS keyword_id,
                k.keyword_name  AS keyword_name,
                NULL            AS tag_status_id,
                NULL            AS tag_status_name
            FROM dg_keyword k
            WHERE k.customer_key = '{tenant.customer_key}'
              AND FIND_IN_SET('{facility_id}', k.facilities_id) > 0

            UNION ALL

            SELECT
                NULL            AS keyword_id,
                NULL            AS keyword_name,
                ts.tag_status_id,
                ts.name         AS tag_status_name
            FROM dg_tag_status ts
            WHERE ts.customer_key = '{tenant.customer_key}'
              AND FIND_IN_SET('{facility_id}', ts.facilities_id) > 0
        ) t
        ORDER BY keyword_id IS NOT NULL DESC, keyword_id, tag_status_id
    """

    keyword_lookup: dict[str, int] = {}
    status_lookup: dict[str, int] = {}

    try:
        rows = execute_query(tenant, sql, limit=10000)

        for row in rows:
            if row.get("keyword_id") is not None and row.get("keyword_name"):
                keyword_lookup[row["keyword_name"]] = int(row["keyword_id"])
            if row.get("tag_status_id") is not None and row.get("tag_status_name"):
                status_lookup[row["tag_status_name"]] = int(row["tag_status_id"])

        logger.debug(
            "Built lookup for facility=%s: %d keywords, %d statuses",
            facility_id,
            len(keyword_lookup),
            len(status_lookup),
        )
    except Exception as e:
        logger.error("Failed to build lookup for facility=%s: %s", facility_id, str(e))

    return {
        "keywords": keyword_lookup,
        "statuses": status_lookup,
    }
