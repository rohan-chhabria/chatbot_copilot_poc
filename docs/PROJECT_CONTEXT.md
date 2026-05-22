# InmateCopilot — Project Context (Agent Reference)

**Last Updated**: 2026-05-22  
**Purpose**: Quick context for AI agents to understand codebase without re-reading.

---

## Architecture Overview

```
User → FastAPI (routes.py) → ScopeStateMachine → Pipeline → Response
                  ↓
          SessionStore (STM: Redis/Valkey)
          ConversationStore (LTM: SQLite/DynamoDB)
```

---

## Directory Structure

```
src/
├── api/
│   ├── routes.py          # All endpoints: /chat, /chat/stream, /scope/*, /health
│   ├── handler.py         # FastAPI app creation
│   ├── schemas.py         # Pydantic models
│   └── middleware.py      # CORS, request-id, logging
├── orchestrator/
│   ├── state_machine.py   # Core routing: scope state, pipeline dispatch, turn persistence
│   ├── cross_scope.py     # Greetings, farewells, help, recall handlers
│   ├── scope_registry.py  # Pipeline registration via @register_pipeline decorator
│   └── persona.py         # Bot personality responses
├── pipelines/
│   ├── base.py            # Abstract Pipeline class
│   ├── inmate_data/       # SQL pipeline (Vanna text-to-SQL)
│   │   ├── pipeline.py    # InmateDataPipeline
│   │   ├── vanna_agent.py # Core SQL generation logic
│   │   ├── prompt_builder.py
│   │   ├── response_formatter.py
│   │   ├── insight_extractor.py
│   │   ├── response_summarizer.py
│   │   └── guardrails/    # Question/SQL validation
│   ├── document_qa/       # RAG pipeline
│   │   ├── pipeline.py    # DocumentQAPipeline
│   │   ├── retriever.py   # Hybrid search (semantic + BM25)
│   │   ├── synthesizer.py # LLM answer generation
│   │   ├── indexer.py     # Document ingestion
│   │   └── documents/store.py  # TenantDocumentStore (ChromaDB)
│   └── daily_activity/    # Compliance pipeline
│       ├── pipeline.py    # DailyActivityPipeline (auto_execute=True)
│       ├── activity_checker.py
│       ├── timetable_loader.py
│       └── response_formatter.py
├── session/
│   ├── models.py          # Session, ScopeContext, ConversationTurn dataclasses
│   └── session_manager.py # SessionStore (Redis/Valkey backends)
├── memory/
│   ├── conversation_store.py  # LTM backends (SQLite/DynamoDB)
│   ├── stm/               # Short-term memory utilities
│   └── ltm/               # Long-term memory utilities
├── tenant/
│   ├── tenant_router.py   # customer_key → TenantContext (DB connection)
│   └── db_registry.py     # DB connection pool, query execution
├── training/
│   ├── trainer.py         # Vanna training functions
│   └── data/              # default_examples.json, default_documentation.json
├── shared/
│   ├── config.py          # All env vars, defaults
│   ├── logger.py          # Logging setup
│   └── exceptions.py      # Custom exceptions
└── tools/                 # Utility scripts
```

---

## Core Data Models

### Session (`src/session/models.py`)
```python
Session:
  session_id: str (UUID)
  customer_key: str          # Tenant identifier
  user_id: str               # e.g., "Richard.Bell"
  facility_ids: list[int]    # SQL filter scope
  role: str                  # "officer", "warden"
  active_scope: str | None   # "inmate_data", "document_qa", "daily_activity"
  scope_history: list[str]   # Navigation history
  scope_contexts: dict[str, ScopeContext]  # Per-scope working memory
  turns: list[ConversationTurn]  # Rolling window (max 15 per scope)

ScopeContext:
  scope: str
  recent_entities: dict      # {"inmate_name": "Anthony Nova", "facility": "Dorm B"}
  recent_queries: list[str]  # Last 5 questions in this scope

ConversationTurn:
  role: str                  # "user" | "assistant"
  content: str
  scope: str | None
  timestamp: float
  sql: str                   # For inmate_data responses
  row_count: int
  metadata: dict
```

---

## 3 Pipelines

| Scope ID | Label | Auto-Execute | Processing |
|----------|-------|--------------|------------|
| `daily_activity` | Daily Activity | Yes | Timetable JSON vs DB → missed/upcoming (template, no LLM) |
| `inmate_data` | Inmate Data | No | Vanna text-to-SQL → Aurora MySQL → LLM summarize |
| `document_qa` | Documents | No | ChromaDB hybrid retrieval → LLM synthesize with sources |

---

## Request Flow

### New Session
```
POST /chat (no session_id, question="hello")
  → create Session
  → cross_scope.handle() → greeting
  → return {session_id, requires_scope: true, options: [...]}
```

### Scope Selection
```
POST /scope/select {session_id, scope: "inmate_data"}
  → state_machine.select_scope()
  → session.switch_scope()
  → return {summary: "Welcome...", scope}
  
If daily_activity:
  → auto_execute: pipeline.process("") → combined welcome + status
```

### Chat with Active Scope
```
POST /chat {session_id, question: "show fire watch notes"}
  → state_machine.handle_message()
    1. Cross-scope check (greeting/help/recall) → early return if match
    2. No scope? → prompt selection
    3. Dispatch to pipeline.process()
    4. _record_turn_pair() → save to session.turns + LTM
    5. _update_scope_context() → add to recent_queries
  → return {summary, row_count, scope}
```

---

## Inmate Data Pipeline Detail

```
Question 
  → validate_question() (guardrails)
  → build_sql_context() (history + training examples from ChromaDB)
  → Vanna LLM generate SQL
  → validate_and_fix_sql()
  → inject_filters() (status=1, facilities_id IN ...)
  → execute_query() (Aurora MySQL)
  → InsightExtractor.extract() (stats from results)
  → ResponseSummarizer.summarize() (LLM polish)
  → format_response_with_insights()
```

Key SQL rules in `vanna_agent.py`:
- Always filter `status = 1` for active records
- Join `dg_notes.user_id = dg_user.username` (NOT user_id INT)
- Inmate status: use `role_call` not `tags_status`
- Facility name column: `facility` not `facility_name`
- Red-highlighted: `highlighter_id = 11`

---

## Document QA Pipeline Detail

```
Question
  → TenantDocumentStore.get(customer_key)
  → DocumentRetriever.retrieve():
      - Semantic search (ChromaDB embeddings)
      - BM25 keyword search
      - RRF fusion → top K chunks
  → ResponseSynthesizer.synthesize():
      - LLM with context chunks
      - Extract sources
  → {answer, sources[]}
```

---

## Memory Architecture

| Type | Backend (Local) | Backend (Prod) | TTL | Purpose |
|------|-----------------|----------------|-----|---------|
| **STM** | Redis | Valkey (ElastiCache) | 1hr | Session state, recent turns |
| **LTM** | SQLite | DynamoDB | 90d | Full conversation history |

STM Key: `session:{session_id}` → JSON serialized Session
LTM Key: `{customer_key}#{user_id}` + `{session_id}#{timestamp}`

---

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/chat` | POST | Main chat (returns JSON) |
| `/chat/stream` | POST | SSE streaming chat |
| `/scope/select` | POST | Select/switch scope |
| `/scope/options` | GET | Available scopes for UI |
| `/session/{id}` | GET | Session debug info |
| `/history` | GET | User's LTM history |
| `/health` | GET | Service health |
| `/pipelines/health/{scope}` | GET | Pipeline-specific health |
| `/train` | POST | Reload Vanna training data |

---

## Key Config (src/shared/config.py)

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | dev | dev/staging/prod |
| `SESSION_BACKEND` | auto | redis (local) / valkey (prod) |
| `LTM_BACKEND` | auto | sqlite (local) / dynamodb (prod) |
| `LLM_PROVIDER` | openai | openai / gemini |
| `LLM_MODEL` | gpt-4o-mini | Model for SQL/synthesis |
| `SESSION_TTL_SECONDS` | 3600 | 1 hour |
| `MAX_QUERY_RESULTS` | 500 | SQL result limit |
| `MAX_CONVERSATION_TURNS` | 15 | STM window per scope |
| `ENABLE_GUARDRAILS` | true | Question validation |
| `DOC_HYBRID_SEARCH` | true | Semantic + BM25 |

---

## Multi-Tenant

- `customer_key` → `TenantContext` via `resolve_tenant()`
- Each tenant has own Aurora MySQL connection
- Document stores: `docs_{customer_key}` ChromaDB collection
- `facility_ids` injected into every SQL query

---

## Response Contracts

**Normal Response**:
```json
{"success": true, "session_id": "...", "summary": "...", "row_count": N, "scope": "..."}
```

**Requires Scope Selection**:
```json
{"requires_scope": true, "options": [{"id": "...", "label": "...", "icon": "...", "description": "..."}]}
```

**Session Expired**:
```json
{"success": false, "error": "session_expired"}
```

**SSE Events**: `session` → `status*` → `result` → `done` (or `error`)

---

## Cross-Scope Handlers

Handled by `CrossScopeHandler` regardless of active scope:
- **Greetings**: "hello", "hi", "hey"
- **Farewells**: "bye", "thanks", "done"
- **Help**: "what can you do", "help"
- **Self-identity**: "who am i", "my name"
- **Recall**: "what did I ask", "history"

---

## Testing

```bash
# All tests
pytest tests/ src/orchestrator/tests/ src/pipelines/*/tests/ -v

# Specific pipeline
pytest src/pipelines/inmate_data/tests/ -v

# Integration
pytest tests/integration/ -v
```

---

## Local Development

```bash
# Start Redis (required for STM)
redis-server

# Run local server with UI
python -m local.server

# Endpoints
# UI:   http://localhost:8000
# Docs: http://localhost:8000/docs
```

---

## Production Deployment

- ECS Fargate behind ALB
- Entry: `uvicorn src.api.handler:app`
- Monitoring: Sentry (DSN via env)
- ChromaDB baked into Docker image (no /train needed post-deploy)
