# InmateCopilot — System Flow Documentation

**Version**: 2.0
**Created**: 2026-03-19

---

## Table of Contents

1. [User Journey Flows](#user-journey-flows)
2. [API Request Flows](#api-request-flows)
3. [Pipeline Execution Flows](#pipeline-execution-flows)
4. [Memory & State Flows](#memory--state-flows)
5. [Error Handling Flows](#error-handling-flows)
6. [Edge Case Flows](#edge-case-flows)

---

## User Journey Flows

### Flow 1: New Session — First Time User

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        NEW SESSION FLOW                                          │
└─────────────────────────────────────────────────────────────────────────────────┘

User                          System                              Storage
  │                              │                                    │
  │  Opens chat interface        │                                    │
  │─────────────────────────────▶│                                    │
  │                              │                                    │
  │                              │  Check for session_id cookie       │
  │                              │  (none found)                      │
  │                              │                                    │
  │                              │  Create new Session                │
  │                              │────────────────────────────────────▶│
  │                              │  UUID, customer_key, user_id       │
  │                              │  active_scope = None               │
  │                              │                                    │
  │                              │                                    │
  │  ◀─────────────────────────── Sarah's Greeting + Scope Options   │
  │                              │                                    │
  │  ┌────────────────────────────────────────────────────────────┐  │
  │  │ "Hi! I'm Sarah. How can I help you today?"                 │  │
  │  │                                                            │  │
  │  │  ┌─────────────────┐  ┌─────────────────┐                 │  │
  │  │  │ 📊 Inmate Data  │  │ 📄 Documents    │                 │  │
  │  │  │ Query notes,    │  │ Search manuals, │                 │  │
  │  │  │ inmates, logs   │  │ guides, SOPs    │                 │  │
  │  │  └─────────────────┘  └─────────────────┘                 │  │
  │  └────────────────────────────────────────────────────────────┘  │
  │                              │                                    │
  │  Clicks "Inmate Data"        │                                    │
  │─────────────────────────────▶│                                    │
  │                              │                                    │
  │                              │  POST /scope/select               │
  │                              │  { scope: "inmate_data" }         │
  │                              │                                    │
  │                              │  Update session                    │
  │                              │────────────────────────────────────▶│
  │                              │  active_scope = "inmate_data"      │
  │                              │  scope_contexts["inmate_data"] = {}│
  │                              │                                    │
  │  ◀─────────────────────────── Scope Welcome                      │
  │                              │                                    │
  │  ┌────────────────────────────────────────────────────────────┐  │
  │  │ [📊 Inmate Data]                                [Switch]  │  │
  │  │                                                            │  │
  │  │ "Great! I can help you query inmate data — notes,         │  │
  │  │  inmates, officers, facilities. What would you like       │  │
  │  │  to know?"                                                 │  │
  │  └────────────────────────────────────────────────────────────┘  │
  │                              │                                    │
  ▼                              ▼                                    ▼
```

---

### Flow 2: Active Conversation — Inmate Data Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                   INMATE DATA QUERY FLOW                                         │
└─────────────────────────────────────────────────────────────────────────────────┘

User                     Orchestrator              Pipeline                 Storage
  │                           │                        │                        │
  │ "Show fire watch notes    │                        │                        │
  │  from today"              │                        │                        │
  │──────────────────────────▶│                        │                        │
  │                           │                        │                        │
  │                           │ Check active_scope     │                        │
  │                           │ = "inmate_data" ✓      │                        │
  │                           │                        │                        │
  │                           │ Dispatch to pipeline   │                        │
  │                           │───────────────────────▶│                        │
  │                           │                        │                        │
  │                           │                        │ 1. Validate question   │
  │                           │                        │    (guardrails)        │
  │                           │                        │                        │
  │                           │                        │ 2. Classify intent     │
  │                           │                        │    → DATA_QUERY        │
  │                           │                        │                        │
  │                           │                        │ 3. Build SQL context   │
  │                           │                        │    (conversation +     │
  │                           │                        │     training data)     │
  │                           │                        │                        │
  │                           │                        │ 4. Generate SQL        │
  │                           │                        │    (Vanna + LLM)       │
  │                           │                        │    ─────────────────────▶ ChromaDB
  │                           │                        │    ◀───────────────────── (similar Q&A)
  │                           │                        │                        │
  │                           │                        │ 5. Validate SQL        │
  │                           │                        │    - SELECT only       │
  │                           │                        │    - No sensitive cols │
  │                           │                        │                        │
  │                           │                        │ 6. Inject filters      │
  │                           │                        │    - status = 1        │
  │                           │                        │    - facilities_id IN  │
  │                           │                        │                        │
  │                           │                        │ 7. Execute query       │
  │                           │                        │    ─────────────────────▶ Aurora MySQL
  │                           │                        │    ◀───────────────────── (results)
  │                           │                        │                        │
  │                           │                        │ 8. Format response     │
  │                           │                        │                        │
  │                           │◀───────────────────────│                        │
  │                           │                        │                        │
  │                           │ 9. Save turn           │                        │
  │                           │    ─────────────────────────────────────────────▶ Valkey (STM)
  │                           │    ─────────────────────────────────────────────▶ DynamoDB (LTM)
  │                           │                        │                        │
  │                           │ 10. Update scope ctx   │                        │
  │                           │     recent_queries +=  │                        │
  │                           │     ["fire watch..."]  │                        │
  │                           │                        │                        │
  │◀──────────────────────────│                        │                        │
  │                           │                        │                        │
  │ ┌─────────────────────────────────────────────────────────────────────────┐ │
  │ │ "Found 23 fire watch notes from today."                                 │ │
  │ │                                                                         │ │
  │ │ ┌─────────────────────────────────────────────────────────────────────┐ │ │
  │ │ │ Note │ Inmate        │ Officer      │ Time   │ Status              │ │ │
  │ │ ├─────┼───────────────┼──────────────┼────────┼─────────────────────┤ │ │
  │ │ │ 1   │ Anthony Nova  │ Richard Bell │ 08:30  │ Fire Watch Started  │ │ │
  │ │ │ 2   │ Maria Santos  │ John Smith   │ 09:15  │ Fire Watch Check    │ │ │
  │ │ │ ... │ ...           │ ...          │ ...    │ ...                 │ │ │
  │ │ └─────────────────────────────────────────────────────────────────────┘ │ │
  │ └─────────────────────────────────────────────────────────────────────────┘ │
  │                           │                        │                        │
  ▼                           ▼                        ▼                        ▼
```

---

### Flow 3: Follow-Up Query (Context-Aware)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        FOLLOW-UP QUERY FLOW                                      │
└─────────────────────────────────────────────────────────────────────────────────┘

User                     Orchestrator              Pipeline                 Context
  │                           │                        │                        │
  │ Previous: "Show fire watch notes from today"       │   scope_ctx:           │
  │ Response: 23 notes with Anthony Nova first         │   recent_queries: [    │
  │                           │                        │     "fire watch..."    │
  │                           │                        │   ]                    │
  │                           │                        │   recent_entities: {   │
  │                           │                        │     inmate: "Anthony"  │
  │                           │                        │   }                    │
  │                           │                        │                        │
  │ "Show more details for    │                        │                        │
  │  that inmate"             │                        │                        │
  │──────────────────────────▶│                        │                        │
  │                           │                        │                        │
  │                           │ Route to inmate_data   │                        │
  │                           │───────────────────────▶│                        │
  │                           │                        │                        │
  │                           │                        │ 1. Classify intent     │
  │                           │                        │    → FOLLOW_UP         │
  │                           │                        │                        │
  │                           │                        │ 2. Rewrite question    │
  │                           │                        │    "that inmate"       │
  │                           │                        │          ↓             │
  │                           │                        │    "inmate Anthony     │
  │                           │                        │     Nova"              │
  │                           │                        │    (from scope_ctx)    │
  │                           │                        │                        │
  │                           │                        │ 3. Full question:      │
  │                           │                        │    "Show more details  │
  │                           │                        │     for inmate         │
  │                           │                        │     Anthony Nova"      │
  │                           │                        │                        │
  │                           │                        │ 4. Generate SQL...     │
  │                           │                        │    (continues as       │
  │                           │                        │     normal)            │
  │                           │                        │                        │
  │◀───────────────────────────────────────────────────│                        │
  │                           │                        │                        │
  │ Response with Anthony Nova's details               │                        │
  │                           │                        │                        │
  ▼                           ▼                        ▼                        ▼
```

---

### Flow 4: Scope Switching

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        SCOPE SWITCH FLOW                                         │
└─────────────────────────────────────────────────────────────────────────────────┘

User                     Orchestrator                              Storage
  │                           │                                        │
  │ Currently in: inmate_data │                                        │
  │ Context: Anthony Nova,    │                                        │
  │          fire watch       │                                        │
  │                           │                                        │
  │ Clicks [Switch] button    │                                        │
  │──────────────────────────▶│                                        │
  │                           │                                        │
  │◀──────────────────────────│ Return scope options                   │
  │                           │                                        │
  │ ┌─────────────────────────────────────────────────────────────┐   │
  │ │ "What would you like to work on?"                           │   │
  │ │                                                             │   │
  │ │  ┌─────────────────┐  ┌─────────────────┐                  │   │
  │ │  │ 📊 Inmate Data  │  │ 📄 Documents    │                  │   │
  │ │  │ (continue)      │  │                 │                  │   │
  │ │  └─────────────────┘  └─────────────────┘                  │   │
  │ └─────────────────────────────────────────────────────────────┘   │
  │                           │                                        │
  │ Clicks "Documents"        │                                        │
  │──────────────────────────▶│                                        │
  │                           │                                        │
  │                           │ POST /scope/select                    │
  │                           │ { scope: "document_qa" }              │
  │                           │                                        │
  │                           │                                        │
  │                           │ ┌────────────────────────────────────┐│
  │                           │ │ SCOPE TRANSITION                   ││
  │                           │ │                                    ││
  │                           │ │ 1. FREEZE inmate_data context      ││
  │                           │ │    scope_contexts["inmate_data"]=  ││────────▶│
  │                           │ │    {                               ││  Valkey │
  │                           │ │      recent_entities: {            ││         │
  │                           │ │        inmate: "Anthony Nova"      ││         │
  │                           │ │      },                            ││         │
  │                           │ │      recent_queries: [             ││         │
  │                           │ │        "fire watch notes...",      ││         │
  │                           │ │        "that inmate..."            ││         │
  │                           │ │      ]                             ││         │
  │                           │ │    }                               ││         │
  │                           │ │                                    ││         │
  │                           │ │ 2. UPDATE session                  ││         │
  │                           │ │    active_scope = "document_qa"    ││────────▶│
  │                           │ │    scope_history += "document_qa"  ││         │
  │                           │ │                                    ││         │
  │                           │ │ 3. LOAD/CREATE document_qa ctx     ││         │
  │                           │ │    scope_contexts["document_qa"]={}││         │
  │                           │ └────────────────────────────────────┘│         │
  │                           │                                        │         │
  │◀──────────────────────────│ Scope welcome                          │         │
  │                           │                                        │         │
  │ ┌─────────────────────────────────────────────────────────────┐   │         │
  │ │ [📄 Documents]                                    [Switch]  │   │         │
  │ │                                                             │   │         │
  │ │ "Now helping with Documents. What would you like to find?" │   │         │
  │ └─────────────────────────────────────────────────────────────┘   │         │
  │                           │                                        │         │
  │                           │                                        │         │
  │ Later: Switches back to   │                                        │         │
  │ "Inmate Data"             │                                        │         │
  │──────────────────────────▶│                                        │         │
  │                           │                                        │         │
  │                           │ RESTORE inmate_data context            │         │
  │                           │◀───────────────────────────────────────│─────────│
  │                           │                                        │  Valkey │
  │                           │                                        │         │
  │◀──────────────────────────│                                        │         │
  │                           │                                        │         │
  │ ┌─────────────────────────────────────────────────────────────┐   │         │
  │ │ "Welcome back to Inmate Data. Last time you were looking   │   │         │
  │ │  at fire watch notes for Anthony Nova. Continue from there │   │         │
  │ │  or ask something new!"                                    │   │         │
  │ └─────────────────────────────────────────────────────────────┘   │         │
  │                           │                                        │         │
  ▼                           ▼                                        ▼         │
```

---

### Flow 5: Document QA Pipeline

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                      DOCUMENT QA FLOW                                            │
└─────────────────────────────────────────────────────────────────────────────────┘

User                     Orchestrator              Pipeline                 Storage
  │                           │                        │                        │
  │ "What is the fire drill   │                        │                        │
  │  evacuation procedure?"   │                        │                        │
  │──────────────────────────▶│                        │                        │
  │                           │                        │                        │
  │                           │ Check active_scope     │                        │
  │                           │ = "document_qa" ✓      │                        │
  │                           │                        │                        │
  │                           │ Dispatch to pipeline   │                        │
  │                           │───────────────────────▶│                        │
  │                           │                        │                        │
  │                           │                        │ 1. Validate question   │
  │                           │                        │    (guardrails)        │
  │                           │                        │                        │
  │                           │                        │ 2. Generate query      │
  │                           │                        │    embedding           │
  │                           │                        │    ─────────────────────▶ OpenAI
  │                           │                        │    ◀───────────────────── (embedding)
  │                           │                        │                        │
  │                           │                        │ 3. HYBRID RETRIEVAL    │
  │                           │                        │                        │
  │                           │                        │    a. Semantic search  │
  │                           │                        │       ─────────────────▶ ChromaDB
  │                           │                        │       (docs_{tenant})  │
  │                           │                        │       ◀─────────────────  top 20
  │                           │                        │                        │
  │                           │                        │    b. BM25 search      │
  │                           │                        │       ─────────────────▶ BM25 Index
  │                           │                        │       ◀─────────────────  top 20
  │                           │                        │                        │
  │                           │                        │    c. RRF fusion       │
  │                           │                        │       merge → top 5    │
  │                           │                        │                        │
  │                           │                        │ 4. (Optional) Rerank   │
  │                           │                        │    cross-encoder       │
  │                           │                        │                        │
  │                           │                        │ 5. SYNTHESIZE answer   │
  │                           │                        │    ─────────────────────▶ OpenAI
  │                           │                        │    Context: [chunks]   │
  │                           │                        │    Question: [query]   │
  │                           │                        │    ◀───────────────────── (answer)
  │                           │                        │                        │
  │                           │                        │ 6. Format with sources │
  │                           │                        │                        │
  │                           │◀───────────────────────│                        │
  │                           │                        │                        │
  │                           │ 7. Save turn           │                        │
  │                           │    (scope: document_qa)│                        │
  │                           │    ─────────────────────────────────────────────▶ Valkey
  │                           │    ─────────────────────────────────────────────▶ DynamoDB
  │                           │                        │                        │
  │◀──────────────────────────│                        │                        │
  │                           │                        │                        │
  │ ┌─────────────────────────────────────────────────────────────────────────┐ │
  │ │ "Based on the Emergency Procedures Manual (Section 4.2):               │ │
  │ │                                                                         │ │
  │ │  Fire drill evacuation procedure:                                      │ │
  │ │  1. Sound alarm and announce evacuation                                │ │
  │ │  2. Officers escort inmates to designated assembly areas               │ │
  │ │  3. Conduct headcount within 5 minutes                                 │ │
  │ │  4. Report count to shift supervisor via radio                         │ │
  │ │  5. Remain at assembly point until all-clear given                     │ │
  │ │                                                                         │ │
  │ │  📄 Sources:                                                           │ │
  │ │  - emergency_procedures.pdf (Section 4.2, p.12)                        │ │
  │ │  - facility_safety_guide.pdf (Chapter 3, p.8)                          │ │
  │ └─────────────────────────────────────────────────────────────────────────┘ │
  │                           │                        │                        │
  ▼                           ▼                        ▼                        ▼
```

---

## API Request Flows

### POST /chat — Unified Chat Endpoint

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        POST /chat FLOW                                           │
└─────────────────────────────────────────────────────────────────────────────────┘

Request:
{
    "question": "Show fire watch notes",
    "session_id": "abc-123",
    "customer_key": "demo",
    "user_id": "richard.bell",
    "facility_ids": [101, 102, 103]
}

                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 1. MIDDLEWARE                                                                    │
│    - Extract customer_key from header/body                                      │
│    - Validate auth token                                                         │
│    - Rate limiting check                                                         │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│ 2. SESSION RESOLUTION                                                            │
│    - Load session from Valkey (or create new)                                   │
│    - Resolve tenant context                                                      │
│    - Check active_scope                                                          │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                        ┌───────────────┴───────────────┐
                        │                               │
                active_scope = None              active_scope != None
                        │                               │
                        ▼                               ▼
┌───────────────────────────────────┐ ┌───────────────────────────────────────────┐
│ 3a. NO SCOPE                      │ │ 3b. ORCHESTRATOR                          │
│     Return scope options          │ │     Check cross-scope handlers            │
│                                   │ │     - is_greeting()?                      │
│ {                                 │ │     - is_recall()?                        │
│   "requires_scope": true,         │ │     - is_help()?                          │
│   "options": [                    │ │                                           │
│     { "id": "inmate_data", ...},  │ │     If none → dispatch to pipeline        │
│     { "id": "document_qa", ...}   │ │                                           │
│   ]                               │ │                                           │
│ }                                 │ │                                           │
└───────────────────────────────────┘ └───────────────────────────────────────────┘
                                                        │
                                                        ▼
                                      ┌───────────────────────────────────────────┐
                                      │ 4. PIPELINE DISPATCH                      │
                                      │    pipeline = registry.get(active_scope)  │
                                      │    response = await pipeline.process(..   │
                                      └───────────────────────────────────────────┘
                                                        │
                                                        ▼
                                      ┌───────────────────────────────────────────┐
                                      │ 5. SAVE & RESPOND                         │
                                      │    - Save turn to STM + LTM               │
                                      │    - Update scope context                 │
                                      │    - Return response                      │
                                      └───────────────────────────────────────────┘
                                                        │
                                                        ▼
Response:
{
    "summary": "Found 23 fire watch notes...",
    "data": [...],
    "row_count": 23,
    "scope": "inmate_data",
    "session_id": "abc-123"
}
```

### POST /scope/select — Scope Selection

```
Request:
{
    "session_id": "abc-123",
    "scope": "document_qa"
}

                │
                ▼
┌─────────────────────────────────────────┐
│ 1. Load session from Valkey             │
│ 2. Validate scope exists in registry    │
│ 3. Freeze current scope context         │
│ 4. Update active_scope                  │
│ 5. Load/create new scope context        │
│ 6. Save session                         │
│ 7. Return welcome message               │
└─────────────────────────────────────────┘
                │
                ▼
Response:
{
    "message": "Now helping with Documents...",
    "scope": "document_qa",
    "previous_scope": "inmate_data"
}
```

---

## Memory & State Flows

### STM (Short-Term Memory) — Valkey

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        VALKEY SESSION STRUCTURE                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

Key: "session:{session_id}"
TTL: 3600 seconds (1 hour)

Value (JSON):
{
    "session_id": "abc-123-def-456",
    "customer_key": "demo",
    "user_id": "richard.bell",
    "facility_ids": [101, 102, 103],
    "role": "officer",
    "display_name": "Richard Bell",

    "active_scope": "inmate_data",           // Current scope
    "scope_history": [                        // Navigation history
        "inmate_data",
        "document_qa",
        "inmate_data"
    ],

    "scope_contexts": {                       // Per-scope working memory
        "inmate_data": {
            "scope": "inmate_data",
            "recent_entities": {
                "inmate_name": "Anthony Nova",
                "facility": "Dorm B"
            },
            "recent_queries": [
                "fire watch notes from today",
                "that inmate's status history"
            ],
            "last_active": 1710864000.0
        },
        "document_qa": {
            "scope": "document_qa",
            "recent_entities": {
                "last_docs": ["fire_safety.pdf"]
            },
            "recent_queries": [
                "fire drill procedure"
            ],
            "last_active": 1710863500.0
        }
    },

    "turns": [                                // Last 15 turns
        {
            "role": "user",
            "content": "fire watch notes from today",
            "scope": "inmate_data",
            "timestamp": 1710864000.0
        },
        {
            "role": "assistant",
            "content": "Found 23 fire watch notes...",
            "scope": "inmate_data",
            "timestamp": 1710864002.0,
            "sql": "SELECT ... FROM dg_notes ...",
            "row_count": 23
        }
    ],

    "created_at": 1710860000.0,
    "last_active": 1710864002.0
}
```

### LTM (Long-Term Memory) — DynamoDB

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        DYNAMODB CONVERSATION STORE                               │
└─────────────────────────────────────────────────────────────────────────────────┘

Table: InmateCopilot-Conversations

Partition Key: "pk" = "{customer_key}#{user_id}"
Sort Key: "sk" = "{session_id}#{timestamp}"

Item Structure:
{
    "pk": "demo#richard.bell",
    "sk": "abc-123#1710864000",

    "session_id": "abc-123-def-456",
    "customer_key": "demo",
    "user_id": "richard.bell",

    "role": "user",
    "content": "fire watch notes from today",
    "scope": "inmate_data",              // NEW: Scope tag

    "sql": null,                          // assistant turns have SQL
    "row_count": null,

    "timestamp": 1710864000,
    "ttl": 1718640000                     // 90 days from now
}

Queries:
---------
1. Get user's history (all scopes):
   Query: pk = "demo#richard.bell"
   ScanIndexForward: false (newest first)
   Limit: 50

2. Get user's history (specific scope):
   Query: pk = "demo#richard.bell"
   FilterExpression: scope = "inmate_data"

3. Get session turns:
   Scan with FilterExpression: session_id = "abc-123"
```

---

## Error Handling Flows

### Pipeline Error Recovery

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        ERROR RECOVERY FLOW                                       │
└─────────────────────────────────────────────────────────────────────────────────┘

                    User Question
                          │
                          ▼
                ┌─────────────────┐
                │   Validation    │
                └────────┬────────┘
                         │
              ┌──────────┴──────────┐
              │                     │
         Valid ✓                Invalid ✗
              │                     │
              ▼                     ▼
    ┌─────────────────┐   ┌─────────────────────────────┐
    │  Generate SQL   │   │ Return validation error     │
    └────────┬────────┘   │ "I can't process that      │
             │            │  question because: {reason}" │
             │            └─────────────────────────────┘
             │
    SQL Generated?
    ┌──────┴──────┐
    │             │
   Yes           No
    │             │
    ▼             ▼
┌────────┐  ┌─────────────────────────────┐
│Validate│  │ Return generation error     │
│  SQL   │  │ "I couldn't understand how  │
└───┬────┘  │  to query that. Try: ..."   │
    │       └─────────────────────────────┘
    │
SQL Valid?
┌──────┴──────┐
│             │
Yes          No → Retry with feedback
│             │
│             ▼
│       ┌─────────────────┐
│       │  Retry once     │
│       │  with error     │
│       │  feedback       │
│       └────────┬────────┘
│                │
│         Still invalid?
│         ┌──────┴──────┐
│         │             │
│        Yes           No
│         │             │
│         ▼             │
│  ┌─────────────┐      │
│  │Return error │      │
│  │with details │      │
│  └─────────────┘      │
│                       │
└───────────┬───────────┘
            │
            ▼
    ┌─────────────────┐
    │   Execute SQL   │
    └────────┬────────┘
             │
    Execution OK?
    ┌──────┴──────┐
    │             │
   Yes           No → Retry with error
    │             │
    ▼             ▼
┌────────┐  ┌─────────────────┐
│ Format │  │  Retry once     │
│Response│  │  with execution │
└───┬────┘  │  error feedback │
    │       └────────┬────────┘
    │                │
    │         Still fails?
    │         ┌──────┴──────┐
    │         │             │
    │        Yes           No
    │         │             │
    │         ▼             │
    │  ┌─────────────┐      │
    │  │Return error │      │
    │  │"Query failed│      │
    │  │ {details}"  │      │
    │  └─────────────┘      │
    │                       │
    └───────────┬───────────┘
                │
                ▼
         Return Response
```

---

## Edge Case Flows

### Edge Case 1: No Scope Selected, User Types

```
User types: "Show fire watch notes"

active_scope = None
        │
        ▼
┌─────────────────────────────────────────────┐
│ Orchestrator detects no active scope        │
│                                             │
│ Response:                                   │
│ "I'd love to help with that! Please select │
│  an option above so I know how to assist." │
│                                             │
│  ┌───────────────┐  ┌───────────────┐      │
│  │📊 Inmate Data │  │📄 Documents   │      │
│  └───────────────┘  └───────────────┘      │
└─────────────────────────────────────────────┘
```

### Edge Case 2: Greeting Before Scope Selection

```
User types: "Hello!"

active_scope = None
        │
        ▼
┌─────────────────────────────────────────────┐
│ CrossScopeHandler.is_greeting() → True      │
│                                             │
│ Response:                                   │
│ "Hi there! I'm Sarah, your assistant.      │
│  Please select what you'd like help with:" │
│                                             │
│  ┌───────────────┐  ┌───────────────┐      │
│  │📊 Inmate Data │  │📄 Documents   │      │
│  └───────────────┘  └───────────────┘      │
└─────────────────────────────────────────────┘
```

### Edge Case 3: Cross-Scope Question

```
User in document_qa asks: "What was that inmate's name from earlier?"

active_scope = "document_qa"
        │
        ▼
┌─────────────────────────────────────────────┐
│ CrossScopeHandler.is_recall() → True        │
│                                             │
│ Access scope_contexts["inmate_data"]        │
│ recent_entities.inmate_name = "Anthony Nova"│
│                                             │
│ Response:                                   │
│ "Earlier in Inmate Data, you were asking   │
│  about Anthony Nova."                       │
│                                             │
│ (Stay in document_qa scope)                 │
└─────────────────────────────────────────────┘
```

### Edge Case 4: Session Timeout Recovery

```
User returns after session expired (>1 hour)

Session not found in Valkey
        │
        ▼
┌─────────────────────────────────────────────┐
│ 1. Create new session                       │
│ 2. Check DynamoDB for user history          │
│    Query: pk = "demo#richard.bell"          │
│                                             │
│ History found:                              │
│ - Last session 2 hours ago                  │
│ - Was asking about fire watch              │
│                                             │
│ Response:                                   │
│ "Welcome back! I see you were previously   │
│  working with Inmate Data. Would you like  │
│  to continue there?"                        │
│                                             │
│  ┌───────────────┐  ┌───────────────┐      │
│  │📊 Inmate Data │  │📄 Documents   │      │
│  │ (recommended) │  │               │      │
│  └───────────────┘  └───────────────┘      │
└─────────────────────────────────────────────┘
```

---

## Summary

This document covers all user journey flows, API request flows, memory state management, error handling, and edge cases for the InmateCopilot V2 guided conversational agent system.

Key flows:
1. **New Session** → Greeting + scope options
2. **Scope Selection** → Pipeline activation
3. **Query Processing** → Pipeline-specific flow
4. **Follow-Up** → Context-aware rewriting
5. **Scope Switching** → Context preservation
6. **Error Recovery** → Retry with feedback
7. **Edge Cases** → Graceful handling
