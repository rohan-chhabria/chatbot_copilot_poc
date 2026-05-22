"""
Customer Configuration — Per-customer settings from DynamoDB.

Each customer has one row in the ChatbotCustomerConfiguration table
containing all configurable settings: DB connections, LLM keys, branding,
feature flags, pipeline tuning, and monitoring config.

Backward-compatible: if CUSTOMER_CONFIG_TABLE is not set, falls back to
the existing env-var-based configuration in shared/config.py.
"""

from __future__ import annotations

import threading
from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.shared.config import (
    BOT_GREETING,
    BOT_NAME,
    CUSTOMER_CONFIG_TABLE,
    DAILY_ACTIVITY_LOOKAHEAD_HOURS,
    DAILY_ACTIVITY_LOOKBACK_HOURS,
    DOC_HYBRID_SEARCH,
    DOC_PIPELINE_TIMEOUT,
    DOC_RERANKING_ENABLED,
    DOC_RETRIEVAL_TOP_K,
    ENABLE_GUARDRAILS,
    INMATE_PIPELINE_TIMEOUT,
    LLM_PROVIDER,
    LLM_TEMPERATURE,
    LOG_LEVEL,
    MAX_CONVERSATION_TURNS,
    MAX_QUERY_RESULTS,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    SESSION_TTL_SECONDS,
    STRICT_TENANT_VALIDATION,
    TENANT_DB_MAP,
)
from src.shared.logger import get_logger

logger = get_logger(__name__)

_lock = threading.Lock()
_cache: dict[str, dict[str, Any]] = {}
_dynamo_table = None


def _get_table():
    global _dynamo_table
    if _dynamo_table is None:
        dynamodb = boto3.resource("dynamodb")
        _dynamo_table = dynamodb.Table(CUSTOMER_CONFIG_TABLE)
    return _dynamo_table


def _env_var_defaults(customer_key: str) -> dict[str, Any]:
    """Build config dict from existing env vars for backward compatibility."""
    db_config = TENANT_DB_MAP.get(customer_key, {})
    if not db_config and TENANT_DB_MAP:
        default_key = next(iter(TENANT_DB_MAP))
        db_config = TENANT_DB_MAP[default_key]

    return {
        "customer_key": customer_key,
        "db_host": db_config.get("host", ""),
        "db_name": db_config.get("database", ""),
        "db_user": db_config.get("user", ""),
        "db_password": db_config.get("password", ""),
        "db_port": db_config.get("port", 3306),
        "llm_provider": LLM_PROVIDER,
        "llm_model": OPENAI_MODEL,
        "llm_temperature": LLM_TEMPERATURE,
        "openai_api_key": OPENAI_API_KEY,
        "bot_name": BOT_NAME,
        "bot_greeting": BOT_GREETING,
        "max_query_results": MAX_QUERY_RESULTS,
        "max_conversation_turns": MAX_CONVERSATION_TURNS,
        "enable_guardrails": ENABLE_GUARDRAILS,
        "strict_tenant_validation": STRICT_TENANT_VALIDATION,
        "session_ttl_seconds": SESSION_TTL_SECONDS,
        "inmate_pipeline_timeout": INMATE_PIPELINE_TIMEOUT,
        "doc_pipeline_timeout": DOC_PIPELINE_TIMEOUT,
        "doc_retrieval_top_k": DOC_RETRIEVAL_TOP_K,
        "doc_hybrid_search": DOC_HYBRID_SEARCH,
        "doc_reranking_enabled": DOC_RERANKING_ENABLED,
        "daily_activity_lookback_hours": DAILY_ACTIVITY_LOOKBACK_HOURS,
        "daily_activity_lookahead_hours": DAILY_ACTIVITY_LOOKAHEAD_HOURS,
        "log_level": LOG_LEVEL,
        "allowed_origins": "*",
        "sentry_dsn": "",
        "enabled": True,
        "_source": "env_vars",
    }


def _fetch_from_dynamo(customer_key: str) -> dict[str, Any] | None:
    """Fetch customer config from DynamoDB. Returns None if not found."""
    try:
        table = _get_table()
        response = table.get_item(Key={"customer_key": customer_key})
        item = response.get("Item")
        if item:
            item["_source"] = "dynamodb"
            logger.info(
                "Loaded config from DynamoDB for customer=%s",
                customer_key,
            )
            return item
        return None
    except ClientError as e:
        logger.error(
            "DynamoDB error loading config for customer=%s: %s",
            customer_key,
            e.response["Error"]["Message"],
        )
        return None
    except Exception as e:
        logger.error(
            "Unexpected error loading config for customer=%s: %s",
            customer_key,
            str(e),
        )
        return None


def get_customer_config(customer_key: str) -> dict[str, Any]:
    """
    Get configuration for a customer. Cached per-process after first load.

    Resolution order:
    1. In-process cache (fastest)
    2. DynamoDB ChatbotCustomerConfiguration table
    3. Environment variable defaults (backward-compatible fallback)
    """
    normalized = customer_key.strip().lower()

    if normalized in _cache:
        return _cache[normalized]

    with _lock:
        if normalized in _cache:
            return _cache[normalized]

        config = None

        if CUSTOMER_CONFIG_TABLE:
            config = _fetch_from_dynamo(normalized)

        if config is None:
            config = _env_var_defaults(normalized)
            logger.info(
                "Using env var defaults for customer=%s (table=%s)",
                normalized,
                "not_configured" if not CUSTOMER_CONFIG_TABLE else "not_found",
            )

        _cache[normalized] = config
        return config


def invalidate_cache(customer_key: str | None = None) -> None:
    """Clear cached config. Pass customer_key to clear one, or None for all."""
    with _lock:
        if customer_key:
            _cache.pop(customer_key.strip().lower(), None)
        else:
            _cache.clear()


def is_customer_enabled(customer_key: str) -> bool:
    """Check if a customer is enabled in configuration."""
    config = get_customer_config(customer_key)
    return config.get("enabled", True)
