"""
InmateCopilot V1 — Business Constants
======================================

Domain-specific constants for the correctional intelligence system.
Includes sensitive columns, status filters, SQL guardrails, and domain keywords.
"""

from __future__ import annotations

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  SENSITIVE COLUMNS — never expose in query results                     ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

SENSITIVE_COLUMNS: frozenset[str] = frozenset({
    "password", "salt", "notes_pin", "strike_pin", "tags_pin",
    "signature", "signature_image", "latitude", "longitude",
    "ssn", "api_key", "token", "secret",
})

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  INTERNAL / TECHNICAL COLUMNS — exclude from user-facing results       ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

INTERNAL_COLUMNS: frozenset[str] = frozenset({
    "customer_key", "is_deleted", "is_archived", "created_by_system",
    "updated_at_internal", "sync_status", "device_token",
})

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  MANDATORY STATUS FILTERS                                              ║
# ║                                                                         ║
# ║  All queries MUST filter status = 1 for these tables.                  ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

STATUS_FILTER_TABLES: dict[str, str] = {
    "dg_notes": "n.status = 1",
    "dg_tags": "t.status = 1",
    "dg_user": "u.status = 1",
    "dg_facilities": "f.status = 1",
    "dg_highlighter": "h.status = 1",
    "dg_tag_status": "ts.status = 1",
}

TABLE_ALIAS_MAP: dict[str, str] = {
    "dg_notes": "n",
    "dg_notes_by_keyword": "knw",
    "dg_notes_tags": "ntg",
    "dg_notes_status_keyword": "nsk",
    "dg_tags": "t",
    "dg_tags_movement": "tm",
    "dg_facilities": "f",
    "dg_user": "u",
    "dg_shift": "s",
    "dg_highlighter": "h",
    "dg_tag_status": "ts",
    "dg_notes_by_comment": "c",
    "dg_notes_by_location": "loc",
    "dg_notes_media": "m",
}

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  MANDATORY COLUMNS — data queries must return these                    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

REQUIRED_DATA_COLUMNS: list[str] = [
    "notes_id", "notes_description", "note_date", "date_added", "user_id",
]

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  SQL SECURITY                                                          ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

DANGEROUS_SQL_KEYWORDS: frozenset[str] = frozenset({
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE",
    "TRUNCATE", "EXEC", "EXECUTE", "CALL", "GRANT", "REVOKE",
    "MERGE", "REPLACE",
})

SCHEMA_PATTERNS: list[str] = [
    "information_schema", "mysql.", "performance_schema",
    "sys.", "SHOW TABLES", "SHOW DATABASES", "SHOW COLUMNS",
]

SCHEMA_REGEX_PATTERNS: list[str] = [
    r"^\s*DESCRIBE\s+",
    r"^\s*DESC\s+\w+",
]

SQL_INJECTION_PATTERNS: list[str] = [
    "'; --", "' OR '1'='1", "UNION SELECT", "1=1",
    "' OR 1=1", "/*", "*/", "xp_", "sp_",
    "LOAD_FILE", "INTO OUTFILE", "INTO DUMPFILE",
]

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  DOMAIN KEYWORDS — for question relevance validation                   ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

DOMAIN_KEYWORDS: frozenset[str] = frozenset({
    "inmate", "inmates", "officer", "officers", "note", "notes",
    "entry", "entries", "log", "logs", "record", "records",
    "facility", "facilities", "prison", "prisons",
    "watch", "fire", "suicide", "round", "rounds", "shift", "shifts",
    "keyword", "keywords", "tag", "tags", "status", "highlighter",
    "highlighted", "marked", "red", "cell", "cells", "dorm", "dorms",
    "movement", "meal", "recreation", "room",
    "medical", "yard", "segregation", "bed", "check", "checks",
    "prescription", "mail", "refusal", "refused", "complaint", "incident",
    "warden", "corrections", "booking", "transfer", "visitor",
    "active", "inactive", "count", "total",
    "security", "inventory", "disciplinary", "emergency", "fight",
    "user", "users", "data",
})

QUERY_KEYWORDS: frozenset[str] = frozenset({
    "how many", "count", "list", "show", "find", "get",
    "fetch", "retrieve", "all", "display",
    "which", "who", "when", "where", "what", "total",
    "average", "avg", "max", "min", "top", "most",
    "least", "between", "last", "recent", "today",
    "yesterday", "week", "month", "daily", "summary",
})

IRRELEVANT_PATTERNS: list[str] = [
    "weather", "sports", "stock", "recipe", "movie",
    "music", "game", "joke", "story", "poem",
    "translate", "calculate", "math", "homework",
]

NON_SQL_PATTERNS: list[str] = [
    "how are you", "hello", "hi ", "hey ", "thanks",
    "thank you", "bye", "goodbye", "good morning",
    "help me", "what can you do", "who are you",
]

# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  HIGHLIGHTER COLORS                                                    ║
# ╚═══════════════════════════════════════════════════════════════════════════╝

HIGHLIGHTER_MAP: dict[int, str] = {
    11: "Red",
    12: "Light Green",
    13: "Blue",
    14: "Yellow",
    15: "Pink",
    21: "White",
    22: "Orange",
}
