"""
DB Registry — Connection pool management for multi-tenant Aurora MySQL.

Maintains one connection pool per tenant. All connections are READ-ONLY.
Pools are lazily created and cached for the lifetime of the process.
"""

from __future__ import annotations

import threading
from typing import Any

import pymysql

from src.shared.config import MAX_QUERY_RESULTS
from src.shared.logger import get_logger
from src.tenant.tenant_router import TenantContext

logger = get_logger(__name__)

_lock = threading.Lock()
_pools: dict[str, pymysql.Connection] = {}


def get_connection(tenant: TenantContext) -> pymysql.Connection:
    key = tenant.customer_key

    if key in _pools:
        conn = _pools[key]
        try:
            conn.ping(reconnect=True)
            return conn
        except Exception:
            logger.warning("Stale connection for tenant %s, reconnecting", key)
            _remove_connection(key)

    return _create_connection(tenant)


def _create_connection(tenant: TenantContext) -> pymysql.Connection:
    with _lock:
        if tenant.customer_key in _pools:
            return _pools[tenant.customer_key]

        logger.info(
            "Creating DB connection for tenant=%s host=%s db=%s",
            tenant.customer_key,
            tenant.db_host,
            tenant.db_name,
        )

        conn = pymysql.connect(
            host=tenant.db_host,
            user=tenant.db_user,
            password=tenant.db_password,
            database=tenant.db_name,
            port=tenant.db_port,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            read_timeout=30,
            autocommit=True,
        )

        _pools[tenant.customer_key] = conn
        return conn


def _remove_connection(key: str) -> None:
    with _lock:
        conn = _pools.pop(key, None)
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def execute_query(tenant: TenantContext, sql: str, limit: int | None = None) -> list[dict[str, Any]]:
    effective_limit = min(limit or MAX_QUERY_RESULTS, MAX_QUERY_RESULTS)

    if "LIMIT" not in sql.upper():
        sql = f"{sql} LIMIT {effective_limit}"

    conn = get_connection(tenant)

    try:
        with conn.cursor() as cursor:
            logger.info("Executing SQL for tenant=%s: %s", tenant.customer_key, sql[:300])
            cursor.execute(sql)
            rows = cursor.fetchall()
            logger.info("Query returned %d rows for tenant=%s", len(rows), tenant.customer_key)
            return rows
    except pymysql.Error as e:
        logger.error("SQL execution failed for tenant=%s: %s", tenant.customer_key, str(e))
        raise


def close_all() -> None:
    with _lock:
        for key, conn in _pools.items():
            try:
                conn.close()
                logger.info("Closed connection for tenant=%s", key)
            except Exception:
                pass
        _pools.clear()
