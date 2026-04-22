# InmateCopilot — System Architecture

**Version**: 2.0 (Guided Conversational Agent)
**Created**: 2026-03-19
**Status**: Design Complete

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [High-Level Architecture](#high-level-architecture)
3. [Component Architecture](#component-architecture)
4. [Data Flow Architecture](#data-flow-architecture)
5. [Infrastructure Architecture](#infrastructure-architecture)
6. [Design Decisions](#design-decisions)

---

## Executive Summary

InmateCopilot V2 transforms from a single-purpose SQL chatbot into a **guided multi-capability conversational agent**. Users explicitly select their intent (Inmate Data queries, Document search, Daily Activity checks, and future capabilities) and the system maintains strict scope isolation while preserving context.

### Key Architectural Principles

| Principle | Implementation |
|-----------|----------------|
| **Guided, Not Inferred** | User clicks to select scope; no AI guessing |
| **Scope Isolation** | Each pipeline operates independently; no cross-contamination |
| **Context Preservation** | Switching scopes preserves previous context for return |
| **Modular Pipelines** | Each capability is self-contained; easy to add new ones |
| **Multi-Tenant** | Strict data isolation per customer |

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                 CLIENT LAYER                                     │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         Chat Interface (UI)                               │   │
│  │  ┌─────────────┐  ┌─────────────────────────────────────────────────┐   │   │
│  │  │   Sarah     │  │              Chat Window                         │   │   │
│  │  │   Avatar    │  │  ┌───────────┐ ┌───────────┐ ┌───────────────┐ │   │   │
│  │  │  [Switch]   │  │  │📊 Inmate  │ │📄 Documents│ │📅 Daily       │ │   │   │
│  │  └─────────────┘  │  │   Data    │ │           │ │   Activity    │ │   │   │
│  │                   │  └───────────┘ └───────────┘ └───────────────┘ │   │   │
│  │                   │                                                   │   │   │
│  │                   │  [Conversation Thread with Scope Indicator]       │   │   │
│  │                   └─────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        │ HTTPS / WebSocket
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              API GATEWAY (ALB)                                   │
│                        Load Balancing, SSL Termination                          │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            APPLICATION LAYER                                     │
│  ┌───────────────────────────────────────────────────────────────────────────┐ │
│  │                        ECS Fargate Cluster                                 │ │
│  │                                                                            │ │
│  │  ┌──────────────────────────────────────────────────────────────────────┐ │ │
│  │  │                         FastAPI Application                           │ │ │
│  │  │                                                                       │ │ │
│  │  │  ┌─────────────────────────────────────────────────────────────────┐ │ │ │
│  │  │  │                    API Layer (routes.py)                         │ │ │ │
│  │  │  │   /chat  /chat/stream  /scope/select  /scope/options  /health   │ │ │ │
│  │  │  └─────────────────────────────┬───────────────────────────────────┘ │ │ │
│  │  │                                │                                      │ │ │
│  │  │  ┌─────────────────────────────▼───────────────────────────────────┐ │ │ │
│  │  │  │                     ORCHESTRATOR LAYER                           │ │ │ │
│  │  │  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │ │ │ │
│  │  │  │  │   Scope     │  │   Context    │  │    Pipeline            │  │ │ │ │
│  │  │  │  │   Manager   │──│   Manager    │──│    Dispatcher          │  │ │ │ │
│  │  │  │  │             │  │              │  │                        │  │ │ │ │
│  │  │  │  │ - Active    │  │ - Turn mgmt  │  │ - Route to pipeline    │  │ │ │ │
│  │  │  │  │   scope     │  │ - History    │  │ - Handle cross-scope   │  │ │ │ │
│  │  │  │  │ - Scope     │  │ - Recall     │  │ - Greetings/help       │  │ │ │ │
│  │  │  │  │   switch    │  │              │  │                        │  │ │ │ │
│  │  │  │  └─────────────┘  └──────────────┘  └────────────────────────┘  │ │ │ │
│  │  │  └─────────────────────────────┬───────────────────────────────────┘ │ │ │
│  │  │                                │                                      │ │ │
│  │  │  ┌─────────────────────────────▼───────────────────────────────────┐ │ │ │
│  │  │  │                      PIPELINE LAYER                              │ │ │ │
│  │  │  │                                                                  │ │ │ │
│  │  │  │  ┌────────────────────┐        ┌────────────────────┐           │ │ │ │
│  │  │  │  │  INMATE DATA       │        │  DOCUMENT QA       │           │ │ │ │
│  │  │  │  │  PIPELINE          │        │  PIPELINE          │           │ │ │ │
│  │  │  │  │  (Vanna SQL)       │        │  (RAG)             │           │ │ │ │
│  │  │  │  │                    │        │                    │           │ │ │ │
│  │  │  │  │ ┌────────────────┐ │        │ ┌────────────────┐ │           │ │ │ │
│  │  │  │  │ │ Intent Engine  │ │        │ │ Retriever      │ │           │ │ │ │
│  │  │  │  │ │ Prompt Builder │ │        │ │ (Hybrid Search)│ │           │ │ │ │
│  │  │  │  │ │ Vanna Agent    │ │        │ │ BM25 + Semantic│ │           │ │ │ │
│  │  │  │  │ │ SQL Validator  │ │        │ └────────────────┘ │           │ │ │ │
│  │  │  │  │ │ Response Fmt   │ │        │ ┌────────────────┐ │           │ │ │ │
│  │  │  │  │ └────────────────┘ │        │ │ Synthesizer    │ │           │ │ │ │
│  │  │  │  │                    │        │ │ (LLM Answer)   │ │           │ │ │ │
│  │  │  │  │ ┌────────────────┐ │        │ └────────────────┘ │           │ │ │ │
│  │  │  │  │ │ Guardrails     │ │        │ ┌────────────────┐ │           │ │ │ │
│  │  │  │  │ │ - Question Val │ │        │ │ Document Store │ │           │ │ │ │
│  │  │  │  │ │ - SQL Val      │ │        │ │ (ChromaDB)     │ │           │ │ │ │
│  │  │  │  │ │ - Filter Inj   │ │        │ │ Tenant-Isolated│ │           │ │ │ │
│  │  │  │  │ └────────────────┘ │        │ └────────────────┘ │           │ │ │ │
│  │  │  │  └────────────────────┘        └────────────────────┘           │ │ │ │
│  │  │  │                                                                  │ │ │ │
│  │  │  │  ┌────────────────────┐                                         │ │ │ │
│  │  │  │  │  DAILY ACTIVITY    │                                         │ │ │ │
│  │  │  │  │  PIPELINE          │                                         │ │ │ │
│  │  │  │  │  (Compliance)      │                                         │ │ │ │
│  │  │  │  │                    │                                         │ │ │ │
│  │  │  │  │ ┌────────────────┐ │                                         │ │ │ │
│  │  │  │  │ │ Activity Check │ │                                         │ │ │ │
│  │  │  │  │ │ Timetable Load │ │                                         │ │ │ │
│  │  │  │  │ │ DB Adapter     │ │                                         │ │ │ │
│  │  │  │  │ │ Response Fmt   │ │                                         │ │ │ │
│  │  │  │  │ └────────────────┘ │                                         │ │ │ │
│  │  │  │  │ Auto-execute on    │                                         │ │ │ │
│  │  │  │  │ scope selection    │                                         │ │ │ │
│  │  │  │  └────────────────────┘                                         │ │ │ │
│  │  │  │                                                                  │ │ │ │
│  │  │  │  ┌─────────────────────────────────────────────────────────────┐│ │ │ │
│  │  │  │  │                    FUTURE PIPELINES                         ││ │ │ │
│  │  │  │  │   [Analytics]  [Shift Planning]  [Risk Assessment]  [...]   ││ │ │ │
│  │  │  │  └─────────────────────────────────────────────────────────────┘│ │ │ │
│  │  │  └─────────────────────────────────────────────────────────────────┘ │ │ │
│  │  │                                                                       │ │ │
│  │  └───────────────────────────────────────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
         ┌──────────────────────────────┼──────────────────────────────┐
         │                              │                              │
         ▼                              ▼                              ▼
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│   SESSION LAYER     │    │   MEMORY LAYER      │    │   DATA LAYER        │
│                     │    │                     │    │                     │
│  ┌───────────────┐  │    │  ┌───────────────┐  │    │  ┌───────────────┐  │
│  │    Valkey     │  │    │  │   DynamoDB    │  │    │  │ Aurora MySQL  │  │
│  │  (ElastiCache)│  │    │  │  (History)    │  │    │  │ (Inmate Data) │  │
│  │               │  │    │  │               │  │    │  │               │  │
│  │ - Session     │  │    │  │ - All turns   │  │    │  │ - dg_notes    │  │
│  │ - Scope ctx   │  │    │  │ - Scope tags  │  │    │  │ - dg_tags     │  │
│  │ - Turns (15)  │  │    │  │ - Analytics   │  │    │  │ - dg_user     │  │
│  │ - TTL: 1hr    │  │    │  │ - TTL: 90d    │  │    │  │ - etc.        │  │
│  └───────────────┘  │    │  └───────────────┘  │    │  └───────────────┘  │
│                     │    │                     │    │                     │
│                     │    │  ┌───────────────┐  │    │  ┌───────────────┐  │
│                     │    │  │   ChromaDB    │  │    │  │   ChromaDB    │  │
│                     │    │  │ (Vanna Train) │  │    │  │ (Documents)   │  │
│                     │    │  │               │  │    │  │               │  │
│                     │    │  │ - SQL examples│  │    │  │ - Manuals     │  │
│                     │    │  │ - Schema docs │  │    │  │ - Policies    │  │
│                     │    │  │ - 321 pairs   │  │    │  │ - Per-tenant  │  │
│                     │    │  └───────────────┘  │    │  └───────────────┘  │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
```

---

## Component Architecture

### 1. API Layer

```
src/api/
├── routes.py           # FastAPI endpoints
├── handlers/
│   ├── chat_handler.py     # Main chat orchestration
│   └── scope_handler.py    # Scope selection/switching
├── schemas.py          # Pydantic models
└── middleware.py       # Auth, tenant extraction
```

**Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `POST /chat` | Unified chat | Routes to active pipeline |
| `POST /chat/stream` | SSE streaming | Token-by-token responses |
| `POST /scope/select` | Scope selection | User clicks option block |
| `GET /scope/options` | Available scopes | Returns scope metadata |
| `GET /health` | Health check | Pipeline status |
| `GET /session/{id}` | Session details | Debug/admin |

### 2. Orchestrator Layer

```
src/orchestrator/
├── __init__.py
├── state_machine.py    # ScopeStateMachine
├── scope_registry.py   # Pipeline registry
├── cross_scope.py      # Cross-scope detection/dispatch
└── persona.py          # Shared persona response builders
```

**Responsibilities:**

| Component | Responsibility |
|-----------|----------------|
| **ScopeStateMachine** | Track active scope, handle transitions |
| **ScopeRegistry** | Available pipelines, metadata, factory |
| **CrossScopeHandler** | Greetings, help, recall (scope-agnostic) |

### 3. Pipeline Layer

```
src/pipelines/
├── base.py             # Abstract Pipeline interface
├── inmate_data/        # Vanna SQL pipeline
│   ├── pipeline.py
│   ├── vanna_agent.py
│   ├── prompt_builder.py
│   ├── response_formatter.py
│   ├── guardrails/
│   │   ├── question_validator.py
│   │   └── sql_validator.py
│   └── tests/
├── document_qa/        # RAG pipeline
│   ├── pipeline.py
│   ├── retriever.py
│   ├── synthesizer.py
│   ├── documents/
│   │   ├── store.py
│   │   ├── loader.py
│   │   └── chunker.py
│   ├── guardrails/
│   │   └── validator.py
│   └── tests/
└── daily_activity/     # Daily Activity pipeline (Compliance)
    ├── pipeline.py         # DailyActivityPipeline (auto-execute)
    ├── activity_checker.py # Core activity comparison logic
    ├── db_adapter.py       # DB access via db_registry
    ├── timetable_loader.py # Timetable loading with fallback
    ├── response_formatter.py # Template-based summaries
    ├── process_timetable.py  # CSV to JSON utility
    ├── data/timetables/    # Timetable JSON files
    └── tests/
```

**Pipeline Interface:**

```python
class Pipeline(ABC):
    scope_id: str           # "inmate_data", "document_qa", "daily_activity"
    scope_label: str        # "Inmate Data", "Documents", "Daily Activity"
    scope_icon: str         # "📊", "📄", "📅"
    scope_description: str  # "Query notes, inmates..."
    supports_auto_execute: bool = False  # If True, auto-run on scope selection

    @abstractmethod
    async def process(self, question: str, session: Session, scope_context: ScopeContext) -> dict

    @abstractmethod
    async def process_stream(self, ...) -> AsyncGenerator[dict, None]

    @abstractmethod
    async def health(self) -> dict
```

### 4. Session Layer

```
src/session/
├── models.py           # Session, Turn, ScopeContext
├── session_manager.py  # CRUD operations
└── scope_context.py    # Scope-specific state
```

**Enhanced Session Model:**

```python
@dataclass
class Session:
    # Existing
    session_id: str
    customer_key: str
    user_id: str
    facility_ids: list[int]
    role: str
    display_name: str
    turns: list[ConversationTurn]

    # NEW: Scope Management
    active_scope: str | None              # "inmate_data", "document_qa", None
    scope_history: list[str]              # ["inmate_data", "document_qa", ...]
    scope_contexts: dict[str, ScopeContext]  # Per-scope working memory

@dataclass
class ScopeContext:
    scope: str
    recent_entities: dict       # {"inmate_name": "Anthony", "facility": "Dorm B"}
    recent_queries: list[str]   # Last 5 queries in this scope
    last_active: float          # Timestamp

@dataclass
class ConversationTurn:
    role: str
    content: str
    scope: str | None           # NEW: Which scope this turn belongs to
    timestamp: float
    sql: str = ""               # For inmate_data
    row_count: int = 0
    metadata: dict = field(default_factory=dict)  # Pipeline-specific
```

### 5. Memory Layer

```
src/memory/
├── stm/
│   └── session_store.py    # Valkey (short-term)
└── ltm/
    └── conversation_store.py  # DynamoDB (long-term)
```

**Memory Behavior:**

| Memory | Storage | TTL | Content |
|--------|---------|-----|---------|
| **STM (Valkey)** | ElastiCache | 1 hour | Active session + scope contexts |
| **LTM (DynamoDB)** | DynamoDB | 90 days | All turns with scope tags |

---

## Data Flow Architecture

### Request Flow

```
┌──────┐     ┌─────────┐     ┌──────────────┐     ┌────────────┐
│Client│────▶│   ALB   │────▶│   FastAPI    │────▶│Orchestrator│
└──────┘     └─────────┘     └──────────────┘     └─────┬──────┘
                                                        │
                              ┌─────────────────────────┴─────────────────────────┐
                              │                                                   │
                              ▼                                                   ▼
                    ┌─────────────────┐                               ┌─────────────────┐
                    │ Inmate Pipeline │                               │Document Pipeline│
                    │                 │                               │                 │
                    │ Q → Validate    │                               │ Q → Validate    │
                    │   → SQL Gen     │                               │   → Retrieve    │
                    │   → Execute     │                               │   → Synthesize  │
                    │   → Format      │                               │   → Format      │
                    └────────┬────────┘                               └────────┬────────┘
                             │                                                  │
                             │              ┌───────────────┐                   │
                             └──────────────│   Response    │───────────────────┘
                                            │   + Save      │
                                            └───────┬───────┘
                                                    │
                                            ┌───────▼───────┐
                                            │  STM + LTM    │
                                            └───────────────┘
```

### Scope Switching Flow

```
┌────────────────────────────────────────────────────────────────────────────────┐
│                           SCOPE SWITCH FLOW                                     │
└────────────────────────────────────────────────────────────────────────────────┘

User in "inmate_data" ─── clicks [Switch] ───▶ UI shows scope options
                                                        │
                                              User clicks "Documents"
                                                        │
                                                        ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│ POST /scope/select { "scope": "document_qa" }                                   │
└────────────────────────────────────────────────────────────────────────────────┘
                                                        │
                                                        ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│ ORCHESTRATOR: Scope Transition                                                  │
│                                                                                 │
│   1. PRESERVE current scope context                                            │
│      session.scope_contexts["inmate_data"] = {                                 │
│          recent_entities: {"inmate": "Anthony Nova"},                          │
│          recent_queries: ["fire watch notes", "that inmate's status"]          │
│      }                                                                          │
│                                                                                 │
│   2. UPDATE session                                                             │
│      session.active_scope = "document_qa"                                       │
│      session.scope_history.append("document_qa")                               │
│                                                                                 │
│   3. LOAD/CREATE new scope context                                             │
│      session.scope_contexts["document_qa"] = ScopeContext(...)                 │
│                                                                                 │
│   4. PERSIST to Valkey                                                          │
│      session_store.save(session)                                               │
└────────────────────────────────────────────────────────────────────────────────┘
                                                        │
                                                        ▼
┌────────────────────────────────────────────────────────────────────────────────┐
│ RESPONSE: Scope Welcome                                                         │
│                                                                                 │
│   {                                                                             │
│       "message": "Now helping with Documents. What would you like to find?",   │
│       "scope": "document_qa",                                                   │
│       "previous_scope": "inmate_data"                                          │
│   }                                                                             │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## Infrastructure Architecture

### AWS Resources

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              AWS INFRASTRUCTURE                                  │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                           VPC (Multi-AZ)                                 │   │
│  │                                                                          │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐            │   │
│  │  │   Public AZ-a  │  │   Public AZ-b  │  │   Public AZ-c  │            │   │
│  │  │  ┌──────────┐  │  │  ┌──────────┐  │  │  ┌──────────┐  │            │   │
│  │  │  │   ALB    │  │  │  │   ALB    │  │  │  │   ALB    │  │            │   │
│  │  │  └──────────┘  │  │  └──────────┘  │  │  └──────────┘  │            │   │
│  │  └────────────────┘  └────────────────┘  └────────────────┘            │   │
│  │                                                                          │   │
│  │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐            │   │
│  │  │  Private AZ-a  │  │  Private AZ-b  │  │  Private AZ-c  │            │   │
│  │  │  ┌──────────┐  │  │  ┌──────────┐  │  │  ┌──────────┐  │            │   │
│  │  │  │ECS Task 1│  │  │  │ECS Task 2│  │  │  │ECS Task 3│  │            │   │
│  │  │  │0.5vCPU/2G│  │  │  │0.5vCPU/2G│  │  │  │0.5vCPU/2G│  │            │   │
│  │  │  └──────────┘  │  │  └──────────┘  │  │  └──────────┘  │            │   │
│  │  │                │  │                │  │                │            │   │
│  │  │  ┌──────────┐  │  │  ┌──────────┐  │  │                │            │   │
│  │  │  │ Valkey   │  │  │  │ Valkey   │  │  │                │            │   │
│  │  │  │ (primary)│  │  │  │(replica) │  │  │                │            │   │
│  │  │  └──────────┘  │  │  └──────────┘  │  │                │            │   │
│  │  └────────────────┘  └────────────────┘  └────────────────┘            │   │
│  │                                                                          │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │                         Managed Services                                 │   │
│  │                                                                          │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │   │
│  │  │  DynamoDB   │  │   Aurora    │  │  Secrets    │  │ CloudWatch  │    │   │
│  │  │ (History)   │  │   MySQL     │  │  Manager    │  │  (Logs)     │    │   │
│  │  │             │  │  (Reader)   │  │             │  │             │    │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘    │   │
│  │                                                                          │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Scaling Configuration

| Load | ECS Tasks | Valkey | Cost |
|------|-----------|--------|------|
| **V1 (100 users)** | 3 × 0.5 vCPU / 2GB | t4g.small | ~$193/mo |
| **V2 (1000 users)** | 10 × 1 vCPU / 4GB | r7g.medium | ~$1000/mo |

---

## Design Decisions

### Why Guided (Not Inferred) Routing

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **Inferred** | "Magic" UX | Hallucinations, wrong pipeline | ❌ Rejected |
| **Guided** | Zero ambiguity, user control | Extra click | ✅ Chosen |

**Rationale:** In a correctional facility, wrong answers can have serious consequences. Explicit scope selection ensures the system never guesses wrong.

### Why ECS Fargate (Not Lambda)

| Factor | Lambda | Fargate | Decision |
|--------|--------|---------|----------|
| Cold starts | 3-8s | None | Fargate |
| ChromaDB | Reload each time | Persistent | Fargate |
| Connections | New per invoke | Pooled | Fargate |
| SSE Streaming | Limited | Full support | Fargate |

### Why Hybrid Search (Not Pure Semantic)

| Query Type | Pure Semantic | Hybrid |
|------------|---------------|--------|
| "Fire watch yesterday" | ✅ Good | ✅ Good |
| "What changed on 2024-09-15?" | ❌ Fails | ✅ Works |
| "/deploy rollback command" | ❌ Fails | ✅ Works |

**Rationale:** BM25 catches exact terms that semantic embeddings miss.

### Why Scope Context Preservation

When user switches from Inmate Data to Documents:

| Approach | Behavior | User Experience |
|----------|----------|-----------------|
| **Clear all** | Lose everything | Frustrating |
| **Keep visible** | See old chat, no context | Confusing |
| **Preserve + Restore** | Return to previous state | ✅ Natural |

---

## Summary

InmateCopilot V2 is a **guided, multi-capability conversational agent** built on:

1. **Explicit scope selection** — No AI guessing
2. **Modular pipelines** — Easy to add capabilities
3. **Context preservation** — Smooth scope switching
4. **Production infrastructure** — ECS Fargate, connection pooling
5. **Hybrid search** — Best of semantic + keyword
6. **Multi-tenant isolation** — Strict data boundaries
