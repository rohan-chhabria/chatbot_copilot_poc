# InmateCopilot — Usage Guide

**Version**: 2.0  
**Updated**: 2026-03-20

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Running the Application](#running-the-application)
3. [Using the Web UI](#using-the-web-ui)
4. [API Reference](#api-reference)
5. [Vanna Training (SQL)](#vanna-training-sql)
6. [Document Ingestion (RAG)](#document-ingestion-rag)
7. [Configuration](#configuration)
8. [Testing](#testing)
9. [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# 1. Clone and install dependencies
cd chatbot_copilot_poc
pip install -r requirements.txt

# 2. Set up environment
cp .env.example .env  # Edit with your OpenAI key, DB credentials

# 3. Start Redis for local STM (required)
redis-server
# or: docker run --name copilot-redis -p 6379:6379 -d redis:7

# 4. Run local development server
python -m local.server

# 5. Open browser
# Dashboard: http://localhost:8000
# API Docs:  http://localhost:8000/docs
```

---

## Running the Application

### Local Development Server

The local server uses runtime local backends by default:

- STM: Redis
- LTM: SQLite file

```bash
# Start Redis first (required for STM)
redis-server
# or: docker run --name copilot-redis -p 6379:6379 -d redis:7

python -m local.server
```

**Endpoints available:**

- `http://localhost:8000` — Web UI Dashboard
- `http://localhost:8000/docs` — Interactive API documentation (Swagger)
- `http://localhost:8000/redoc` — ReDoc API documentation

### Production Server

For production deployment:

```bash
uvicorn src.api.handler:app --host 0.0.0.0 --port 8000
```

### Environment Variables

Create a `.env` file in the project root:

```env
# Required
OPENAI_API_KEY=sk-your-openai-key-here

# Database (for Inmate Data queries)
MYSQL_HOST=your-aurora-reader-endpoint
MYSQL_DATABASE=Demo_aurora
MYSQL_USER=readonly_user
MYSQL_PASSWORD=your-password

# Optional (defaults shown)
ENVIRONMENT=dev
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
CHROMA_STORAGE_DIR=./chroma_db
VALKEY_HOST=localhost
VALKEY_PORT=6379
ENABLE_GUARDRAILS=true
```

---

## Using the Web UI

### 1. Login

Open `http://localhost:8000` and select a user profile from the login screen:


| User         | Role    | Description             |
| ------------ | ------- | ----------------------- |
| Richard Bell | Officer | Standard officer access |
| Anks         | Officer | Standard officer access |
| Mark Kent    | Warden  | Supervisor access       |
| Bill Allen   | Officer | Standard officer access |


### 2. Scope Selection

After login, you'll be greeted with scope options:


| Scope              | Icon | Description                                        |
| ------------------ | ---- | -------------------------------------------------- |
| **Inmate Data**    | 📊   | Query notes, inmates, officers, facilities via SQL |
| **Documents**      | 📄   | Search manuals, policies, SOPs via RAG             |
| **Daily Activity** | 📅   | Check missed and upcoming scheduled activities     |


Click a scope block to enter that mode.

### 3. Chat Interface

Click the floating chat button (bottom-right) to open the chat panel:

- **Type a question** in the input field and press Enter
- **Voice input**: Click the microphone button
- **Quick actions**: Use preset query buttons on the dashboard
- **Switch scope**: Click "Switch" button in the chat header

### 4. Example Queries

**Inmate Data (SQL):**

```
Show fire watch notes from today
How many inmates are active?
Notes for inmate Anthony Nova
Top 5 officers by notes this month
Red highlighted entries in last 7 days
```

**Documents (RAG):**

```
What is the fire drill evacuation procedure?
How do I handle a medical emergency?
What are the visitor check-in policies?
```

### 5. Scope Switching

1. Click the **[Switch]** button in the chat header
2. Select a different scope from the options
3. Your context in the previous scope is preserved
4. When you switch back, you'll see a reminder of your last query

---

## API Reference

### Chat Endpoints

#### POST /chat

Main chat endpoint (uses orchestrator).

If `session_id` is provided but expired/invalid, the endpoint returns HTTP `200` with:
`{"success": false, "error": "session_expired"}`.

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Show fire watch notes today",
    "customer_key": "demo",
    "user_id": "Richard.Bell",
    "facility_ids": [63]
  }'
```

**Response:**

```json
{
  "success": true,
  "session_id": "abc-123",
  "summary": "Found 23 fire watch notes from today...",
  "row_count": 23,
  "scope": "inmate_data"
}
```

#### POST /chat/stream

SSE streaming endpoint for real-time responses.

If `session_id` is provided but expired/invalid, stream emits `event: error`
with `{"error":"session_expired", ...}` followed by `event: done`.

```bash
curl -N http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Show fire watch notes",
    "session_id": "abc-123",
    "customer_key": "demo",
    "user_id": "Richard.Bell"
  }'
```

**Events:**

- `event: session` — Session ID
- `event: status` — Processing status updates
- `event: result` — Final response
- `event: error` — Error message
- `event: done` — Stream complete

### Scope Management

#### POST /scope/select

Select or switch to a scope.

```bash
curl -X POST http://localhost:8000/scope/select \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "abc-123",
    "scope": "document_qa",
    "customer_key": "demo",
    "user_id": "Richard.Bell"
  }'
```

If `session_id` is expired/missing, response is `404` with `{"detail":"session_expired"}`.

#### GET /scope/options

Get available scope options.

```bash
curl "http://localhost:8000/scope/options?session_id=abc-123"
```

If `session_id` is provided but invalid/expired, response is `404` with `{"detail":"session_expired"}`.

### Utility Endpoints

#### GET /health

Health check.

```bash
curl http://localhost:8000/health
```

#### GET /pipelines/health/{scope}

Pipeline-specific health check.

```bash
curl http://localhost:8000/pipelines/health/inmate_data
curl http://localhost:8000/pipelines/health/document_qa
curl http://localhost:8000/pipelines/health/daily_activity
```

#### POST /train

Trigger Vanna training data reload.

```bash
curl -X POST http://localhost:8000/train
```

#### GET /session/{session_id}

Get session details.

```bash
curl http://localhost:8000/session/abc-123
```

#### GET /history

Get conversation history for a user.

```bash
curl "http://localhost:8000/history?customer_key=demo&user_id=Richard.Bell&limit=50"
```

---

## Vanna Training (SQL)

The Vanna agent uses ChromaDB to store training examples that improve SQL generation.

### Training Data Files

Training data is stored in JSON files:

```
src/training/data/
├── default_examples.json      # Question-SQL pairs
└── default_documentation.json # Schema documentation
```

### Training Data Format

**Examples (default_examples.json):**

```json
[
  {
    "question": "How many notes were added today?",
    "sql": "SELECT COUNT(*) AS count FROM dg_notes n WHERE DATE(n.date_added) = CURDATE() AND n.status = 1"
  },
  {
    "question": "Show fire watch notes from last week",
    "sql": "SELECT n.notes_id, n.notes_description, n.note_date FROM dg_notes n LEFT JOIN dg_notes_by_keyword knw ON n.notes_id = knw.notes_id WHERE LOWER(knw.keyword_name) LIKE '%fire%' AND LOWER(knw.keyword_name) LIKE '%watch%' AND n.date_added >= DATE_SUB(CURDATE(), INTERVAL 7 DAY) AND n.status = 1"
  }
]
```

**Documentation (default_documentation.json):**

```json
[
  {
    "documentation": "The dg_notes table stores officer notes. Key columns: notes_id (PK), notes_description (text), note_date (date), user_id (officer username), facilities_id, status (1=active)."
  },
  {
    "documentation": "To get officer names, join dg_notes.user_id = dg_user.username (NOT dg_user.user_id which is INT)."
  }
]
```

### Training via API

Trigger training reload:

```bash
curl -X POST http://localhost:8000/train
```

**Response:**

```json
{
  "success": true,
  "examples_trained": 321,
  "documentation_trained": 45
}
```

### Training via Python Script

```python
from src.training.trainer import (
    train_from_defaults,
    train_examples,
    train_documentation,
    train_ddl,
    get_training_stats,
)

# Train from default files
result = train_from_defaults()
print(f"Trained {result['examples']} examples, {result['documentation']} docs")

# Train custom examples
train_examples("path/to/custom_examples.json")

# Train documentation
train_documentation("path/to/schema_docs.json")

# Train DDL statements
train_ddl([
    "CREATE TABLE dg_notes (notes_id INT PRIMARY KEY, notes_description TEXT, ...)",
    "CREATE TABLE dg_tags (tags_id INT PRIMARY KEY, emp_first_name VARCHAR(100), ...)",
])

# Check stats
stats = get_training_stats()
print(f"Total entries: {stats['total_entries']}")
```

### Adding New Training Examples

1. Edit `src/training/data/default_examples.json`
2. Add new question-SQL pairs
3. Trigger reload via API or restart server

**Tips for good training examples:**

- Include diverse query patterns (COUNT, SELECT, GROUP BY, JOIN)
- Cover common questions users ask
- Include date range variations
- Show proper JOIN syntax for your schema

---

## Document Ingestion (RAG)

The Document QA pipeline uses ChromaDB to store document chunks with embeddings. Before you can search documents, you need to index them.

### Supported File Types


| Type     | Extension | Library Required        |
| -------- | --------- | ----------------------- |
| PDF      | `.pdf`    | `pypdf` or `pdfplumber` |
| Word     | `.docx`   | `python-docx`           |
| Text     | `.txt`    | (built-in)              |
| Markdown | `.md`     | (built-in)              |


### Quick Start: Index Documents

The simplest way to index documents is using the built-in `DocumentIndexer`.

**From the project root, run Python:**

```bash
cd chatbot_copilot_poc
python
```

**Index a single file:**

```python
from src.pipelines.document_qa.indexer import index_file

# Index a PDF (sync function - blocks until done)
result = index_file("./docs/my_policy.pdf", customer_key="demo")
print(result)
# Output: {'success': True, 'doc_id': '...', 'filename': 'my_policy.pdf', 'chunks_indexed': 23, ...}
```

**Index an entire directory:**

```python
from src.pipelines.document_qa.indexer import index_directory

# Index all PDFs, DOCX, TXT, MD files in a folder (recursively)
result = index_directory(
    "./manuals/",           # Path to your documents folder
    customer_key="demo",    # Tenant isolation key
    recursive=True,         # Include subdirectories
    chunk_size=512,         # Characters per chunk
    chunk_overlap=50,       # Overlap between chunks
)

print(f"Files found: {result['files_found']}")
print(f"Files indexed: {result['files_indexed']}")
print(f"Total chunks: {result['total_chunks']}")

# See details for each file
for detail in result['details']:
    status = "✓" if detail['success'] else "✗"
    print(f"  {status} {detail['filename']}: {detail.get('chunks_indexed', 0)} chunks")
```

### Check What's Indexed

```python
from src.pipelines.document_qa.indexer import get_index_stats

stats = get_index_stats(customer_key="demo")
print(f"Total documents: {stats['total_documents']}")
print(f"Total chunks: {stats['total_chunks']}")

# List each document
for doc in stats['documents']:
    print(f"  - {doc['filename']} ({doc['chunk_count']} chunks)")
```

### Delete a Document

```python
from src.pipelines.document_qa.indexer import DocumentIndexer

indexer = DocumentIndexer(customer_key="demo")

# First, find the doc_id from stats
stats = indexer.get_stats()
for doc in stats['documents']:
    print(f"{doc['doc_id']}: {doc['filename']}")

# Delete by doc_id
deleted_count = indexer.delete_document(doc_id="abc-123-def-456")
print(f"Removed {deleted_count} chunks")
```

### Using in Async Code

If you're integrating into an async application (e.g., FastAPI endpoint):

```python
import asyncio
from src.pipelines.document_qa.indexer import DocumentIndexer

async def ingest_uploaded_file(file_bytes: bytes, filename: str):
    indexer = DocumentIndexer(customer_key="demo")
    
    # Determine file type from extension
    file_type = filename.rsplit(".", 1)[-1].lower()  # "pdf", "docx", etc.
    
    # Index from bytes (useful for file uploads)
    result = await indexer.index_bytes(
        data=file_bytes,
        filename=filename,
        file_type=file_type,
    )
    return result

# Or index a file path asynchronously
async def ingest_file(path: str):
    indexer = DocumentIndexer(customer_key="demo")
    return await indexer.index_file(path)
```

### Full Example: Batch Ingest Script

Create a script `ingest.py` in your project:

```python
#!/usr/bin/env python
"""Ingest documents into the Document QA pipeline."""

import sys
from src.pipelines.document_qa.indexer import index_directory, get_index_stats

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python ingest.py /path/to/documents [tenant]")
        sys.exit(1)
    
    doc_path = sys.argv[1]
    tenant = sys.argv[2] if len(sys.argv) > 2 else "demo"
    
    print(f"Indexing documents from: {doc_path}")
    print(f"Tenant: {tenant}")
    print("-" * 40)
    
    result = index_directory(doc_path, customer_key=tenant)
    
    print(f"\nResults:")
    print(f"  Files found:   {result['files_found']}")
    print(f"  Files indexed: {result['files_indexed']}")
    print(f"  Files failed:  {result['files_failed']}")
    print(f"  Total chunks:  {result['total_chunks']}")
    
    if result['files_failed'] > 0:
        print("\nFailed files:")
        for d in result['details']:
            if not d['success']:
                print(f"  - {d['filename']}: {d['error']}")
    
    print("\n" + "-" * 40)
    stats = get_index_stats(customer_key=tenant)
    print(f"Store now has {stats['total_documents']} documents, {stats['total_chunks']} chunks")
```

Run it:

```bash
python ingest.py ./manuals/ demo
```

### Document Storage Location

Documents are stored in ChromaDB at the path specified by `DOC_CHROMA_DIR`:

```
./chroma_docs/
└── docs_{tenant}/     # Per-tenant collection (e.g., docs_demo)
    └── (ChromaDB internal files)
```

Configure via environment variable:

```env
DOC_CHROMA_DIR=./chroma_docs
```

### Tenant Isolation

Each `customer_key` creates a separate ChromaDB collection. Documents indexed with `customer_key="acme"` are completely isolated from `customer_key="demo"`. This ensures multi-tenant data separation.

---

## Daily Activity Pipeline (Compliance)

The Daily Activity pipeline checks scheduled activities against database records to identify missed and upcoming tasks. It auto-executes on scope selection and supports the "refresh" keyword for updates.

### How It Works

1. **Auto-Execute on Scope Selection**: When you select the Daily Activity scope, the pipeline automatically runs an activity check.

2. **Timetable Comparison**: The system compares scheduled activities from the timetable JSON against actual database records.

3. **Multi-Facility Support**: Results are aggregated across all facilities assigned to the user.

4. **Refresh Keyword**: Type "refresh" to re-run the activity check and get updated results.

### Response Format

The pipeline generates template-based summaries (no LLM calls) with:

- **Missed activities**: Tasks scheduled but not recorded in the lookback window
- **Upcoming activities**: Tasks scheduled in the lookahead window
- Full duration format: `(HH:MM-HH:MM)`
- Per-facility breakdown for multi-facility users

### Example Response (Single Facility)

```
You have **3 missed** and **5 upcoming** activities for Main Block.

⚠️ **Missed (last 8h):**
- Count-Official (03:00-04:00)
- Pill Call (04:45-05:30)
- Chow Call (05:00-07:00)

📌 **Upcoming (next 4h):**
- Recreation (10:00-11:00)
- Count-Official (11:00-12:00)
- Chow Call (12:00-14:00)
- Pill Call (13:00-13:30)
- 1st Block/Program (09:30-11:30)

💡 Type "refresh" to update.
```

### Example Response (Multi-Facility)

```
Across **2 facilities**, you have **5 missed** and **8 upcoming** activities.

🏢 **Main Block** — 3 missed, 4 upcoming
⚠️ Missed: Count-Official (03:00-04:00), Pill Call (04:45-05:30), Chow Call (05:00-07:00)
📌 Upcoming: Recreation (10:00-11:00), Count-Official (11:00-12:00), Chow Call (12:00-14:00), Pill Call (13:00-13:30)

🏢 **East Wing** — 2 missed, 4 upcoming
⚠️ Missed: Count-Official (03:00-04:00), Sanitation Check (06:00-06:30)
📌 Upcoming: Medical Rounds (09:45-10:15), Count-Official (11:00-12:00), Chow Call (12:00-14:00), Pill Call (13:00-13:30)

💡 Type "refresh" to update.
```

### Timetable Management

Timetables are JSON files that define scheduled activities per day. The system uses a fallback lookup order:

1. `{TIMETABLE_DIR}/{customer_key}/{facility_id}.json` — per-facility
2. `{TIMETABLE_DIR}/{customer_key}/default.json` — per-tenant default
3. `{TIMETABLE_DIR}/default.json` — global default

#### Timetable Format

```json
[
  {
    "day": "Monday",
    "tasks": [
      {
        "task": "Count-Official",
        "start_time": "03:00:00",
        "end_time": "04:00:00",
        "keywords": "Official Count |",
        "statuses": {}
      },
      {
        "task": "Pill Call",
        "start_time": "04:45:00",
        "end_time": "05:30:00",
        "keywords": "Pill Call |, Medical |",
        "statuses": {}
      }
    ]
  }
]
```

#### Converting CSV to JSON

Use the included utility to convert CSV timetables to JSON format:

```bash
python -m src.pipelines.daily_activity.process_timetable input.csv output.json
```

**CSV Format:**

```csv
Time,Keywords,Statuses,Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday
0300-0400,Official Count |,,Count-Official,Count-Official,Count-Official,Count-Official,Count-Official,Count-Official,Count-Official
0445-0530,Pill Call |,,Pill Call,Pill Call,Pill Call,Pill Call,Pill Call,Pill Call,Pill Call
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DAILY_ACTIVITY_LOOKBACK_HOURS` | `8.0` | Hours to look back for missed activities |
| `DAILY_ACTIVITY_LOOKAHEAD_HOURS` | `4.0` | Hours to look ahead for upcoming activities |
| `DAILY_ACTIVITY_TOLERANCE_MINUTES` | `0` | Additional tolerance after task end time |
| `DAILY_ACTIVITY_TIMETABLE_DIR` | `src/pipelines/daily_activity/data/timetables` | Timetable directory path |

---

## Response Summarization (Inmate Data Pipeline)

The Inmate Data pipeline uses **LLM-enhanced summarization** to generate natural language responses from SQL query results. This provides dense, officer-friendly summaries instead of raw data tables.

### How It Works

1. **Insight Extraction** (fast, deterministic): 
   - `InsightExtractor` computes key statistics from query results
   - Calculates totals, date ranges, top categories, red flags, etc.
   - Pure Python — no external calls, ~5ms

2. **LLM Polish** (~1s latency):
   - `ResponseSummarizer` sends structured stats to LLM
   - Generates 2-3 sentence natural language summary
   - Includes follow-up question suggestions

3. **Smart Routing**:
   - Simple count queries (e.g., "how many?") skip LLM entirely
   - Complex multi-row results use full summarization

### Example Transformation

**Query**: "show notes from last 30 days"

**Raw Data**: 500 rows with notes_id, description, date, keyword, officer...

**Old Response (Template)**:
```
Found **500 notes** from Mar 01 to Mar 15.
Categories: Fire Watch (120), Rounds (98)...

• Mar 15, 10:30 AM — Inmate completed fire drill...
• Mar 15, 09:15 AM — Routine cell inspection...
+495 more entries
```

**New Response (LLM-Summarized)**:
```
500 notes recorded over the past 30 days. Fire Watch leads at 24%, 
followed by Rounds (20%). Richard Bell is the most active officer 
with 50 entries. 3 red-flagged items need attention, peaking on Mar 12.

Want to see the red-flagged entries?
```

### Benefits

| Aspect | Template (Old) | LLM-Summarized (New) |
|--------|----------------|----------------------|
| Information density | Low | High |
| Natural language | Stilted | Conversational |
| Follow-up suggestions | None | Included |
| Red flag highlighting | Basic | Prominent |
| Accuracy | 100% | 100% (numbers from code) |
| Latency | ~0ms | ~1-1.5s |

### Components

| File | Purpose |
|------|---------|
| `insight_extractor.py` | Extracts structured stats from rows |
| `response_summarizer.py` | Generates LLM summaries from stats |
| `response_formatter.py` | Main entry point, integrates both |

### Customizing the Summarizer

The LLM prompt is in `response_summarizer.py`:

```python
SUMMARIZER_SYSTEM_PROMPT = """You are a helpful assistant for correctional officers.
Your job is to summarize database query results into clear, dense natural language.
Officers are busy — they need quick, scannable answers.
...
"""
```

---

## Configuration

### Environment Variables Reference


| Variable                 | Default                  | Description                         |
| ------------------------ | ------------------------ | ----------------------------------- |
| `ENVIRONMENT`            | `dev`                    | Environment name (dev/staging/prod) |
| `OPENAI_API_KEY`         | (required)               | OpenAI API key                      |
| `LLM_PROVIDER`           | `openai`                 | LLM provider (openai/gemini)        |
| `LLM_MODEL`              | `gpt-4o-mini`            | Model for SQL/answer generation     |
| `LLM_TEMPERATURE`        | `0.1`                    | LLM temperature                     |
| `CHROMA_STORAGE_DIR`     | `./chroma_db`            | Vanna training data ChromaDB path   |
| `DOC_CHROMA_DIR`         | `./chroma_docs`          | Document QA ChromaDB path           |
| `DOC_EMBEDDING_MODEL`    | `text-embedding-3-small` | Embedding model                     |
| `DOC_RETRIEVAL_TOP_K`    | `5`                      | Number of chunks to retrieve        |
| `DOC_HYBRID_SEARCH`      | `true`                   | Enable BM25 + semantic hybrid       |
| `VALKEY_HOST`            | `localhost`              | Redis/Valkey host for sessions      |
| `VALKEY_PORT`            | `6379`                   | Redis/Valkey port                   |
| `REDIS_HOST`             | `localhost`              | Local Redis host for STM            |
| `REDIS_PORT`             | `6379`                   | Local Redis port for STM            |
| `SESSION_BACKEND`        | `auto`                   | `auto`, `redis`, `valkey`, `memory` (tests only) |
| `LOCAL_SESSION_BACKEND`  | `redis`                  | Local STM backend                   |
| `PROD_SESSION_BACKEND`   | `valkey`                 | Prod/staging STM backend            |
| `LTM_BACKEND`            | `auto`                   | `auto`, `sqlite`, `dynamodb`, `noop` (tests only) |
| `LOCAL_LTM_BACKEND`      | `sqlite`                 | Local LTM backend                   |
| `PROD_LTM_BACKEND`       | `dynamodb`               | Prod/staging LTM backend            |
| `LOCAL_LTM_SQLITE_PATH`  | `./local/conversation_store.db` | Local SQLite LTM path         |
| `SESSION_TTL_SECONDS`    | `3600`                   | Session timeout (1 hour)            |
| `ENABLE_GUARDRAILS`      | `true`                   | Enable input validation             |
| `MAX_QUERY_RESULTS`      | `500`                    | Max rows returned from SQL          |
| `MAX_CONVERSATION_TURNS` | `15`                     | Max turns kept per scope in STM     |


### Pipeline-Specific Config


| Variable                  | Default | Description                    |
| ------------------------- | ------- | ------------------------------ |
| `INMATE_PIPELINE_TIMEOUT` | `30`    | SQL pipeline timeout (seconds) |
| `DOC_PIPELINE_TIMEOUT`    | `30`    | Document pipeline timeout      |
| `DOC_RERANKING_ENABLED`   | `false` | Enable cross-encoder reranking |


---

## Testing

### Run All Tests

```bash
# Full test suite
python -m pytest tests/ src/orchestrator/tests/ src/pipelines/*/tests/ -v

# With coverage
python -m pytest --cov=src --cov-report=html
```

### Run Specific Test Categories

```bash
# Unit tests only
python -m pytest tests/unit/ -v

# Integration tests
python -m pytest tests/integration/ -v

# Orchestrator tests
python -m pytest src/orchestrator/tests/ -v

# Pipeline tests
python -m pytest src/pipelines/inmate_data/tests/ -v
python -m pytest src/pipelines/document_qa/tests/ -v
```

### Manual API Testing

```bash
# Health check
curl http://localhost:8000/health

# Pipeline health
curl http://localhost:8000/pipelines/health/inmate_data
curl http://localhost:8000/pipelines/health/document_qa

# Chat test
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question": "hello",
    "customer_key": "demo",
    "user_id": "test"
  }'
```

### Testing Vanna SQL Generation

```python
from src.pipelines.inmate_data.vanna_agent import generate_sql_via_llm_sync

# Test SQL generation
sql = generate_sql_via_llm_sync(
    question="How many notes were added today?",
    context="",
    user_id="test"
)
print(f"Generated SQL:\n{sql}")
```

---

## Troubleshooting

### Common Issues

#### "ChromaDB not available"

**Cause**: ChromaDB directory doesn't exist or is corrupted.

**Fix**:

```bash
# Remove and recreate
rm -rf ./chroma_db
python -c "from src.pipelines.inmate_data.vanna_agent import get_agent_memory; print(get_agent_memory())"
```

#### "OpenAI API key not found"

**Cause**: Missing `OPENAI_API_KEY` environment variable.

**Fix**:

```bash
export OPENAI_API_KEY=sk-your-key-here
# Or add to .env file
```

#### "Session not found or expired"

**Cause**: Session expired (default: 1 hour) or configured STM backend unavailable.

**Fix**:

- Increase `SESSION_TTL_SECONDS`
- Start a new session
- Verify local Redis is running (default STM backend)
- For tests only, use `SESSION_BACKEND=memory`

#### "Session backend 'redis' is unavailable: Error 111 connecting to localhost:6379"

**Cause**: Local Redis process is not running.

**Fix**:

```bash
# Start Redis locally
redis-server

# Or run Redis in Docker
docker run --name copilot-redis -p 6379:6379 -d redis:7

# Then start app
python -m local.server
```

#### "Unknown scope: xxx"

**Cause**: Pipeline not registered.

**Fix**: Ensure pipelines are imported:

```python
import src.pipelines.inmate_data
import src.pipelines.document_qa
```

#### SQL Generation Returns Errors

**Cause**: Insufficient training data or ambiguous question.

**Fix**:

1. Add more training examples
2. Be more specific in questions
3. Check ChromaDB has training data:
  ```python
   from src.training.trainer import get_training_stats
   print(get_training_stats())
  ```

#### Document Search Returns No Results

**Cause**: Documents not indexed or wrong tenant.

**Fix**:

```python
from src.pipelines.document_qa.documents.store import TenantDocumentStore
store = TenantDocumentStore(customer_key="demo")
print(f"Indexed chunks: {store.count()}")
print(f"Documents: {store.list_documents()}")
```

### Logs

Application logs are written to stdout. Configure log level:

```env
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

### Getting Help

1. Check the API docs: `http://localhost:8000/docs`
2. Review the architecture: `docs/ARCHITECTURE.md`
3. Check system flows: `docs/SYSTEM_FLOWS.md`

---

## Summary


| Task         | Command/Action                              |
| ------------ | ------------------------------------------- |
| Start server | `redis-server` then `python -m local.server` |
| Open UI      | `http://localhost:8000`                     |
| API docs     | `http://localhost:8000/docs`                |
| Train Vanna  | `curl -X POST http://localhost:8000/train`  |
| Ingest docs  | `python ingest_documents.py /path/to/docs/` |
| Run tests    | `python -m pytest tests/ -v`                |
| Health check | `curl http://localhost:8000/health`         |
