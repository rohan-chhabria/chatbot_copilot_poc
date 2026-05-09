"""
Session models with scope management support.

Enhanced session model that supports:
- Scope tracking (active scope, scope history)
- Per-scope context preservation (ScopeContext)
- Conversation turns tagged by scope
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from src.shared.config import MAX_CONVERSATION_TURNS


@dataclass
class ScopeContext:
    """Working memory for a specific scope — preserved across switches."""

    scope: str
    recent_entities: dict[str, Any] = field(default_factory=dict)
    recent_queries: list[str] = field(default_factory=list)
    last_active: float = field(default_factory=time.time)

    def add_query(self, query: str, max_queries: int = 5) -> None:
        """Add a query, maintaining max size."""
        self.recent_queries.append(query)
        if len(self.recent_queries) > max_queries:
            self.recent_queries = self.recent_queries[-max_queries:]
        self.last_active = time.time()

    def update_entity(self, key: str, value: Any) -> None:
        """Update an entity in working memory."""
        self.recent_entities[key] = value
        self.last_active = time.time()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "scope": self.scope,
            "recent_entities": self.recent_entities,
            "recent_queries": self.recent_queries,
            "last_active": self.last_active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScopeContext:
        """Deserialize from dictionary."""
        return cls(
            scope=data["scope"],
            recent_entities=data.get("recent_entities", {}),
            recent_queries=data.get("recent_queries", []),
            last_active=data.get("last_active", time.time()),
        )


@dataclass
class ConversationTurn:
    """Single turn in conversation with scope tracking."""

    role: str  # "user" | "assistant" | "system"
    content: str
    scope: str | None = None  # Which scope this turn belongs to
    timestamp: float = field(default_factory=time.time)
    sql: str = ""  # For inmate_data pipeline
    row_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "role": self.role,
            "content": self.content,
            "scope": self.scope,
            "timestamp": self.timestamp,
            "sql": self.sql,
            "row_count": self.row_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConversationTurn:
        """Deserialize from dictionary."""
        return cls(
            role=data["role"],
            content=data["content"],
            scope=data.get("scope"),
            timestamp=data.get("timestamp", time.time()),
            sql=data.get("sql", ""),
            row_count=data.get("row_count", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Session:
    """Enhanced session with scope management."""

    session_id: str
    customer_key: str
    user_id: str
    facility_ids: list[int] = field(default_factory=list)
    role: str = "officer"
    display_name: str = ""

    # Conversation
    turns: list[ConversationTurn] = field(default_factory=list)

    # Scope management
    active_scope: str | None = None
    scope_history: list[str] = field(default_factory=list)
    scope_contexts: dict[str, ScopeContext] = field(default_factory=dict)

    # Timestamps
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        now = time.time()
        if self.created_at == 0.0:
            self.created_at = now
        if self.last_active == 0.0:
            self.last_active = now

    def add_turn(self, turn: ConversationTurn) -> None:
        """Add turn with scope tag."""
        turn.scope = turn.scope or self.active_scope
        self.turns.append(turn)
        self.last_active = time.time()
        self._enforce_scope_window(turn.scope)

    def _enforce_scope_window(self, scope: str | None) -> None:
        """Keep a per-scope rolling STM window."""
        scoped_indexes = [i for i, t in enumerate(self.turns) if t.scope == scope]
        overflow = len(scoped_indexes) - MAX_CONVERSATION_TURNS
        if overflow <= 0:
            return

        remove_indexes = set(scoped_indexes[:overflow])
        self.turns = [t for i, t in enumerate(self.turns) if i not in remove_indexes]

    def get_scope_context(self, scope: str | None = None) -> ScopeContext | None:
        """Get context for a scope (defaults to active)."""
        scope = scope or self.active_scope
        if not scope:
            return None
        return self.scope_contexts.get(scope)

    def switch_scope(self, new_scope: str) -> ScopeContext:
        """Switch to a new scope, preserving current context."""
        self.active_scope = new_scope
        self.scope_history.append(new_scope)

        if new_scope not in self.scope_contexts:
            self.scope_contexts[new_scope] = ScopeContext(scope=new_scope)

        self.last_active = time.time()
        return self.scope_contexts[new_scope]

    def get_turns_for_scope(self, scope: str | None = None) -> list[ConversationTurn]:
        """Get turns filtered by scope."""
        scope = scope or self.active_scope
        if not scope:
            return self.turns
        return [t for t in self.turns if t.scope == scope]

    def get_history_prompt(self, max_turns: int = 2) -> str:
        """Return scoped last N turns for SQL context."""
        turns = self.get_turns_for_scope()
        if not turns:
            return ""
        lines = []
        for turn in turns[-max_turns:]:
            lines.append(f"{turn.role}: {turn.content}")
        return "\n".join(lines)

    def get_last_turn(
        self,
        role: str | None = None,
        scope: str | None = None,
    ) -> ConversationTurn | None:
        turns = self.get_turns_for_scope(scope)
        if role is not None:
            turns = [t for t in turns if t.role == role]
        return turns[-1] if turns else None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "customer_key": self.customer_key,
            "user_id": self.user_id,
            "facility_ids": self.facility_ids,
            "role": self.role,
            "display_name": self.display_name,
            "turns": [t.to_dict() for t in self.turns],
            "active_scope": self.active_scope,
            "scope_history": self.scope_history,
            "scope_contexts": {k: v.to_dict() for k, v in self.scope_contexts.items()},
            "created_at": self.created_at,
            "last_active": self.last_active,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        """Deserialize from dictionary."""
        turns = [ConversationTurn.from_dict(t) for t in data.get("turns", [])]
        scope_contexts = {
            k: ScopeContext.from_dict(v)
            for k, v in data.get("scope_contexts", {}).items()
        }
        return cls(
            session_id=data["session_id"],
            customer_key=data["customer_key"],
            user_id=data["user_id"],
            facility_ids=data.get("facility_ids", []),
            role=data.get("role", "officer"),
            display_name=data.get("display_name", ""),
            turns=turns,
            active_scope=data.get("active_scope"),
            scope_history=data.get("scope_history", []),
            scope_contexts=scope_contexts,
            created_at=data.get("created_at", 0.0),
            last_active=data.get("last_active", 0.0),
        )


def create_session(
    customer_key: str,
    user_id: str,
    facility_ids: list[int] | None = None,
    role: str = "officer",
    display_name: str = "",
) -> Session:
    """Factory function to create a new session."""
    return Session(
        session_id=str(uuid.uuid4()),
        customer_key=customer_key,
        user_id=user_id,
        facility_ids=facility_ids or [],
        role=role,
        display_name=display_name or user_id.replace(".", " ").title(),
    )
