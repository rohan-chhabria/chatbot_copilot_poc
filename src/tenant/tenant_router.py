"""
Tenant Router — Routes customer_key to the correct database connection.

Single deployment serves all tenants. The customer_key (from request header
or auth token) determines which Aurora MySQL endpoint is used.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.shared.config import STRICT_TENANT_VALIDATION, TENANT_DB_MAP, is_valid_tenant
from src.shared.logger import get_logger

logger = get_logger(__name__)


class TenantNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class TenantContext:
    customer_key: str
    db_host: str
    db_name: str
    db_user: str
    db_password: str
    db_port: int


def resolve_tenant(customer_key: str) -> TenantContext:
    if not customer_key:
        raise TenantNotFoundError("customer_key is required.")

    normalized = customer_key.strip().lower()

    if not is_valid_tenant(normalized):
        logger.warning("Unknown tenant rejected: %s", normalized)
        raise TenantNotFoundError(f"Unknown tenant: {normalized}")

    db_config = TENANT_DB_MAP.get(normalized)
    if not db_config:
        if STRICT_TENANT_VALIDATION:
            raise TenantNotFoundError(f"No DB config for tenant: {normalized}")

        logger.info("Using default DB config for unregistered tenant: %s", normalized)
        default_key = next(iter(TENANT_DB_MAP))
        db_config = TENANT_DB_MAP[default_key]

    return TenantContext(
        customer_key=normalized,
        db_host=db_config["host"],
        db_name=db_config["database"],
        db_user=db_config["user"],
        db_password=db_config["password"],
        db_port=db_config.get("port", 3306),
    )


def list_tenants() -> list[str]:
    return list(TENANT_DB_MAP.keys())
