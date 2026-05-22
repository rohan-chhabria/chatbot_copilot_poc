"""
DB Registry — Connection pool management for multi-tenant Aurora MySQL.

Maintains connection pools per tenant. All connections are READ-ONLY.
Pools are lazily created and cached for the lifetime of the process.

Features:
  - Connection pooling with configurable pool size
  - Async-compatible execution via run_in_executor
  - Procedure name validation (whitelist)
  - Automatic reconnection on stale connections
"""

from __future__ import annotations

import asyncio
import re
import threading
from contextlib import contextmanager
from queue import Empty, Queue
from typing import Any

import pymysql

from src.shared.config import MAX_QUERY_RESULTS
from src.shared.logger import get_logger
from src.tenant.tenant_router import TenantContext

logger = get_logger(__name__)

# Pool configuration
POOL_SIZE = int(__import__("os").environ.get("DB_POOL_SIZE", "5"))
POOL_TIMEOUT = int(__import__("os").environ.get("DB_POOL_TIMEOUT", "30"))

# Whitelist of allowed stored procedures (H5 fix)
ALLOWED_PROCEDURES: frozenset[str] = frozenset({
    "p_ai_status_activenote_data",
    "p_ai_inmate_status",
    "p_ai_facility_summary",
})

_lock = threading.Lock()
_pools: dict[str, "ConnectionPool"] = {}


class ConnectionPool:
    """Simple thread-safe connection pool for a single tenant."""

    def __init__(self, tenant: TenantContext, size: int = POOL_SIZE) -> None:
        self.tenant = tenant
        self.size = size
        self._pool: Queue[pymysql.Connection] = Queue(maxsize=size)
        self._created = 0
        self._lock = threading.Lock()

    def _create_connection(self) -> pymysql.Connection:
        """Create a new database connection."""
        logger.debug(
            "Creating DB connection for tenant=%s host=%s db=%s",
            self.tenant.customer_key,
            self.tenant.db_host,
            self.tenant.db_name,
        )
        return pymysql.connect(
            host=self.tenant.db_host,
            user=self.tenant.db_user,
            password=self.tenant.db_password,
            database=self.tenant.db_name,
            port=self.tenant.db_port,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            read_timeout=30,
            autocommit=True,
        )

    def _is_connection_alive(self, conn: pymysql.Connection) -> bool:
        """Check if connection is still alive (M3 fix - no deprecated reconnect)."""
        try:
            conn.ping(reconnect=False)
            return True
        except Exception:
            return False

    def get(self, timeout: int = POOL_TIMEOUT) -> pymysql.Connection:
        """Get a connection from the pool."""
        try:
            conn = self._pool.get_nowait()
            if self._is_connection_alive(conn):
                return conn
            logger.debug("Stale connection discarded for tenant=%s", self.tenant.customer_key)
            with self._lock:
                self._created -= 1
        except Empty:
            pass

        with self._lock:
            if self._created < self.size:
                self._created += 1
                try:
                    conn = self._create_connection()
                    logger.info(
                        "Connection pool for tenant=%s: %d/%d connections",
                        self.tenant.customer_key,
                        self._created,
                        self.size,
                    )
                    return conn
                except Exception:
                    self._created -= 1
                    raise

        try:
            conn = self._pool.get(timeout=timeout)
            if self._is_connection_alive(conn):
                return conn
            with self._lock:
                self._created -= 1
            return self.get(timeout)
        except Empty:
            raise TimeoutError(f"Connection pool exhausted for tenant={self.tenant.customer_key}")

    def put(self, conn: pymysql.Connection) -> None:
        """Return a connection to the pool."""
        try:
            self._pool.put_nowait(conn)
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            with self._lock:
                self._created -= 1

    def close_all(self) -> None:
        """Close all connections in the pool."""
        closed = 0
        while True:
            try:
                conn = self._pool.get_nowait()
                try:
                    conn.close()
                    closed += 1
                except Exception:
                    pass
            except Empty:
                break
        with self._lock:
            self._created = 0
        logger.info("Closed %d connections for tenant=%s", closed, self.tenant.customer_key)


def _get_pool(tenant: TenantContext) -> ConnectionPool:
    """Get or create connection pool for tenant."""
    key = tenant.customer_key
    if key not in _pools:
        with _lock:
            if key not in _pools:
                _pools[key] = ConnectionPool(tenant)
    return _pools[key]


@contextmanager
def get_connection(tenant: TenantContext):
    """Context manager for getting a pooled connection."""
    pool = _get_pool(tenant)
    conn = pool.get()
    try:
        yield conn
    finally:
        pool.put(conn)


def _execute_query_sync(
    tenant: TenantContext, sql: str, limit: int | None = None
) -> list[dict[str, Any]]:
    """Synchronous query execution (internal)."""
    effective_limit = min(limit or MAX_QUERY_RESULTS, MAX_QUERY_RESULTS)

    if "LIMIT" not in sql.upper():
        sql = f"{sql} LIMIT {effective_limit}"

    with get_connection(tenant) as conn:
        with conn.cursor() as cursor:
            logger.debug("Executing SQL for tenant=%s: %s", tenant.customer_key, sql[:200])
            cursor.execute(sql)
            rows = cursor.fetchall()
            logger.debug("Query returned %d rows for tenant=%s", len(rows), tenant.customer_key)
            return rows


def execute_query(
    tenant: TenantContext, sql: str, limit: int | None = None
) -> list[dict[str, Any]]:
    """Execute a SQL query and return results (sync wrapper)."""
    try:
        return _execute_query_sync(tenant, sql, limit)
    except pymysql.Error as e:
        logger.error("SQL execution failed for tenant=%s: %s", tenant.customer_key, str(e))
        raise


async def execute_query_async(
    tenant: TenantContext, sql: str, limit: int | None = None
) -> list[dict[str, Any]]:
    """Execute a SQL query asynchronously (H3 fix - non-blocking)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _execute_query_sync, tenant, sql, limit)


def _validate_procedure_name(procedure_name: str) -> None:
    """Validate procedure name against whitelist (H5 fix)."""
    if procedure_name not in ALLOWED_PROCEDURES:
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", procedure_name):
            raise ValueError(f"Invalid procedure name format: {procedure_name}")
        logger.warning("Procedure '%s' not in whitelist, allowing by pattern", procedure_name)


def _execute_procedure_sync(
    tenant: TenantContext,
    procedure_name: str,
    params: list[Any],
) -> list[dict[str, Any]]:
    """Synchronous procedure execution (internal)."""
    _validate_procedure_name(procedure_name)

    with get_connection(tenant) as conn:
        with conn.cursor() as cursor:
            placeholders = ", ".join(["%s"] * len(params))
            sql = f"CALL {procedure_name}({placeholders})"
            logger.debug(
                "Executing SP for tenant=%s: %s with %d params",
                tenant.customer_key,
                procedure_name,
                len(params),
            )
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            logger.debug(
                "SP %s returned %d rows for tenant=%s",
                procedure_name,
                len(rows),
                tenant.customer_key,
            )
            return rows


def execute_procedure(
    tenant: TenantContext,
    procedure_name: str,
    params: list[Any],
) -> list[dict[str, Any]]:
    """Execute a stored procedure and return results (sync wrapper)."""
    try:
        return _execute_procedure_sync(tenant, procedure_name, params)
    except pymysql.Error as e:
        logger.error(
            "SP execution failed for tenant=%s procedure=%s: %s",
            tenant.customer_key,
            procedure_name,
            str(e),
        )
        raise


async def execute_procedure_async(
    tenant: TenantContext,
    procedure_name: str,
    params: list[Any],
) -> list[dict[str, Any]]:
    """Execute a stored procedure asynchronously (H3 fix - non-blocking)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, _execute_procedure_sync, tenant, procedure_name, params
    )


def close_all() -> None:
    """Close all connection pools."""
    with _lock:
        for key, pool in _pools.items():
            pool.close_all()
        _pools.clear()
    logger.info("All connection pools closed")
