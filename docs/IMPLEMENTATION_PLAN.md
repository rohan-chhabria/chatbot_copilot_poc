# InmateCopilot — Implementation Plan (Historical)

**Version**: 2.0
**Created**: 2026-03-19
**Status**: Archived (implemented; keep for historical migration context)

---

## Table of Contents

1. [Overview](#overview)
2. [Folder Structure](#folder-structure)
3. [Implementation Phases](#implementation-phases)
4. [Phase 1: Foundation](#phase-1-foundation)
5. [Phase 2: Orchestrator Layer](#phase-2-orchestrator-layer)
6. [Phase 3: Migrate Inmate Pipeline](#phase-3-migrate-inmate-pipeline)
7. [Phase 4: Document QA Pipeline](#phase-4-document-qa-pipeline)
8. [Phase 5: API Integration](#phase-5-api-integration)
9. [Phase 6: Testing & Validation](#phase-6-testing--validation)
10. [File-by-File Changes](#file-by-file-changes)
11. [Migration Strategy](#migration-strategy)

---

## Overview

### Goals

1. Transform single-purpose SQL chatbot into guided multi-capability agent
2. Add document QA pipeline alongside existing Vanna pipeline
3. Implement scope management with context preservation
4. Maintain backward compatibility throughout migration

### Principles

- **No Breaking Changes**: Existing functionality continues to work
- **Incremental Migration**: Each phase is independently deployable
- **SOLID Compliance**: Clean interfaces, single responsibility
- **Test-Driven**: Each component has tests before integration

---

## Folder Structure

### Current Structure

```
src/
├── api/
│   ├── __init__.py
│   ├── handler.py
│   ├── middleware.py
│   ├── routes.py
│   └── schemas.py
├── agent/
│   ├── __init__.py
│   ├── intent_engine.py
│   ├── prompt_builder.py
│   ├── response_formatter.py
│   ├── domain_responses.py
│   └── vanna_agent.py      # AgentPipeline class
├── guardrails/
│   ├── __init__.py
│   ├── question_validator.py
│   └── sql_validator.py
├── memory/
│   ├── __init__.py
│   └── conversation_store.py
├── session/
│   ├── __init__.py
│   └── session_manager.py
├── shared/
│   ├── __init__.py
│   ├── config.py
│   ├── constants.py
│   └── logger.py
├── tenant/
│   ├── __init__.py
│   ├── db_registry.py
│   └── tenant_router.py
├── tools/
│   └── ...
└── training/
    └── ...
```

### Target Structure

```
src/
├── api/
│   ├── __init__.py
│   ├── handlers/                    # NEW: Split handlers
│   │   ├── __init__.py
│   │   ├── chat_handler.py          # Main chat orchestration
│   │   └── scope_handler.py         # Scope selection/switching
│   ├── middleware.py
│   ├── routes.py                    # MODIFIED: Add scope endpoints
│   └── schemas.py                   # MODIFIED: Add scope schemas
│
├── orchestrator/                    # NEW: Coordination layer
│   ├── __init__.py
│   ├── state_machine.py             # ScopeStateMachine
│   ├── scope_registry.py            # Pipeline registry
│   ├── cross_scope.py               # Greetings, recall, help
│   └── tests/
│       ├── __init__.py
│       ├── test_state_machine.py
│       └── test_cross_scope.py
│
├── pipelines/                       # NEW: Modular pipelines
│   ├── __init__.py
│   ├── base.py                      # Abstract Pipeline interface
│   │
│   ├── inmate_data/                 # MIGRATED from agent/
│   │   ├── __init__.py              # Registers with ScopeRegistry
│   │   ├── pipeline.py              # InmateDataPipeline
│   │   ├── vanna_agent.py           # MOVED from agent/
│   │   ├── prompt_builder.py        # MOVED from agent/
│   │   ├── response_formatter.py    # MOVED from agent/
│   │   ├── intent_engine.py         # MOVED from agent/
│   │   ├── domain_responses.py      # Inmate-domain conversational logic
│   │   ├── guardrails/
│   │   │   ├── __init__.py
│   │   │   ├── question_validator.py  # MOVED from guardrails/
│   │   │   └── sql_validator.py       # MOVED from guardrails/
│   │   ├── config.py                # Pipeline-specific config
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── conftest.py
│   │       ├── test_pipeline.py
│   │       ├── test_vanna_agent.py
│   │       └── test_guardrails.py
│   │
│   └── document_qa/                 # NEW: RAG pipeline
│       ├── __init__.py              # Registers with ScopeRegistry
│       ├── pipeline.py              # DocumentQAPipeline
│       ├── retriever.py             # Hybrid search (semantic + BM25)
│       ├── synthesizer.py           # LLM answer generation
│       ├── documents/               # Document management
│       │   ├── __init__.py
│       │   ├── store.py             # ChromaDB tenant-isolated
│       │   ├── loader.py            # PDF, DOCX, TXT parsing
│       │   ├── chunker.py           # Recursive chunking
│       │   └── models.py            # Document, Chunk dataclasses
│       ├── guardrails/
│       │   ├── __init__.py
│       │   └── validator.py
│       ├── config.py
│       ├── scripts/
│       │   └── index_documents.py   # Pre-indexing CLI
│       └── tests/
│           ├── __init__.py
│           ├── conftest.py
│           ├── test_pipeline.py
│           ├── test_retriever.py
│           └── fixtures/
│               ├── sample.pdf
│               └── sample.txt
│
├── session/                         # ENHANCED
│   ├── __init__.py
│   ├── models.py                    # NEW: Session, Turn, ScopeContext
│   ├── session_manager.py           # MODIFIED: Scope management
│   └── models.py                    # ScopeContext kept in models.py
│
├── memory/                          # ENHANCED
│   ├── __init__.py
│   ├── stm/                         # NEW: Organized
│   │   ├── __init__.py
│   │   └── session_store.py         # MOVED from session_manager
│   └── ltm/
│       ├── __init__.py
│       └── conversation_store.py    # MODIFIED: Add scope field
│
├── agent/                           # DEPRECATED (kept for compat)
│   ├── __init__.py                  # Re-exports from pipelines/inmate_data
│   └── _deprecated.py               # Deprecation warnings
│
├── guardrails/                      # DEPRECATED (kept for compat)
│   ├── __init__.py                  # Re-exports from pipelines/inmate_data/guardrails
│   └── _deprecated.py
│
├── tenant/                          # UNCHANGED
│   └── ...
├── shared/                          # ENHANCED
│   ├── __init__.py
│   ├── config.py                    # MODIFIED: Add pipeline configs
│   ├── constants.py
│   ├── logger.py
│   └── exceptions.py                # NEW: Custom exceptions
└── training/                        # UNCHANGED
    └── ...
```

---

## Implementation Phases

```
Phase 1: Foundation (Days 1-2)
├── Enhanced session models
├── Base pipeline interface
├── Shared exceptions
└── Tests

Phase 2: Orchestrator Layer (Days 3-4)
├── ScopeStateMachine
├── ScopeRegistry
├── CrossScopeHandler
└── Tests

Phase 3: Migrate Inmate Pipeline (Days 5-6)
├── Move files to pipelines/inmate_data/
├── Create InmateDataPipeline wrapper
├── Backward compatibility shims
└── Tests

Phase 4: Document QA Pipeline (Days 7-10)
├── Document store (ChromaDB)
├── Loader + Chunker
├── Retriever (hybrid search)
├── Synthesizer
├── DocumentQAPipeline
└── Tests

Phase 5: API Integration (Days 11-12)
├── New endpoints
├── Handler refactoring
├── Schema updates
└── Integration tests

Phase 6: Testing & Validation (Days 13-14)
├── End-to-end tests
├── Load testing
├── Documentation
└── Deploy to staging
```

---

## Phase 1: Foundation

### 1.1 Create Session Models

**File**: `src/session/models.py` (NEW)

```python
"""
Session models with scope management support.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
import time
import uuid


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


@dataclass
class ConversationTurn:
    """Single turn in conversation with scope tracking."""
    role: str                          # "user" | "assistant" | "system"
    content: str
    scope: str | None = None           # Which scope this turn belongs to
    timestamp: float = field(default_factory=time.time)
    sql: str = ""                      # For inmate_data pipeline
    row_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


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

    # Scope management (NEW)
    active_scope: str | None = None
    scope_history: list[str] = field(default_factory=list)
    scope_contexts: dict[str, ScopeContext] = field(default_factory=dict)

    # Timestamps
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)

    def add_turn(self, turn: ConversationTurn) -> None:
        """Add turn with scope tag."""
        turn.scope = turn.scope or self.active_scope
        self.turns.append(turn)
        self.last_active = time.time()

        # Trim to max turns
        from src.shared.config import MAX_CONVERSATION_TURNS
        if len(self.turns) > MAX_CONVERSATION_TURNS:
            self.turns = self.turns[-MAX_CONVERSATION_TURNS:]

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
        display_name=display_name or user_id,
    )
```

### 1.2 Create Base Pipeline Interface

**File**: `src/pipelines/base.py` (NEW)

```python
"""
Abstract base class for all pipelines.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator

from src.session.models import Session, ScopeContext


class Pipeline(ABC):
    """
    Abstract base for capability pipelines.

    Each pipeline handles a specific type of query (SQL, RAG, etc.)
    and is registered with the ScopeRegistry.
    """

    # Class attributes for registry
    scope_id: str                  # "inmate_data", "document_qa"
    scope_label: str               # "Inmate Data", "Documents"
    scope_icon: str                # "📊", "📄"
    scope_description: str         # "Query notes, inmates..."

    @abstractmethod
    async def process(
        self,
        question: str,
        session: Session,
        scope_context: ScopeContext,
    ) -> dict[str, Any]:
        """
        Process a question and return response.

        Args:
            question: User's question
            session: Full session state
            scope_context: Scope-specific working memory

        Returns:
            Response dict with at minimum:
            - summary: str
            - row_count: int (or equivalent)
        """
        pass

    @abstractmethod
    async def process_stream(
        self,
        question: str,
        session: Session,
        scope_context: ScopeContext,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """
        Stream response as SSE events.

        Yields dicts with:
        - {"event": "status", "data": "Processing..."}
        - {"event": "token", "data": "partial text"}
        - {"event": "result", "data": {full response}}
        - {"event": "error", "data": "error message"}
        """
        pass

    @abstractmethod
    async def health(self) -> dict[str, Any]:
        """
        Health check for this pipeline.

        Returns:
            {"status": "healthy"|"degraded"|"unhealthy", ...}
        """
        pass

    def get_welcome_message(self, is_returning: bool = False) -> str:
        """Get welcome message when entering this scope."""
        if is_returning:
            return f"Welcome back to {self.scope_label}. What would you like to know?"
        return f"Now helping with {self.scope_label}. {self.scope_description}"
```

### 1.3 Create Shared Exceptions

**File**: `src/shared/exceptions.py` (NEW)

```python
"""
Custom exceptions for InmateCopilot.
"""


class InmateCopilotError(Exception):
    """Base exception for all InmateCopilot errors."""
    pass


class PipelineError(InmateCopilotError):
    """Error within a pipeline."""
    def __init__(self, message: str, pipeline: str, recoverable: bool = True):
        super().__init__(message)
        self.pipeline = pipeline
        self.recoverable = recoverable


class ValidationError(InmateCopilotError):
    """Input validation failed."""
    pass


class ScopeError(InmateCopilotError):
    """Scope-related error (invalid scope, no active scope, etc.)."""
    pass


class SessionError(InmateCopilotError):
    """Session not found or corrupted."""
    pass


class TenantError(InmateCopilotError):
    """Tenant not found or access denied."""
    pass


class DocumentError(PipelineError):
    """Document pipeline specific errors."""
    def __init__(self, message: str, doc_id: str | None = None):
        super().__init__(message, pipeline="document_qa")
        self.doc_id = doc_id
```

### 1.4 Update Config

**File**: `src/shared/config.py` (MODIFY)

Add to existing file:

```python
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
DEFAULT_SCOPE: str | None = os.environ.get("DEFAULT_SCOPE", None)  # None = show options
SCOPE_SWITCH_COOLDOWN: int = int(os.environ.get("SCOPE_SWITCH_COOLDOWN", "0"))  # seconds
```

---

## Phase 2: Orchestrator Layer

### 2.1 Create Scope Registry

**File**: `src/orchestrator/scope_registry.py` (NEW)

```python
"""
Registry of available pipeline scopes.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Type
from collections import defaultdict

from src.pipelines.base import Pipeline
from src.shared.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ScopeDefinition:
    """Metadata for a registered scope."""
    id: str
    label: str
    icon: str
    description: str
    category: str | None
    pipeline_class: Type[Pipeline]
    enabled: bool = True


class ScopeRegistry:
    """
    Central registry of all available pipeline scopes.

    Pipelines register themselves at import time via @register decorator.
    """

    _scopes: dict[str, ScopeDefinition] = {}
    _instances: dict[str, Pipeline] = {}

    @classmethod
    def register(cls, scope: ScopeDefinition) -> None:
        """Register a scope definition."""
        cls._scopes[scope.id] = scope
        logger.info("Registered scope: %s (%s)", scope.id, scope.label)

    @classmethod
    def get(cls, scope_id: str) -> Pipeline:
        """Get or create pipeline instance for a scope."""
        if scope_id not in cls._scopes:
            raise ValueError(f"Unknown scope: {scope_id}")

        if scope_id not in cls._instances:
            definition = cls._scopes[scope_id]
            if not definition.enabled:
                raise ValueError(f"Scope disabled: {scope_id}")
            cls._instances[scope_id] = definition.pipeline_class()
            logger.info("Instantiated pipeline: %s", scope_id)

        return cls._instances[scope_id]

    @classmethod
    def get_definition(cls, scope_id: str) -> ScopeDefinition | None:
        """Get scope definition without instantiating."""
        return cls._scopes.get(scope_id)

    @classmethod
    def get_all(cls, include_disabled: bool = False) -> list[ScopeDefinition]:
        """Get all registered scopes."""
        return [
            s for s in cls._scopes.values()
            if include_disabled or s.enabled
        ]

    @classmethod
    def get_by_category(cls) -> dict[str, list[ScopeDefinition]]:
        """Get scopes grouped by category."""
        result = defaultdict(list)
        for scope in cls.get_all():
            result[scope.category or "Other"].append(scope)
        return dict(result)

    @classmethod
    def is_valid_scope(cls, scope_id: str) -> bool:
        """Check if scope exists and is enabled."""
        defn = cls._scopes.get(scope_id)
        return defn is not None and defn.enabled

    @classmethod
    def get_options_for_api(cls) -> list[dict]:
        """Get scope options formatted for API response."""
        return [
            {
                "id": s.id,
                "label": s.label,
                "icon": s.icon,
                "description": s.description,
                "category": s.category,
            }
            for s in cls.get_all()
        ]


def register_pipeline(
    scope_id: str,
    label: str,
    icon: str,
    description: str,
    category: str | None = None,
    enabled: bool = True,
):
    """
    Decorator to register a pipeline class.

    Usage:
        @register_pipeline("document_qa", "Documents", "📄", "Search docs")
        class DocumentQAPipeline(Pipeline):
            ...
    """
    def decorator(cls: Type[Pipeline]) -> Type[Pipeline]:
        cls.scope_id = scope_id
        cls.scope_label = label
        cls.scope_icon = icon
        cls.scope_description = description

        ScopeRegistry.register(ScopeDefinition(
            id=scope_id,
            label=label,
            icon=icon,
            description=description,
            category=category,
            pipeline_class=cls,
            enabled=enabled,
        ))
        return cls
    return decorator
```

### 2.2 Create State Machine

**File**: `src/orchestrator/state_machine.py` (NEW)

```python
"""
Scope state machine for guided conversation flow.
"""

from __future__ import annotations
from typing import Any

from src.session.models import Session, ConversationTurn, ScopeContext
from src.orchestrator.scope_registry import ScopeRegistry
from src.orchestrator.cross_scope import CrossScopeHandler
from src.memory.ltm.conversation_store import ConversationStore
from src.shared.logger import get_logger
from src.shared.exceptions import ScopeError

logger = get_logger(__name__)


class ScopeStateMachine:
    """
    Manages scope state and transitions.

    States:
        NO_SCOPE: No active scope, show options
        SCOPE_ACTIVE: Processing within a scope

    Transitions:
        select_scope: NO_SCOPE → SCOPE_ACTIVE
        switch_scope: SCOPE_ACTIVE → SCOPE_ACTIVE (different scope)
        clear_scope: SCOPE_ACTIVE → NO_SCOPE
    """

    def __init__(self, conversation_store: ConversationStore):
        self._conversation_store = conversation_store
        self._cross_scope = CrossScopeHandler()

    async def handle_message(
        self,
        message: str,
        session: Session,
    ) -> dict[str, Any]:
        """
        Main entry point for message handling.

        Returns response dict or routes to appropriate pipeline.
        """
        # 1. Check cross-scope handlers (greetings, recall, help)
        cross_scope_response = self._cross_scope.handle(message, session)
        if cross_scope_response:
            return cross_scope_response

        # 2. No active scope? Prompt for selection
        if session.active_scope is None:
            return self._prompt_scope_selection(message, session)

        # 3. Route to active pipeline
        return await self._dispatch_to_pipeline(message, session)

    def select_scope(self, scope_id: str, session: Session) -> dict[str, Any]:
        """
        User selected a scope (clicked option block).

        Returns welcome message for the scope.
        """
        if not ScopeRegistry.is_valid_scope(scope_id):
            raise ScopeError(f"Invalid scope: {scope_id}")

        previous_scope = session.active_scope
        is_returning = scope_id in session.scope_contexts

        # Switch scope (preserves previous context)
        scope_context = session.switch_scope(scope_id)

        # Get pipeline welcome
        pipeline = ScopeRegistry.get(scope_id)
        welcome = pipeline.get_welcome_message(is_returning)

        # If returning, add context reminder
        if is_returning and scope_context.recent_queries:
            last_query = scope_context.recent_queries[-1]
            welcome = (
                f"Welcome back to {pipeline.scope_label}. "
                f"Last time you asked: \"{last_query[:50]}...\" "
                f"Continue from there or ask something new!"
            )

        logger.info(
            "Scope selected: %s (previous: %s, returning: %s)",
            scope_id, previous_scope, is_returning
        )

        return {
            "message": welcome,
            "scope": scope_id,
            "previous_scope": previous_scope,
            "is_scope_change": True,
        }

    def get_scope_options(self, session: Session) -> dict[str, Any]:
        """Get available scope options for UI."""
        options = ScopeRegistry.get_options_for_api()

        # Mark current scope if any
        for opt in options:
            opt["is_current"] = opt["id"] == session.active_scope
            opt["is_visited"] = opt["id"] in session.scope_contexts

        return {
            "options": options,
            "current_scope": session.active_scope,
        }

    async def _dispatch_to_pipeline(
        self,
        message: str,
        session: Session,
    ) -> dict[str, Any]:
        """Dispatch to the active pipeline."""
        pipeline = ScopeRegistry.get(session.active_scope)
        scope_context = session.get_scope_context()

        response = await pipeline.process(message, session, scope_context)

        # Update scope context
        scope_context.add_query(message)

        # Tag response with scope
        response["scope"] = session.active_scope

        return response

    async def dispatch_stream(
        self,
        message: str,
        session: Session,
    ):
        """Dispatch to pipeline with streaming."""
        if session.active_scope is None:
            yield {
                "event": "error",
                "data": "Please select a scope first."
            }
            return

        pipeline = ScopeRegistry.get(session.active_scope)
        scope_context = session.get_scope_context()

        async for event in pipeline.process_stream(message, session, scope_context):
            yield event

        # Update scope context after completion
        scope_context.add_query(message)

    def _prompt_scope_selection(
        self,
        message: str,
        session: Session,
    ) -> dict[str, Any]:
        """Prompt user to select a scope."""
        options = ScopeRegistry.get_options_for_api()

        # Check if user typed something that looks like an option
        message_lower = message.lower()
        for opt in options:
            if opt["id"] in message_lower or opt["label"].lower() in message_lower:
                # Auto-select if user typed the scope name
                return self.select_scope(opt["id"], session)

        return {
            "message": (
                "I'd love to help with that! Please select an option "
                "so I know how to assist you."
            ),
            "requires_scope": True,
            "options": options,
        }
```

### 2.3 Create Cross-Scope Handler

**File**: `src/orchestrator/cross_scope.py` (NEW)

```python
"""
Handles scope-agnostic interactions (greetings, recall, help).
"""

from __future__ import annotations
import re
from typing import Any

from src.session.models import Session
from src.orchestrator.scope_registry import ScopeRegistry
from src.shared.config import BOT_NAME


class CrossScopeHandler:
    """
    Handles messages that don't require a specific scope.

    - Greetings: "Hello", "Hi Sarah"
    - Help/Capabilities: "What can you do?"
    - Recall: "What did I ask earlier?"
    - Farewells: "Goodbye", "Thanks"
    """

    GREETING_PATTERNS = [
        r"^(hi|hello|hey|good\s+(morning|afternoon|evening))(\s|!|\.|$)",
        r"^(yo|sup|howdy)(\s|!|\.|$)",
    ]

    FAREWELL_PATTERNS = [
        r"^(bye|goodbye|see\s+you|thanks?|thank\s+you)(\s|!|\.|$)",
        r"^(that'?s?\s+all|done|exit|quit)(\s|!|\.|$)",
    ]

    HELP_PATTERNS = [
        r"(what\s+can\s+you\s+do|help|capabilities)",
        r"(how\s+do\s+(you|i)\s+use|how\s+does\s+this\s+work)",
    ]

    RECALL_PATTERNS = [
        r"(what\s+did\s+i\s+ask|what\s+was\s+my|my\s+(earlier|previous|last)\s+question)",
        r"(repeat\s+that|what\s+have\s+we\s+discussed)",
        r"(show\s+my\s+history|conversation\s+history)",
    ]

    def handle(self, message: str, session: Session) -> dict[str, Any] | None:
        """
        Check if message is cross-scope and handle if so.

        Returns None if message should be routed to pipeline.
        """
        message_lower = message.lower().strip()

        if self._is_greeting(message_lower):
            return self._handle_greeting(session)

        if self._is_farewell(message_lower):
            return self._handle_farewell(session)

        if self._is_help(message_lower):
            return self._handle_help(session)

        if self._is_recall(message_lower):
            return self._handle_recall(message_lower, session)

        return None

    def _is_greeting(self, message: str) -> bool:
        return any(re.search(p, message, re.I) for p in self.GREETING_PATTERNS)

    def _is_farewell(self, message: str) -> bool:
        return any(re.search(p, message, re.I) for p in self.FAREWELL_PATTERNS)

    def _is_help(self, message: str) -> bool:
        return any(re.search(p, message, re.I) for p in self.HELP_PATTERNS)

    def _is_recall(self, message: str) -> bool:
        return any(re.search(p, message, re.I) for p in self.RECALL_PATTERNS)

    def _handle_greeting(self, session: Session) -> dict[str, Any]:
        """Respond to greeting with optional scope prompt."""
        options = ScopeRegistry.get_options_for_api()

        if session.active_scope:
            scope = ScopeRegistry.get_definition(session.active_scope)
            return {
                "message": f"Hi there! I'm currently helping you with {scope.label}. What would you like to know?",
                "is_greeting": True,
                "scope": session.active_scope,
            }

        return {
            "message": f"Hi! I'm {BOT_NAME}. What would you like help with today?",
            "is_greeting": True,
            "requires_scope": True,
            "options": options,
        }

    def _handle_farewell(self, session: Session) -> dict[str, Any]:
        """Respond to farewell."""
        turn_count = len([t for t in session.turns if t.role == "user"])

        if turn_count > 0:
            return {
                "message": f"Goodbye! We covered {turn_count} questions today. Come back anytime!",
                "is_farewell": True,
            }

        return {
            "message": "Goodbye! Feel free to come back whenever you need help.",
            "is_farewell": True,
        }

    def _handle_help(self, session: Session) -> dict[str, Any]:
        """Explain capabilities."""
        options = ScopeRegistry.get_options_for_api()

        lines = [f"I'm {BOT_NAME}, your assistant. Here's what I can help with:\n"]
        for opt in options:
            lines.append(f"  {opt['icon']} **{opt['label']}**: {opt['description']}")

        if session.active_scope:
            lines.append(f"\nYou're currently in **{session.active_scope}**. Use the Switch button to change.")
        else:
            lines.append("\nSelect an option above to get started!")

        return {
            "message": "\n".join(lines),
            "is_help": True,
            "options": options if not session.active_scope else None,
        }

    def _handle_recall(self, message: str, session: Session) -> dict[str, Any]:
        """Recall conversation history."""
        # Check if asking about specific scope
        scope_mentioned = None
        for opt in ScopeRegistry.get_all():
            if opt.id in message or opt.label.lower() in message:
                scope_mentioned = opt.id
                break

        if scope_mentioned:
            turns = session.get_turns_for_scope(scope_mentioned)
            scope_label = ScopeRegistry.get_definition(scope_mentioned).label
        elif "all" in message:
            turns = session.turns
            scope_label = "all scopes"
        else:
            # Default to current scope or all
            turns = session.get_turns_for_scope() if session.active_scope else session.turns
            scope_label = (
                ScopeRegistry.get_definition(session.active_scope).label
                if session.active_scope else "this session"
            )

        user_turns = [t for t in turns if t.role == "user"]

        if not user_turns:
            return {
                "message": f"No questions yet in {scope_label}. What would you like to know?",
                "is_recall": True,
            }

        lines = [f"Here's what you've asked in {scope_label}:\n"]
        for i, turn in enumerate(user_turns[-10:], 1):
            lines.append(f"  {i}. {turn.content}")

        if len(user_turns) > 10:
            lines.append(f"\n... and {len(user_turns) - 10} more.")

        lines.append("\nWant me to revisit any of these?")

        return {
            "message": "\n".join(lines),
            "is_recall": True,
            "query_count": len(user_turns),
        }
```

---

## Phase 3: Migrate Inmate Pipeline

### 3.1 Create Pipeline Wrapper

**File**: `src/pipelines/inmate_data/pipeline.py` (NEW)

```python
"""
Inmate Data Pipeline — wraps existing Vanna/SQL functionality.
"""

from __future__ import annotations
from typing import Any, AsyncGenerator

from src.pipelines.base import Pipeline
from src.orchestrator.scope_registry import register_pipeline
from src.session.models import Session, ScopeContext

# Import existing modules (will be moved to this package)
from src.pipelines.inmate_data.vanna_agent import AgentPipeline as VannaAgentPipeline
from src.memory.ltm.conversation_store import ConversationStore, create_conversation_store
from src.memory.stm.session_store import SessionStore, create_session_store


@register_pipeline(
    scope_id="inmate_data",
    label="Inmate Data",
    icon="📊",
    description="Query notes, inmates, officers, and facilities",
    category="Data & Analytics",
)
class InmateDataPipeline(Pipeline):
    """
    Inmate Data Pipeline using Vanna for text-to-SQL.

    Wraps the existing AgentPipeline with the new Pipeline interface.
    """

    def __init__(self):
        self._session_store = create_session_store()
        self._conversation_store = create_conversation_store()
        self._vanna_pipeline = VannaAgentPipeline(
            session_store=self._session_store,
            conversation_store=self._conversation_store,
        )

    async def process(
        self,
        question: str,
        session: Session,
        scope_context: ScopeContext,
    ) -> dict[str, Any]:
        """Process a data query."""
        from src.tenant.tenant_router import resolve_tenant

        # Get tenant context
        tenant = resolve_tenant(session.customer_key)

        # Use existing Vanna pipeline
        response = await self._vanna_pipeline.process_question(
            question=question,
            session=session,
            tenant=tenant,
        )

        # Update scope context with entities
        self._extract_entities(response, scope_context)

        return response

    async def process_stream(
        self,
        question: str,
        session: Session,
        scope_context: ScopeContext,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a data query response."""
        from src.tenant.tenant_router import resolve_tenant

        tenant = resolve_tenant(session.customer_key)

        async for event in self._vanna_pipeline.process_question_stream(
            question=question,
            session=session,
            tenant=tenant,
        ):
            yield event

        # Update scope context after completion
        # (extracted from final result event)

    async def health(self) -> dict[str, Any]:
        """Check pipeline health."""
        from src.agent.vanna_agent import get_llm_service, get_agent_memory

        llm_ok = get_llm_service() is not None
        memory_ok = get_agent_memory() is not None

        return {
            "status": "healthy" if (llm_ok and memory_ok) else "degraded",
            "llm": "ok" if llm_ok else "unavailable",
            "memory": "ok" if memory_ok else "unavailable",
        }

    def _extract_entities(self, response: dict, scope_context: ScopeContext) -> None:
        """Extract entities (inmate names, etc.) from response for context."""
        import re

        summary = response.get("summary", "")

        # Extract inmate names (bold pattern)
        names = re.findall(r"\*\*([A-Z][a-z]+ [A-Z][a-z]+)\*\*", summary)
        if names:
            scope_context.update_entity("inmate_name", names[0])

        # Extract facility names
        facilities = re.findall(r"(?:Dorm|Facility|Building)\s+([A-Z0-9]+)", summary)
        if facilities:
            scope_context.update_entity("facility", facilities[0])
```

### 3.2 Move Existing Files

Move these files to `src/pipelines/inmate_data/`:

| From | To |
|------|-----|
| `src/agent/vanna_agent.py` | `src/pipelines/inmate_data/vanna_agent.py` |
| `src/agent/prompt_builder.py` | `src/pipelines/inmate_data/prompt_builder.py` |
| `src/agent/response_formatter.py` | `src/pipelines/inmate_data/response_formatter.py` |
| `src/agent/intent_engine.py` | `src/pipelines/inmate_data/intent_engine.py` |
| `src/agent/sarah_brain.py` | `src/pipelines/inmate_data/domain_responses.py` |
| `src/guardrails/question_validator.py` | `src/pipelines/inmate_data/guardrails/question_validator.py` |
| `src/guardrails/sql_validator.py` | `src/pipelines/inmate_data/guardrails/sql_validator.py` |

### 3.3 Create Backward Compatibility Shims

**File**: `src/agent/__init__.py` (MODIFY)

```python
"""
DEPRECATED: This module is deprecated.

Use src.pipelines.inmate_data instead.

Keeping for backward compatibility.
"""

import warnings

# Re-export from new location
from src.pipelines.inmate_data.vanna_agent import (
    AgentPipeline,
    generate_sql_via_llm,
    generate_sql_via_llm_sync,
    get_llm_service,
    get_agent_memory,
)
from src.pipelines.inmate_data.intent_engine import (
    Intent,
    IntentResult,
    classify_intent,
)
from src.pipelines.inmate_data.prompt_builder import build_sql_context
from src.pipelines.inmate_data.response_formatter import (
    format_data_response,
    format_analytics_response,
    format_empty_response,
    format_error_response,
)
from src.pipelines.inmate_data.domain_responses import generate_response

warnings.warn(
    "src.agent is deprecated. Use src.pipelines.inmate_data instead.",
    DeprecationWarning,
    stacklevel=2,
)
```

---

## Phase 4: Document QA Pipeline

### 4.1 Document Store

**File**: `src/pipelines/document_qa/documents/store.py` (NEW)

```python
"""
ChromaDB-backed document store with tenant isolation.
"""

from __future__ import annotations
import uuid
from typing import Any
from pathlib import Path

import chromadb
from chromadb.config import Settings

from src.shared.config import DOC_CHROMA_DIR
from src.shared.logger import get_logger

logger = get_logger(__name__)


class TenantDocumentStore:
    """
    ChromaDB store with tenant isolation.

    Each tenant gets a separate collection: docs_{customer_key}
    """

    def __init__(
        self,
        customer_key: str,
        persist_dir: str | None = None,
    ):
        self._customer_key = customer_key
        self._collection_name = f"docs_{customer_key}"

        persist_dir = persist_dir or DOC_CHROMA_DIR
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )

        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine", "tenant": customer_key},
        )

        logger.info("Document store: %s (%d docs)", self._collection_name, self.count())

    def add_chunks(
        self,
        texts: list[str],
        embeddings: list[list[float]],
        metadata: list[dict[str, Any]],
    ) -> list[str]:
        """Add document chunks with embeddings."""
        ids = [str(uuid.uuid4()) for _ in texts]

        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadata,
        )

        return ids

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: dict | None = None,
    ) -> list[dict[str, Any]]:
        """Search for similar chunks."""
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        formatted = []
        for i in range(len(results["ids"][0])):
            formatted.append({
                "id": results["ids"][0][i],
                "text": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "score": 1 - results["distances"][0][i],  # Distance to similarity
            })

        return formatted

    def delete_document(self, doc_id: str) -> int:
        """Delete all chunks for a document."""
        # Find chunks with this doc_id
        results = self._collection.get(
            where={"doc_id": doc_id},
            include=[],
        )

        if results["ids"]:
            self._collection.delete(ids=results["ids"])
            return len(results["ids"])
        return 0

    def count(self) -> int:
        """Total chunks in collection."""
        return self._collection.count()

    def list_documents(self) -> list[dict[str, Any]]:
        """List unique documents."""
        results = self._collection.get(include=["metadatas"])

        docs = {}
        for meta in results["metadatas"]:
            doc_id = meta.get("doc_id")
            if doc_id and doc_id not in docs:
                docs[doc_id] = {
                    "doc_id": doc_id,
                    "filename": meta.get("filename"),
                    "file_type": meta.get("file_type"),
                    "indexed_at": meta.get("indexed_at"),
                    "chunk_count": 0,
                }
            if doc_id:
                docs[doc_id]["chunk_count"] += 1

        return list(docs.values())
```

### 4.2 Retriever (Hybrid Search)

**File**: `src/pipelines/document_qa/retriever.py` (NEW)

```python
"""
Hybrid retriever: Semantic + BM25 with RRF fusion.
"""

from __future__ import annotations
import re
from typing import Any

from openai import AsyncOpenAI
from rank_bm25 import BM25Okapi

from src.pipelines.document_qa.documents.store import TenantDocumentStore
from src.session.models import ScopeContext
from src.shared.config import (
    OPENAI_API_KEY,
    DOC_EMBEDDING_MODEL,
    DOC_RETRIEVAL_TOP_K,
    DOC_HYBRID_SEARCH,
)
from src.shared.logger import get_logger

logger = get_logger(__name__)


class DocumentRetriever:
    """
    Retrieves relevant document chunks via hybrid search.

    Combines:
    - Semantic search (ChromaDB embeddings)
    - BM25 keyword search
    - Reciprocal Rank Fusion (RRF)
    """

    def __init__(self):
        self._openai = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self._embedding_model = DOC_EMBEDDING_MODEL
        self._bm25_indices: dict[str, BM25Okapi] = {}
        self._bm25_docs: dict[str, list[dict]] = {}

    async def retrieve(
        self,
        question: str,
        store: TenantDocumentStore,
        top_k: int | None = None,
        context: ScopeContext | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve relevant chunks for a question."""
        top_k = top_k or DOC_RETRIEVAL_TOP_K

        # Get query embedding
        embedding = await self._get_embedding(question)

        # Semantic search
        semantic_results = store.search(
            query_embedding=embedding,
            top_k=top_k * 4,  # Get more for fusion
        )

        if not DOC_HYBRID_SEARCH:
            return semantic_results[:top_k]

        # BM25 search
        bm25_results = self._bm25_search(question, store, top_k * 4)

        # RRF fusion
        fused = self._reciprocal_rank_fusion(
            semantic_results,
            bm25_results,
            top_k,
        )

        # Context-aware boosting
        if context and context.recent_entities.get("last_docs"):
            fused = self._boost_recent_docs(
                fused,
                context.recent_entities["last_docs"],
            )

        # Deduplicate
        fused = self._deduplicate(fused)

        return fused[:top_k]

    async def _get_embedding(self, text: str) -> list[float]:
        """Generate embedding for text."""
        response = await self._openai.embeddings.create(
            model=self._embedding_model,
            input=text,
        )
        return response.data[0].embedding

    def _bm25_search(
        self,
        question: str,
        store: TenantDocumentStore,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """BM25 keyword search."""
        tenant = store._customer_key

        # Build/update BM25 index if needed
        if tenant not in self._bm25_indices:
            self._build_bm25_index(store)

        # Tokenize query
        tokens = self._tokenize(question)

        # Score documents
        scores = self._bm25_indices[tenant].get_scores(tokens)

        # Rank
        ranked = sorted(
            enumerate(scores),
            key=lambda x: x[1],
            reverse=True,
        )[:top_k]

        # Return with scores
        results = []
        for idx, score in ranked:
            if score > 0:
                doc = self._bm25_docs[tenant][idx].copy()
                doc["bm25_score"] = float(score)
                results.append(doc)

        return results

    def _build_bm25_index(self, store: TenantDocumentStore) -> None:
        """Build BM25 index for a tenant's documents."""
        tenant = store._customer_key

        # Get all documents
        results = store._collection.get(include=["documents", "metadatas"])

        docs = []
        tokenized = []

        for i, (doc, meta) in enumerate(zip(results["documents"], results["metadatas"])):
            docs.append({
                "id": results["ids"][i],
                "text": doc,
                "metadata": meta,
                "score": 0,  # Will be filled during search
            })
            tokenized.append(self._tokenize(doc))

        self._bm25_docs[tenant] = docs
        self._bm25_indices[tenant] = BM25Okapi(tokenized)

        logger.info("Built BM25 index for %s: %d docs", tenant, len(docs))

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenizer for BM25."""
        return re.findall(r'\w+', text.lower())

    def _reciprocal_rank_fusion(
        self,
        semantic: list[dict],
        keyword: list[dict],
        top_k: int,
        k: int = 60,
    ) -> list[dict]:
        """
        Merge two ranked lists with RRF.

        RRF score = sum(1 / (k + rank)) for each list
        """
        scores = {}
        docs_by_id = {}

        # Score semantic results
        for rank, doc in enumerate(semantic):
            doc_id = doc["id"]
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
            docs_by_id[doc_id] = doc

        # Score keyword results
        for rank, doc in enumerate(keyword):
            doc_id = doc["id"]
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
            if doc_id not in docs_by_id:
                docs_by_id[doc_id] = doc

        # Sort by RRF score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Build result list
        results = []
        for doc_id, rrf_score in ranked[:top_k]:
            doc = docs_by_id[doc_id].copy()
            doc["rrf_score"] = rrf_score
            results.append(doc)

        return results

    def _boost_recent_docs(
        self,
        results: list[dict],
        recent_docs: list[str],
        boost: float = 0.1,
    ) -> list[dict]:
        """Boost scores for chunks from recently accessed documents."""
        for r in results:
            if r["metadata"].get("filename") in recent_docs:
                r["score"] = min(1.0, r.get("score", 0) + boost)

        return sorted(results, key=lambda x: x.get("score", 0), reverse=True)

    def _deduplicate(
        self,
        results: list[dict],
        threshold: float = 0.8,
    ) -> list[dict]:
        """Remove near-duplicate chunks."""
        unique = []
        seen_texts = []

        for r in results:
            text = r["text"]
            is_duplicate = False

            for seen in seen_texts:
                if self._text_overlap(text, seen) > threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique.append(r)
                seen_texts.append(text)

        return unique

    def _text_overlap(self, text1: str, text2: str) -> float:
        """Calculate word overlap ratio."""
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union
```

### 4.3 Document Pipeline

**File**: `src/pipelines/document_qa/pipeline.py` (NEW)

```python
"""
Document Q&A Pipeline using RAG.
"""

from __future__ import annotations
from typing import Any, AsyncGenerator

from src.pipelines.base import Pipeline
from src.orchestrator.scope_registry import register_pipeline
from src.session.models import Session, ScopeContext
from src.pipelines.document_qa.documents.store import TenantDocumentStore
from src.pipelines.document_qa.retriever import DocumentRetriever
from src.pipelines.document_qa.synthesizer import ResponseSynthesizer
from src.shared.logger import get_logger

logger = get_logger(__name__)


@register_pipeline(
    scope_id="document_qa",
    label="Documents",
    icon="📄",
    description="Search manuals, guides, and policies",
    category="Information",
)
class DocumentQAPipeline(Pipeline):
    """
    Document Q&A Pipeline using RAG.

    Flow:
      1. Validate question
      2. Retrieve relevant chunks (hybrid search)
      3. Synthesize answer (LLM)
      4. Format response with sources
    """

    def __init__(self):
        self._stores: dict[str, TenantDocumentStore] = {}
        self._retriever = DocumentRetriever()
        self._synthesizer = ResponseSynthesizer()

    def _get_store(self, customer_key: str) -> TenantDocumentStore:
        """Get or create tenant-specific document store."""
        if customer_key not in self._stores:
            self._stores[customer_key] = TenantDocumentStore(customer_key)
        return self._stores[customer_key]

    async def process(
        self,
        question: str,
        session: Session,
        scope_context: ScopeContext,
    ) -> dict[str, Any]:
        """Process a document question."""
        store = self._get_store(session.customer_key)

        # Check if any documents indexed
        if store.count() == 0:
            return {
                "summary": "No documents have been indexed yet. Please contact your administrator to add documents.",
                "sources": [],
                "row_count": 0,
            }

        # Retrieve relevant chunks
        chunks = await self._retriever.retrieve(
            question=question,
            store=store,
            context=scope_context,
        )

        if not chunks:
            return {
                "summary": (
                    "I couldn't find any relevant information in the documents. "
                    "Try rephrasing your question or check if the topic is covered."
                ),
                "sources": [],
                "row_count": 0,
            }

        # Synthesize response
        response = await self._synthesizer.synthesize(
            question=question,
            chunks=chunks,
        )

        # Update scope context
        scope_context.add_query(question)
        scope_context.update_entity(
            "last_docs",
            [c["metadata"].get("filename") for c in chunks[:3]],
        )

        return {
            "summary": response["answer"],
            "sources": response["sources"],
            "row_count": len(chunks),
            "chunks_used": len(chunks),
        }

    async def process_stream(
        self,
        question: str,
        session: Session,
        scope_context: ScopeContext,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream document QA response."""
        yield {"event": "status", "data": "Searching documents..."}

        store = self._get_store(session.customer_key)

        if store.count() == 0:
            yield {"event": "error", "data": "No documents indexed."}
            return

        chunks = await self._retriever.retrieve(
            question=question,
            store=store,
            context=scope_context,
        )

        if not chunks:
            yield {"event": "result", "data": {
                "summary": "No relevant documents found.",
                "sources": [],
            }}
            return

        yield {"event": "status", "data": f"Found {len(chunks)} relevant sections..."}

        async for event in self._synthesizer.synthesize_stream(question, chunks):
            yield event

        # Update context
        scope_context.add_query(question)

    async def health(self) -> dict[str, Any]:
        """Health check."""
        return {
            "status": "healthy",
            "stores_loaded": len(self._stores),
        }
```

---

## Phase 5: API Integration

### 5.1 Update Routes

**File**: `src/api/routes.py` (MODIFY)

Add new endpoints:

```python
# Add these imports
from src.orchestrator.state_machine import ScopeStateMachine
from src.orchestrator.scope_registry import ScopeRegistry

# Add these endpoints

@app.post("/scope/select")
async def select_scope(
    request: ScopeSelectRequest,
    session_store = Depends(get_session_store),
    conversation_store = Depends(get_conversation_store),
):
    """Select a scope (user clicked option block)."""
    session = session_store.get(request.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    state_machine = ScopeStateMachine(conversation_store)
    response = state_machine.select_scope(request.scope, session)

    session_store.save(session)

    return response


@app.get("/scope/options")
async def get_scope_options(
    session_id: str = Query(...),
    session_store = Depends(get_session_store),
):
    """Get available scope options."""
    session = session_store.get(session_id) or Session(...)

    state_machine = ScopeStateMachine(None)
    return state_machine.get_scope_options(session)


@app.get("/pipelines/health/{scope}")
async def pipeline_health(scope: str):
    """Health check for a specific pipeline."""
    if not ScopeRegistry.is_valid_scope(scope):
        raise HTTPException(404, f"Unknown scope: {scope}")

    pipeline = ScopeRegistry.get(scope)
    return await pipeline.health()
```

### 5.2 Update Schemas

**File**: `src/api/schemas.py` (MODIFY)

```python
# Add these schemas

class ScopeSelectRequest(BaseModel):
    session_id: str
    scope: str


class ScopeOption(BaseModel):
    id: str
    label: str
    icon: str
    description: str
    category: str | None = None
    is_current: bool = False
    is_visited: bool = False


class ScopeOptionsResponse(BaseModel):
    options: list[ScopeOption]
    current_scope: str | None = None
```

---

## Phase 6: Testing & Validation

### 6.1 Test Structure

```
tests/
├── unit/
│   ├── test_session_models.py
│   ├── test_scope_registry.py
│   └── test_state_machine.py
├── integration/
│   ├── test_inmate_pipeline.py
│   ├── test_document_pipeline.py
│   └── test_scope_switching.py
└── e2e/
    ├── test_full_flow.py
    └── test_api_endpoints.py
```

### 6.2 Verification Checklist

- [ ] Unit tests pass: `pytest tests/unit/ -v`
- [ ] Pipeline tests pass: `pytest src/pipelines/ -v`
- [ ] Integration tests pass: `pytest tests/integration/ -v`
- [ ] E2E tests pass: `pytest tests/e2e/ -v`
- [ ] Load test: 100 concurrent users, P99 < 5s
- [ ] Manual testing: Full user journey through UI

---

## File-by-File Changes

### New Files

| File | Purpose |
|------|---------|
| `src/session/models.py` | Session, Turn, ScopeContext dataclasses |
| `src/pipelines/base.py` | Abstract Pipeline interface |
| `src/pipelines/inmate_data/pipeline.py` | InmateDataPipeline wrapper |
| `src/pipelines/document_qa/pipeline.py` | DocumentQAPipeline |
| `src/pipelines/document_qa/retriever.py` | Hybrid retriever |
| `src/pipelines/document_qa/synthesizer.py` | LLM synthesizer |
| `src/pipelines/document_qa/documents/store.py` | ChromaDB store |
| `src/pipelines/document_qa/documents/loader.py` | Document loaders |
| `src/pipelines/document_qa/documents/chunker.py` | Text chunker |
| `src/orchestrator/state_machine.py` | ScopeStateMachine |
| `src/orchestrator/scope_registry.py` | Pipeline registry |
| `src/orchestrator/cross_scope.py` | Cross-scope handlers |
| `src/shared/exceptions.py` | Custom exceptions |

### Modified Files

| File | Changes |
|------|---------|
| `src/api/routes.py` | Add scope endpoints, use orchestrator |
| `src/api/schemas.py` | Add scope-related schemas |
| `src/shared/config.py` | Add pipeline configs |
| `src/memory/conversation_store.py` | Add scope field to turns |

### Moved Files (with backward compat)

| From | To |
|------|-----|
| `src/agent/vanna_agent.py` | `src/pipelines/inmate_data/vanna_agent.py` |
| `src/agent/intent_engine.py` | `src/pipelines/inmate_data/intent_engine.py` |
| `src/agent/prompt_builder.py` | `src/pipelines/inmate_data/prompt_builder.py` |
| `src/agent/response_formatter.py` | `src/pipelines/inmate_data/response_formatter.py` |
| `src/agent/sarah_brain.py` | `src/pipelines/inmate_data/domain_responses.py` |
| `src/guardrails/*` | `src/pipelines/inmate_data/guardrails/*` |

---

## Migration Strategy

### Phase-by-Phase Deployment

1. **Phase 1-2**: Deploy foundation + orchestrator (no breaking changes)
2. **Phase 3**: Deploy migrated inmate pipeline (backward compat via shims)
3. **Phase 4**: Deploy document pipeline (new capability)
4. **Phase 5-6**: Deploy API changes (UI can adopt incrementally)

### Rollback Plan

- Each phase is independently reversible
- Feature flags for new functionality
- Original `src/agent/` kept as fallback

### Monitoring

- Track scope selection patterns
- Monitor pipeline latencies separately
- Alert on error rate per pipeline
