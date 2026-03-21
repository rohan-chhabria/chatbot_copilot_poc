"""
InmateCopilot V1 — Centralized Configuration
=============================================

All application settings loaded from environment variables with sensible defaults.
Tenant DB connections, LLM config, session/memory settings, and AWS resource names.

Design:
  - Multi-tenant: customer_key routes to tenant-specific Aurora MySQL.
  - Single deployment serves all clients.
  - Resource names follow: InmateCopilot-{Resource}-{DeploymentId}-{Environment}
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  ENVIRONMENT                                                            ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "dev")
DEPLOYMENT_ID: str = os.environ.get("DEPLOYMENT_ID", "localdev000")
IS_LAMBDA: bool = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "") != ""
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  LLM CONFIGURATION                                                     ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "openai")
OPENAI_API_KEY: str = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.environ.get("LLM_MODEL", "gpt-4o-mini")
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
LLM_TEMPERATURE: float = float(os.environ.get("LLM_TEMPERATURE", "0.1"))

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  TENANT DATABASE CONFIGURATION                                         ║
# ║                                                                         ║
# ║  JSON map: customer_key → {host, database, user, password, port}       ║
# ║  Each tenant has its own Aurora MySQL reader endpoint.                  ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

_DEFAULT_TENANT_DB: dict = {
    "demo": {
        "host": os.environ.get("MYSQL_HOST", "localhost"),
        "database": os.environ.get("MYSQL_DATABASE", "Demo_aurora"),
        "user": os.environ.get("MYSQL_USER", "root"),
        "password": os.environ.get("MYSQL_PASSWORD", ""),
        "port": int(os.environ.get("MYSQL_PORT", "3306")),
    }
}

def _load_tenant_db_map() -> dict[str, dict[str, Any]]:
    raw = os.environ.get("TENANT_DB_MAP", "")
    if raw:
        return json.loads(raw)
    return _DEFAULT_TENANT_DB

TENANT_DB_MAP: dict[str, dict[str, Any]] = _load_tenant_db_map()

STRICT_TENANT_VALIDATION: bool = os.environ.get(
    "STRICT_TENANT_VALIDATION", "false"
).lower() == "true"


def is_valid_tenant(customer_key: str) -> bool:
    if not STRICT_TENANT_VALIDATION:
        return True
    return customer_key in TENANT_DB_MAP

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  VALKEY / REDIS (Session Store)                                         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

VALKEY_HOST: str = os.environ.get("VALKEY_HOST", "localhost")
VALKEY_PORT: int = int(os.environ.get("VALKEY_PORT", "6379"))
VALKEY_DB: int = int(os.environ.get("VALKEY_DB", "0"))
SESSION_TTL_SECONDS: int = int(os.environ.get("SESSION_TTL_SECONDS", "3600"))

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  DYNAMODB (Conversation History)                                        ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

CONVERSATION_TABLE: str = os.environ.get(
    "CONVERSATION_TABLE", "InmateCopilot-Conversations-local"
)

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  CHROMADB (Vector Store)                                                ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

CHROMA_STORAGE_DIR: str = os.environ.get("CHROMA_STORAGE_DIR", "./chroma_db")
VANNA_COLLECTION_NAME: str = os.environ.get("VANNA_COLLECTION_NAME", "inmate_copilot")
VANNA_MODEL_NAME: str = os.environ.get("VANNA_MODEL_NAME", "inmate_copilot_v1")

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  APPLICATION SETTINGS                                                   ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

MAX_QUERY_RESULTS: int = int(os.environ.get("MAX_QUERY_RESULTS", "500"))
MAX_CONVERSATION_TURNS: int = int(os.environ.get("MAX_CONVERSATION_TURNS", "15"))
ENABLE_GUARDRAILS: bool = os.environ.get("ENABLE_GUARDRAILS", "true").lower() == "true"
MIN_QUESTION_LENGTH: int = int(os.environ.get("MIN_QUESTION_LENGTH", "5"))
MAX_QUESTION_LENGTH: int = int(os.environ.get("MAX_QUESTION_LENGTH", "1000"))

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  BOT / UI CONFIGURATION                                                ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

BOT_NAME: str = os.environ.get("BOT_NAME", "Sarah")
BOT_GREETING: str = os.environ.get(
    "BOT_GREETING",
    "Hi, I'm {bot_name} — your Inmate Intelligence assistant. "
    "Ask me anything about notes, inmates, officers, facilities, or keywords. "
    "How can I help you today?",
)
LOCAL_USERS_PATH: str = os.environ.get(
    "LOCAL_USERS_PATH",
    str(Path(__file__).resolve().parents[2] / "local_users.json"),
)
USE_LOCAL_DYNAMO: bool = os.environ.get("USE_LOCAL_DYNAMO", "true").lower() == "true"

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  TRAINING DATA PATHS                                                    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

TRAINING_EXAMPLES_PATH: str = os.environ.get(
    "TRAINING_EXAMPLES_PATH", "src/training/data/default_examples.json"
)
TRAINING_DOCUMENTATION_PATH: str = os.environ.get(
    "TRAINING_DOCUMENTATION_PATH", "src/training/data/default_documentation.json"
)

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  PIPELINE CONFIGURATION                                                   ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

# Inmate Data Pipeline
INMATE_PIPELINE_TIMEOUT: int = int(os.environ.get("INMATE_PIPELINE_TIMEOUT", "30"))

# Document QA Pipeline
DOC_PIPELINE_TIMEOUT: int = int(os.environ.get("DOC_PIPELINE_TIMEOUT", "30"))
DOC_CHROMA_DIR: str = os.environ.get("DOC_CHROMA_DIR", "./chroma_docs")
DOC_EMBEDDING_MODEL: str = os.environ.get("DOC_EMBEDDING_MODEL", "text-embedding-3-small")
DOC_RETRIEVAL_TOP_K: int = int(os.environ.get("DOC_RETRIEVAL_TOP_K", "5"))
DOC_HYBRID_SEARCH: bool = os.environ.get("DOC_HYBRID_SEARCH", "true").lower() == "true"
DOC_RERANKING_ENABLED: bool = os.environ.get("DOC_RERANKING_ENABLED", "false").lower() == "true"

# Scope Configuration
DEFAULT_SCOPE: str | None = os.environ.get("DEFAULT_SCOPE") or None  # None = show options
SCOPE_SWITCH_COOLDOWN: int = int(os.environ.get("SCOPE_SWITCH_COOLDOWN", "0"))  # seconds
