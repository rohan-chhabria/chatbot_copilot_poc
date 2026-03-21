# InmateCopilot — Guided Multi-Capability Conversational Agent

A multi-tenant, conversational AI system for correctional facility officers that combines **natural language SQL queries** (Vanna AI 2.0) with **document-based Q&A** (RAG with hybrid search). Officers explicitly select their intent through a guided interface, enabling strict scope isolation and context preservation.

**Version**: 2.0 (Guided Conversational Agent)

---

## What This System Does

InmateCopilot V2 provides two distinct capabilities through a guided UI:

### 📊 Inmate Data Pipeline (SQL)
Officers query operational data using natural language:

| Question | What Happens |
|----------|-------------|
| "How many inmates are on Fire Watch?" | Generates SQL → queries Aurora MySQL → returns count |
| "Show me Officer Bell's notes from yesterday" | Filters by user_id + date → returns notes |
| "Which facilities had the most refusals?" | Aggregates by facility → ranks by refusal count |
| "Now show me just the red-highlighted ones" | Uses conversation context → adds highlighter filter |

### 📄 Document QA Pipeline (RAG)
Officers ask questions about policies, procedures, and documentation:

| Question | What Happens |
|----------|-------------|
| "What is the attorney visit procedure?" | Hybrid search → retrieves relevant chunks → synthesizes answer |
| "How do I document a fire drill?" | BM25 + semantic search → RRF fusion → LLM synthesis |
| "Explain the restraint removal process" | Retrieves from indexed PDFs/DOCXs → formatted response with sources |

The system maintains **multi-turn conversations** (up to 15 turns per session) with **scope isolation** — switching between pipelines preserves context for when you return.

---

## Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                 CLIENT LAYER                                     │
│    ┌─────────────┐  ┌─────────────────────────────────────────────────────┐    │
│    │   Sarah     │  │  [📊 Inmate Data]  [📄 Documents]  ← Scope Selector │    │
│    │   Avatar    │  │                                                      │    │
│    └─────────────┘  │  Conversation Thread (scope-aware)                   │    │
│                     └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              API LAYER (FastAPI)                                 │
│   /chat  /chat/stream  /scope/select  /scope/options  /health  /train           │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            ORCHESTRATOR LAYER                                    │
│   ┌─────────────────┐  ┌─────────────────┐  ┌────────────────────────────────┐ │
│   │ ScopeStateMachine│  │ ScopeRegistry   │  │ CrossScopeHandler              │ │
│   │ - Active scope  │  │ - Pipeline map  │  │ - Greetings, help, recall      │ │
│   │ - Scope switch  │  │ - Definitions   │  │ - Context preservation         │ │
│   └─────────────────┘  └─────────────────┘  └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
┌───────────────────────────────────┐   ┌───────────────────────────────────────┐
│      INMATE DATA PIPELINE         │   │         DOCUMENT QA PIPELINE          │
│                                   │   │                                       │
│  ┌─────────────────────────────┐  │   │  ┌─────────────────────────────────┐  │
│  │ QuestionValidator           │  │   │  │ DocumentValidator               │  │
│  │ (injection, domain check)   │  │   │  │ (length, relevance)             │  │
│  └─────────────────────────────┘  │   │  └─────────────────────────────────┘  │
│               │                   │   │               │                       │
│  ┌─────────────────────────────┐  │   │  ┌─────────────────────────────────┐  │
│  │ VannaAgent (Text-to-SQL)    │  │   │  │ DocumentRetriever               │  │
│  │ - ChromaDB training data    │  │   │  │ - Semantic search (embeddings)  │  │
│  │ - GPT-4o-mini generation    │  │   │  │ - BM25 keyword search           │  │
│  └─────────────────────────────┘  │   │  │ - RRF fusion (top-k merge)      │  │
│               │                   │   │  └─────────────────────────────────┘  │
│  ┌─────────────────────────────┐  │   │               │                       │
│  │ SQLValidator                │  │   │  ┌─────────────────────────────────┐  │
│  │ - Security checks           │  │   │  │ ResponseSynthesizer             │  │
│  │ - Filter injection          │  │   │  │ - Context + question → LLM      │  │
│  └─────────────────────────────┘  │   │  │ - Source attribution            │  │
│               │                   │   │  └─────────────────────────────────┘  │
│  ┌─────────────────────────────┐  │   │               │                       │
│  │ Aurora MySQL (read-only)    │  │   │  ┌─────────────────────────────────┐  │
│  └─────────────────────────────┘  │   │  │ ChromaDB (vector store)         │  │
│               │                   │   │  └─────────────────────────────────┘  │
│  ┌─────────────────────────────┐  │   │                                       │
│  │ ResponseFormatter           │  │   │                                       │
│  │ (concise officer-friendly)  │  │   │                                       │
│  └─────────────────────────────┘  │   │                                       │
└───────────────────────────────────┘   └───────────────────────────────────────┘
                    │                                       │
                    └───────────────────┬───────────────────┘
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              STORAGE LAYER                                       │
│   ┌─────────────────┐  ┌─────────────────┐  ┌────────────────────────────────┐ │
│   │ Valkey          │  │ DynamoDB        │  │ ChromaDB                       │ │
│   │ (Sessions/STM)  │  │ (History/LTM)   │  │ (Vanna training + Doc vectors) │ │
│   └─────────────────┘  └─────────────────┘  └────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### Key Architectural Principles

| Principle | Implementation |
|-----------|----------------|
| **Guided, Not Inferred** | User clicks to select scope; no AI guessing intent |
| **Scope Isolation** | Each pipeline operates independently; no cross-contamination |
| **Context Preservation** | Switching scopes preserves previous context for return |
| **Modular Pipelines** | Each capability is self-contained via `Pipeline` base class |
| **Multi-Tenant** | Strict data isolation per `customer_key` |
| **Hybrid Search** | Semantic + BM25 with RRF fusion for document retrieval |

---

## Project Structure

```
chatbot_copilot_poc/
├── .github/workflows/
│   ├── ci.yml                           # Lint, test, validate on push/PR
│   └── cd.yml                           # Deploy to AWS (manual dispatch)
│
├── docs/
│   ├── ARCHITECTURE.md                  # System architecture diagrams
│   ├── IMPLEMENTATION_PLAN.md           # V2 migration phases
│   ├── INFRASTRUCTURE_ANALYSIS.md       # AWS cost analysis
│   ├── SYSTEM_FLOWS.md                  # Detailed flow diagrams
│   ├── USAGE_GUIDE.md                   # How to use the application
│   └── V1_V2_SCOPE.md                   # V1→V2 scope comparison
│
├── infra/
│   ├── template.yaml                    # SAM/CloudFormation
│   └── samconfig.toml                   # SAM CLI config
│
├── local/
│   ├── server.py                        # Local development server
│   ├── bootstrap.py                     # Environment setup
│   └── test_conversations.py            # Manual testing scripts
│
├── scripts/
│   └── train_vanna.py                   # Vanna ChromaDB training CLI
│
├── src/
│   ├── api/
│   │   ├── handlers/
│   │   │   ├── chat_handler.py          # Chat orchestration
│   │   │   └── scope_handler.py         # Scope selection/switching
│   │   ├── handler.py                   # Lambda/Uvicorn entry point
│   │   ├── routes.py                    # All API endpoints
│   │   ├── schemas.py                   # Pydantic request/response models
│   │   └── middleware.py                # Request logging, CORS
│   │
│   ├── orchestrator/                    # NEW: V2 Orchestration Layer
│   │   ├── state_machine.py             # ScopeStateMachine (dispatch, context)
│   │   ├── scope_registry.py            # ScopeRegistry (pipeline mapping)
│   │   ├── cross_scope.py               # CrossScopeHandler (greetings, help)
│   │   └── tests/                       # Orchestrator unit tests
│   │
│   ├── pipelines/
│   │   ├── base.py                      # Pipeline abstract base class
│   │   │
│   │   ├── inmate_data/                 # SQL Pipeline (migrated from agent/)
│   │   │   ├── pipeline.py              # InmateDataPipeline
│   │   │   ├── vanna_agent.py           # Vanna AI 2.0 integration
│   │   │   ├── intent_engine.py         # Intent detection
│   │   │   ├── prompt_builder.py        # Context-aware prompts
│   │   │   ├── response_formatter.py    # Officer-friendly formatting
│   │   │   ├── sarah_brain.py           # Personality/greeting logic
│   │   │   ├── guardrails/
│   │   │   │   ├── question_validator.py # Input validation
│   │   │   │   └── sql_validator.py      # SQL security checks
│   │   │   └── tests/                   # Pipeline-specific tests
│   │   │
│   │   └── document_qa/                 # NEW: RAG Pipeline
│   │       ├── pipeline.py              # DocumentQAPipeline
│   │       ├── retriever.py             # Hybrid search (semantic + BM25)
│   │       ├── synthesizer.py           # LLM response synthesis
│   │       ├── indexer.py               # Document indexing utilities
│   │       ├── documents/
│   │       │   ├── loader.py            # PDF/DOCX text extraction
│   │       │   ├── chunker.py           # Recursive text chunking
│   │       │   ├── store.py             # TenantDocumentStore (ChromaDB)
│   │       │   └── models.py            # Document/Chunk data classes
│   │       ├── guardrails/
│   │       │   └── validator.py         # Document question validation
│   │       └── tests/                   # Document pipeline tests
│   │
│   ├── session/
│   │   ├── models.py                    # Session model with scope context
│   │   └── session_manager.py           # Valkey-backed session store
│   │
│   ├── memory/
│   │   └── conversation_store.py        # DynamoDB conversation history
│   │
│   ├── tenant/
│   │   ├── tenant_router.py             # customer_key → DB resolver
│   │   └── db_registry.py               # Connection pool per tenant
│   │
│   ├── training/
│   │   ├── trainer.py                   # ChromaDB training data loader
│   │   └── data/                        # JSON training files
│   │
│   ├── tools/
│   │   ├── compliance_tool.py           # Pre-built compliance queries
│   │   └── facility_tool.py             # Facility summary queries
│   │
│   └── shared/
│       ├── config.py                    # Centralized configuration
│       ├── constants.py                 # Domain constants
│       ├── exceptions.py                # Custom exception classes
│       └── logger.py                    # Structured logging factory
│
├── static/
│   └── index.html                       # Web UI with scope selection
│
├── tests/
│   ├── conftest.py                      # Shared fixtures
│   ├── unit/                            # Unit tests
│   └── integration/                     # Integration tests
│
├── .env.example                         # Environment variable template
├── .gitignore
├── Makefile                             # install, lint, test, run
├── pyproject.toml                       # pytest, ruff, mypy config
├── requirements.txt                     # Production dependencies
└── requirements-dev.txt                 # Dev/test dependencies
```

---

## Quick Start

### 1. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # For testing
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your configuration:
#   - OPENAI_API_KEY (required for both pipelines)
#   - Database credentials (for Inmate Data pipeline)
#   - LLM_PROVIDER=openai (default)
#   - LOG_LEVEL=DEBUG (for detailed logging)
```

### 3. Train Vanna ChromaDB (Required for SQL Pipeline)

```bash
# Using the training script
python scripts/train_vanna.py --stats  # View current stats
python scripts/train_vanna.py --train  # Load training data

# Or programmatically
PYTHONPATH=. python3 -c "from src.training.trainer import train_from_defaults; print(train_from_defaults())"
```

### 4. Index Documents (Required for Document QA Pipeline)

```python
# Using the indexer programmatically
from src.pipelines.document_qa.indexer import index_file, index_directory

# Index a single file
await index_file("/path/to/document.pdf", customer_key="demo")

# Index a directory
await index_directory("/path/to/docs/", customer_key="demo")

# Check index stats
from src.pipelines.document_qa.indexer import get_index_stats
stats = get_index_stats(customer_key="demo")
print(f"Total chunks: {stats['total_chunks']}")
```

### 5. Run the Server

```bash
# Local development server
python -m local.server

# Or with uvicorn directly
PYTHONPATH=. uvicorn src.api.handler:app --reload --host 0.0.0.0 --port 8000
```

### 6. Access the Application

- **Web UI**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

### 7. Run Tests

```bash
# All tests
PYTHONPATH=. pytest tests/ -v

# Specific test suites
PYTHONPATH=. pytest src/orchestrator/tests/ -v      # Orchestrator tests
PYTHONPATH=. pytest src/pipelines/inmate_data/tests/ -v  # SQL pipeline tests
PYTHONPATH=. pytest src/pipelines/document_qa/tests/ -v  # Document pipeline tests
```

---

## API Endpoints

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat` | POST | Main conversation endpoint (scope-aware) |
| `/chat/stream` | POST | Streaming conversation (SSE) |
| `/scope/select` | POST | Select active scope |
| `/scope/options` | GET | Get available scopes |
| `/health` | GET | Health check |
| `/train` | POST | Trigger Vanna training |

### POST /chat — Main Conversation

**Request:**
```json
{
    "question": "How many inmates are on Fire Watch?",
    "customer_key": "demo",
    "user_id": "richard.bell",
    "session_id": null,
    "facility_ids": [101, 102]
}
```

**Response (with active scope):**
```json
{
    "success": true,
    "session_id": "a1b2c3d4-...",
    "summary": "Found 45 inmates on Fire Watch across 3 facilities.",
    "data": [{"facility": "Main Block", "count": 20}],
    "row_count": 3,
    "sql": "SELECT f.facility, COUNT(*) ...",
    "scope": "inmate_data"
}
```

**Response (no scope selected):**
```json
{
    "requires_scope": true,
    "greeting": "Hello! I'm Sarah, your correctional facility assistant.",
    "options": [
        {"id": "inmate_data", "name": "Inmate Data", "description": "Query operational data"},
        {"id": "document_qa", "name": "Documents", "description": "Search policies and procedures"}
    ]
}
```

### POST /scope/select — Select Scope

**Request:**
```json
{
    "session_id": "a1b2c3d4-...",
    "scope_id": "document_qa"
}
```

**Response:**
```json
{
    "success": true,
    "scope": "document_qa",
    "message": "📄 Documents scope selected. Ask me about policies and procedures."
}
```

---

## Document QA Pipeline

### Indexing Documents

The Document QA pipeline requires documents to be indexed before querying:

```python
from src.pipelines.document_qa.indexer import DocumentIndexer

# Initialize indexer
indexer = DocumentIndexer(customer_key="demo")

# Index a PDF
result = await indexer.index_file("/path/to/manual.pdf")
print(f"Indexed {result['chunks']} chunks from {result['filename']}")

# Index a directory of documents
results = await indexer.index_directory("/path/to/docs/", recursive=True)
for r in results:
    print(f"  {r['filename']}: {r['chunks']} chunks")
```

### Supported File Types

| Format | Extension | Library |
|--------|-----------|---------|
| PDF | `.pdf` | pypdf |
| Word | `.docx` | python-docx |
| Text | `.txt` | Built-in |
| Markdown | `.md` | Built-in |

### Hybrid Search Architecture

The retriever uses a three-stage hybrid search:

1. **Semantic Search**: OpenAI embeddings (`text-embedding-3-small`) → ChromaDB vector similarity
2. **BM25 Search**: Tokenized keyword matching with Okapi BM25 scoring
3. **RRF Fusion**: Reciprocal Rank Fusion merges results with `k=60`

```
Query: "attorney visit procedure"
                    │
    ┌───────────────┴───────────────┐
    ▼                               ▼
┌─────────────┐             ┌─────────────┐
│  Semantic   │             │    BM25     │
│  (top 20)   │             │  (top 20)   │
└─────────────┘             └─────────────┘
    │                               │
    └───────────────┬───────────────┘
                    ▼
            ┌─────────────┐
            │ RRF Fusion  │
            │  (top 5)    │
            └─────────────┘
                    │
                    ▼
            ┌─────────────┐
            │ Synthesizer │
            │ (GPT-4o)    │
            └─────────────┘
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| **General** | | |
| `ENVIRONMENT` | `dev` | Environment (dev/staging/prod) |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| **LLM** | | |
| `OPENAI_API_KEY` | — | OpenAI API key (required) |
| `LLM_PROVIDER` | `openai` | LLM provider |
| `LLM_MODEL` | `gpt-4o-mini` | Model for SQL generation |
| `DOC_LLM_MODEL` | `gpt-4o-mini` | Model for document synthesis |
| **Database** | | |
| `TENANT_DB_MAP` | `{}` | JSON map of tenant DB configs |
| **Storage** | | |
| `CHROMA_STORAGE_DIR` | `./chroma_db` | Vanna training ChromaDB path |
| `DOC_CHROMA_DIR` | `./chroma_docs` | Document vectors ChromaDB path |
| `VALKEY_HOST` | `localhost` | Session store host |
| `DYNAMODB_TABLE` | — | Conversation history table |
| **Document QA** | | |
| `DOC_CHUNK_SIZE` | `512` | Document chunk size (chars) |
| `DOC_CHUNK_OVERLAP` | `50` | Chunk overlap (chars) |
| `DOC_TOP_K` | `5` | Number of chunks to retrieve |
| `DOC_PIPELINE_TIMEOUT` | `30` | Pipeline timeout (seconds) |

### Multi-Tenant Configuration

```json
{
    "demo": {
        "host": "demo-db.cluster-ro-xxx.rds.amazonaws.com",
        "database": "Demo_aurora",
        "user": "reader",
        "password": "xxx",
        "port": 3306
    },
    "gdc-prod": {
        "host": "gdc-db.cluster-ro-xxx.rds.amazonaws.com",
        "database": "GDC_aurora",
        "user": "reader",
        "password": "xxx",
        "port": 3306
    }
}
```

---

## Security & Guardrails

### Inmate Data Pipeline (SQL)

**Question Validation:**
- SQL injection detection (UNION, OR 1=1, leetspeak normalization)
- Schema exposure prevention (information_schema, SHOW TABLES)
- Sensitive data request blocking (password, SSN)
- Domain relevance checking (rejects weather, sports, etc.)
- Length limits (5-1000 characters)

**SQL Validation:**
- SELECT/WITH only (no DDL, DML, stored procedures)
- Sensitive column filtering (password, salt, ssn, signature)
- Mandatory `status = 1` filter injection
- Facility-level isolation via `facilities_id IN (...)`
- REGEXP → LIKE conversion for MySQL
- Balanced parentheses validation

### Document QA Pipeline (RAG)

**Question Validation:**
- Length limits (3-2000 characters)
- Relevance checking for document context
- Empty/whitespace rejection

**Response Synthesis:**
- Source attribution required
- Context-grounded answers only
- No hallucination of document content

---

## Debug Logging

Enable comprehensive debug logging to troubleshoot issues:

```bash
# Set in .env
LOG_LEVEL=DEBUG

# Or export directly
export LOG_LEVEL=DEBUG
python -m local.server
```

Debug logs are available for:

| Component | Log Prefix | What It Logs |
|-----------|------------|--------------|
| API Routes | `src.api.routes` | Request/response, session resolution |
| Orchestrator | `src.orchestrator.state_machine` | Scope dispatch, message handling |
| Session Manager | `src.session.session_manager` | Session get/save/delete |
| Document Retriever | `src.pipelines.document_qa.retriever` | BM25 scores, semantic scores, RRF fusion |
| Document Synthesizer | `src.pipelines.document_qa.synthesizer` | Context length, chunk details, LLM calls |
| Document Indexer | `src.pipelines.document_qa.indexer` | Chunking, embedding, storage |
| Document Loader | `src.pipelines.document_qa.documents.loader` | PDF/DOCX extraction |
| Inmate Pipeline | `src.pipelines.inmate_data.pipeline` | Vanna agent calls, SQL generation |

---

## Testing

### Test Structure

```
tests/
├── conftest.py                          # Shared fixtures
├── unit/
│   ├── test_question_validator.py       # 17 tests
│   ├── test_sql_validator.py            # 14 tests
│   ├── test_session_manager.py          # 11 tests
│   ├── test_tenant_router.py            # 8 tests
│   ├── test_prompt_builder.py           # 7 tests
│   └── test_response_formatter.py       # 11 tests
└── integration/
    ├── test_api_endpoints.py            # 9 tests
    └── test_agent_pipeline.py           # 13 tests

src/
├── orchestrator/tests/                  # Orchestrator unit tests
├── pipelines/inmate_data/tests/         # SQL pipeline tests
└── pipelines/document_qa/tests/         # Document pipeline tests
```

### Running Tests

```bash
# All tests
PYTHONPATH=. pytest -v

# With coverage
PYTHONPATH=. pytest --cov=src --cov-report=html

# Specific module
PYTHONPATH=. pytest src/pipelines/document_qa/tests/ -v

# Integration tests only
PYTHONPATH=. pytest tests/integration/ -v
```

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Text-to-SQL** | Vanna AI 2.0.2 | NL → SQL generation with ChromaDB memory |
| **Document QA** | RAG (Hybrid Search) | Semantic + BM25 with RRF fusion |
| **LLM** | OpenAI GPT-4o-mini | SQL generation + document synthesis |
| **Embeddings** | OpenAI text-embedding-3-small | Document and query vectors |
| **API** | FastAPI + Mangum | REST API + SSE streaming |
| **Database** | Aurora MySQL | Read-only operational data |
| **Vector Store** | ChromaDB | Training data + document embeddings |
| **Sessions** | Valkey (ElastiCache) | Short-term conversation context |
| **History** | DynamoDB | Long-term conversation persistence |
| **PDF Parsing** | pypdf | PDF text extraction |
| **DOCX Parsing** | python-docx | Word document extraction |
| **BM25** | rank-bm25 | Keyword search scoring |
| **Infra** | AWS SAM | DynamoDB, Lambda, API Gateway |
| **CI/CD** | GitHub Actions | Lint, test, deploy |
| **Tests** | pytest + moto | Unit + integration + mock AWS |

---

## Dependencies

### Production (requirements.txt)

```
vanna[chromadb,mysql]
fastapi>=0.115.0
mangum>=0.19.0
uvicorn>=0.32.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
pymysql>=1.1.0
cryptography>=43.0.0
boto3>=1.35.0
redis>=5.0.0
litellm>=1.50.0
sse-starlette>=2.0.0
moto[dynamodb]>=5.0.0
python-dotenv>=1.0.0

# Document QA pipeline
openai>=1.0.0
pypdf>=4.0.0
python-docx>=1.0.0
rank-bm25>=0.2.2
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [USAGE_GUIDE.md](docs/USAGE_GUIDE.md) | Complete guide to using the application |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture diagrams |
| [SYSTEM_FLOWS.md](docs/SYSTEM_FLOWS.md) | Detailed request/response flows |
| [IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | V2 migration phases |
| [V1_V2_SCOPE.md](docs/V1_V2_SCOPE.md) | V1 vs V2 comparison |
| [INFRASTRUCTURE_ANALYSIS.md](docs/INFRASTRUCTURE_ANALYSIS.md) | AWS cost analysis |

---

## Performance

### LLM Provider (GPT-4o-mini)

| Metric | Value |
|--------|-------|
| Success rate | 100% (35/35 queries) |
| Avg response time | 2.3s |
| Cost | $0.15/1M input + $0.60/1M output tokens |

### Pipeline Breakdown (warm query)

| Stage | Time | % |
|-------|------|---|
| Guardrails | ~0.1 ms | <1% |
| ChromaDB search | ~215 ms | 9% |
| LLM generation | ~1,800 ms | 78% |
| SQL validation | ~0.3 ms | <1% |
| DB execution | ~150 ms | 7% |
| **Total** | **~2,300 ms** | 100% |

### Document QA Pipeline

| Stage | Time |
|-------|------|
| Query embedding | ~200 ms |
| Semantic search | ~100 ms |
| BM25 search | ~50 ms |
| RRF fusion | ~5 ms |
| LLM synthesis | ~2,000 ms |
| **Total** | **~2,400 ms** |

---

## Deployment

### Local Development

```bash
python -m local.server
```

### AWS Lambda

```bash
sam build --template infra/template.yaml
sam deploy \
    --stack-name "InmateCopilot-V2-dev" \
    --capabilities CAPABILITY_IAM \
    --parameter-overrides "Environment=dev DeploymentId=a1b2c3d4e5"
```

### ECS Fargate

Deploy using the same Docker image with `uvicorn` as the entrypoint.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| **2.0** | 2026-03 | Guided multi-capability agent, Document QA pipeline, Orchestrator layer, Scope isolation |
| **1.0** | 2026-01 | Initial release, SQL-only chatbot with Vanna AI |

---

## License

Proprietary — Internal use only.
