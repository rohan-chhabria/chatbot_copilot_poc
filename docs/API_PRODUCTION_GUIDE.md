# InmateCopilot — Production API Guide

> For the frontend team consuming the deployed InmateCopilot chatbot API.
> Deployment: ECS Fargate behind ALB.
> Production entry: `src.api.handler:app` via uvicorn.
> Monitoring: Sentry (unhandled exceptions, performance tracing).
> Updated: 2026-05-21 (Interaction 3)

---

## Base URL

| Environment | URL |
|-------------|-----|
| Production | `https://{your-alb-domain}/` |
| Staging | `https://{staging-alb-domain}/` |
| Local Dev | `http://localhost:8000` (uvicorn) or `http://localhost:8065` (local.server with UI) |

---

## Authentication & Headers

**Current state**: No server-side authentication. CORS is configurable per deployment via `ALLOWED_ORIGINS` env var (default: `*` for dev, production should be set to the frontend domain). Your frontend or API gateway must handle auth before reaching this API.

**Required headers for POST requests**:
```
Content-Type: application/json
```

**Response headers**:
```
X-Request-Id: abc12345    ← unique per request, use for debugging/Sentry correlation
```

---

## Complete Frontend Integration Flow

### Flow 1: First-Time User (New Session)

```
┌──────────┐                              ┌──────────────┐
│ Frontend │                              │ InmateCopilot│
└────┬─────┘                              └──────┬───────┘
     │                                           │
     │  1. GET /scope/options                    │
     │ ─────────────────────────────────────────>│
     │  ← {options: [...3 scopes...]}            │
     │ <─────────────────────────────────────────│
     │                                           │
     │  Render scope selection cards in UI       │
     │                                           │
     │  2. POST /chat {question:"hello",         │
     │     customer_key:"demo", user_id:"R.B"}   │
     │ ─────────────────────────────────────────>│
     │  ← {session_id:"abc-123",                 │
     │     requires_scope:true, options:[...]}   │
     │ <─────────────────────────────────────────│
     │                                           │
     │  ★ PERSIST session_id="abc-123"           │
     │                                           │
     │  3. User clicks "Inmate Data" card        │
     │  POST /scope/select                       │
     │  {session_id:"abc-123",                   │
     │   scope:"inmate_data"}                    │
     │ ─────────────────────────────────────────>│
     │  ← {scope:"inmate_data",                  │
     │     summary:"Welcome to Inmate Data..."}  │
     │ <─────────────────────────────────────────│
     │                                           │
     │  4. User types a question                 │
     │  POST /chat/stream                        │
     │  {question:"show fire watch notes",       │
     │   session_id:"abc-123",                   │
     │   customer_key:"demo", user_id:"R.B"}     │
     │ ─────────────────────────────────────────>│
     │  ← SSE stream:                            │
     │     event:session → {session_id}          │
     │     event:result  → {summary, row_count}  │
     │     event:done                            │
     │ <─────────────────────────────────────────│
     │                                           │
     │  5. Continue conversation loop (repeat 4) │
```

### Flow 2: Returning User (Existing Session)

```
Frontend has session_id from previous interaction
     │
     │  POST /chat/stream {question, session_id, customer_key, user_id}
     │ ──────────────────────────────────────────>
     │  ← SSE stream with results
     │ <──────────────────────────────────────────
```

### Flow 3: Expired Session

```
Frontend sends stale session_id
     │
     │  POST /chat {question, session_id:"stale-id", ...}
     │ ──────────────────────────────────────────>
     │  ← {success:false, error:"session_expired"}
     │ <──────────────────────────────────────────
     │
     │  Frontend: discard session_id, retry without it
     │  POST /chat {question, customer_key, user_id}  ← no session_id
     │ ──────────────────────────────────────────>
     │  ← {session_id:"new-456", ...}
     │ <──────────────────────────────────────────
```

### Flow 4: Switching Scopes Mid-Conversation

```
User is in "inmate_data", wants to switch to "document_qa"
     │
     │  POST /scope/select {session_id, scope:"document_qa"}
     │ ──────────────────────────────────────────>
     │  ← {scope:"document_qa",
     │     previous_scope:"inmate_data",
     │     summary:"Welcome to Documents..."}
     │ <──────────────────────────────────────────
     │
     │  Previous scope context is preserved.
     │  Switching back later shows last question in that scope.
```

### Flow 5: Daily Activity (Auto-Execute Scope)

```
User selects "daily_activity" scope
     │
     │  POST /scope/select {session_id, scope:"daily_activity"}
     │ ──────────────────────────────────────────>
     │  ← {scope:"daily_activity",
     │     summary:"Welcome...\n\nMissed: Roll Call (9:00 AM)
     │             Upcoming: Lunch Count (12:00 PM)"}
     │ <──────────────────────────────────────────
     │
     │  ★ No initial question needed — auto-executes compliance check
     │  User can ask follow-up questions normally after this
```

---

## API Call Order (Required Sequence)

```
Step 1: GET  /scope/options                   ← Bootstrap: fetch scope cards for UI
Step 2: POST /chat {no session_id}            ← First message: server creates session
Step 3: ★ PERSIST returned session_id         ← Critical: all future calls need this
Step 4: POST /scope/select                    ← User picks a scope
Step 5: POST /chat or POST /chat/stream       ← Conversation loop (repeat)

Optional at any time:
  - POST /scope/select                        ← Switch scope
  - GET  /session/{session_id}                ← Debug session state
  - GET  /history?customer_key=X&user_id=Y    ← User's full history
```

---

## Endpoint Reference

### POST /chat

**Request**:
```json
{
  "question": "show fire watch notes for last week",
  "customer_key": "demo",
  "user_id": "Richard.Bell",
  "session_id": "abc-123-def",
  "facility_ids": [63, 164],
  "role": "officer"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| question | string | Yes | 1-1000 chars |
| customer_key | string | Yes | Tenant identifier from your auth system |
| user_id | string | Yes | Format: `Firstname.Lastname` |
| session_id | string | No | Omit for first message; include for all subsequent |
| facility_ids | int[] | No | Scopes SQL queries to these facilities |
| role | string | No | Default: `"officer"` |

**Response** — three shapes depending on state:

**Shape A: Normal response (scope active)**
```json
{
  "success": true,
  "session_id": "abc-123-def",
  "summary": "Found 12 fire watch notes for the past week...",
  "row_count": 12,
  "truncated": false,
  "error": "",
  "question": "show fire watch notes for last week",
  "scope": "inmate_data",
  "requires_scope": false,
  "options": null
}
```

**Shape B: No scope selected (prompting user)**
```json
{
  "success": true,
  "session_id": "abc-123-def",
  "summary": "Hi, I'm SARAH — your personalized virtual assistant. How can I help you today?",
  "requires_scope": true,
  "options": [
    {"id": "daily_activity", "label": "Daily Activity", "icon": "📅", "description": "Check missed and upcoming scheduled activities", "category": "Compliance"},
    {"id": "inmate_data", "label": "Inmate Data", "icon": "📊", "description": "Query notes, inmates, officers, and facilities", "category": "Data & Analytics"},
    {"id": "document_qa", "label": "Documents", "icon": "📄", "description": "Search manuals, guides, and policies", "category": "Information"}
  ]
}
```

**Shape C: Session expired**
```json
{
  "success": false,
  "session_id": "",
  "error": "session_expired"
}
```

**Frontend handling**:
1. Check `success` — HTTP 200 does NOT mean success
2. If `requires_scope == true` → render `options` as clickable cards
3. If `error == "session_expired"` → discard session_id, re-init
4. If `success == true` && scope present → render `summary` as bot message

**Status codes**: 200 (success or session_expired), 422 (validation), 503 (backend down), 500 (processing error)

---

### POST /chat/stream

Same request body as `/chat`. Returns Server-Sent Events (SSE).

**SSE Event Sequence (normal flow)**:
```
event: session
data: {"session_id":"abc-123-def"}

event: status                          ← zero or more status updates
data: {"message":"Generating SQL..."}

event: result                          ← final response
data: {"success":true,"summary":"Found 12 fire watch notes...","row_count":12,"scope":"inmate_data"}

event: done                            ← always last event
data:
```

**SSE on session_expired**:
```
event: error
data: {"error":"session_expired","summary":"Your previous session expired. Please start a new chat session."}

event: done
data:
```

**SSE on error**:
```
event: error
data: {"error":"backend_unavailable","detail":"Session store unreachable"}

event: done
data:
```

**Frontend SSE handling**:
```javascript
const eventSource = new EventSource(url);  // or fetch + ReadableStream for POST

// Listen for events
eventSource.addEventListener('session', (e) => { /* persist session_id */ });
eventSource.addEventListener('status', (e) => { /* show typing indicator */ });
eventSource.addEventListener('result', (e) => { /* render bot response */ });
eventSource.addEventListener('error', (e) => { /* handle error */ });
eventSource.addEventListener('done', (e) => { /* cleanup, re-enable input */ });
```

**Note**: Since this is a POST endpoint, you cannot use the browser's native `EventSource` (which only supports GET). Use `fetch` with a `ReadableStream` reader or a library like `@microsoft/fetch-event-source`.

---

### POST /scope/select

**Request**:
```json
{
  "session_id": "abc-123-def",
  "scope": "inmate_data"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| session_id | string | Yes | Must be valid/active |
| scope | string | Yes | One of: `inmate_data`, `document_qa`, `daily_activity` |
| customer_key | string | No | Optional override |
| user_id | string | No | Optional override |

**Response**:
```json
{
  "success": true,
  "session_id": "abc-123-def",
  "summary": "Welcome to Inmate Data. You can ask questions about inmates, notes, officers, and facilities.",
  "scope": "inmate_data",
  "previous_scope": null,
  "is_scope_change": true
}
```

**Special: `daily_activity` auto-executes**. The `summary` will contain both the welcome message AND the compliance check results (missed/upcoming activities). No follow-up question needed.

**Status codes**: 200, 404 (session_expired), 400 (invalid scope), 503, 500

---

### GET /scope/options

**Query params**: `?session_id=abc-123` (optional), `?customer_key=demo` (optional), `?user_id=R.B` (optional)

**Response**:
```json
{
  "options": [
    {"id": "daily_activity", "label": "Daily Activity", "icon": "📅", "description": "...", "category": "Compliance", "is_current": false, "is_visited": false},
    {"id": "inmate_data", "label": "Inmate Data", "icon": "📊", "description": "...", "category": "Data & Analytics", "is_current": true, "is_visited": true},
    {"id": "document_qa", "label": "Documents", "icon": "📄", "description": "...", "category": "Information", "is_current": false, "is_visited": false}
  ],
  "current_scope": "inmate_data"
}
```

**Frontend use**: Render each option as a card/button. Highlight `is_current`. Mark `is_visited` with a checkmark or badge.

---

### GET /health

**Response**: `{"status": "healthy", "version": "2.0.0", "environment": "prod"}`

Use for ALB health checks and monitoring dashboards.

---

### GET /session/{session_id}

**Response**:
```json
{
  "session_id": "abc-123-def",
  "customer_key": "demo",
  "user_id": "Richard.Bell",
  "turn_count": 12,
  "created_at": 1716300000.0,
  "last_active": 1716303600.0,
  "active_scope": "inmate_data",
  "scope_history": ["daily_activity", "inmate_data"]
}
```

**Status codes**: 200, 404 (session not found)

---

### GET /history

**Query params**: `?customer_key=demo&user_id=Richard.Bell&limit=50`

| Param | Required | Default |
|-------|----------|---------|
| customer_key | Yes | — |
| user_id | Yes | — |
| limit | No | 50 |

**Response**:
```json
{
  "turns": [
    {"role": "user", "content": "show fire watch notes", "scope": "inmate_data", "timestamp": 1716300000.0, "sql": "SELECT ...", "row_count": 5, "metadata": {}},
    {"role": "assistant", "content": "Found 5 fire watch notes...", "scope": "inmate_data", "timestamp": 1716300005.0, "sql": "", "row_count": 0, "metadata": {}}
  ],
  "total": 42
}
```

---

### POST /train

No request body. Reloads training data into Vanna ChromaDB.

**Response**: `{"success": true, "examples_trained": 25, "documentation_trained": 10}`

**Production note**: ChromaDB data is **baked into the Docker image** at build time. The vector store is pre-indexed and ready at container startup. You do **NOT** need to call `/train` after deployment. This endpoint exists for dev/manual re-indexing only.

**Status codes**: 200 (success), 500 (training failed — ChromaDB or data file error)

---

### GET /pipelines/health/{scope}

**Path param**: `scope` — one of `daily_activity`, `inmate_data`, `document_qa`

**Response**: `{"status": "healthy", "pipeline": "inmate_data", "details": {}}`

**Status codes**: 200, 404 (unknown scope)

---

## Session Lifecycle

```
Session created: POST /chat without session_id
Session TTL: 1 hour of inactivity (configurable via SESSION_TTL_SECONDS)
Session store: Valkey (ElastiCache) in production, Redis locally
Session expiry detection: endpoint-specific (see below)
```

| Endpoint | Expired Session Behavior |
|----------|-------------------------|
| POST /chat | HTTP 200, `success:false`, `error:"session_expired"` |
| POST /chat/stream | SSE `event:error` with `error:"session_expired"`, then `event:done` |
| POST /scope/select | HTTP 404, `{"detail":"session_expired"}` |
| GET /scope/options | HTTP 404, `{"detail":"session_expired"}` (only if session_id was provided) |

**Frontend strategy**: On any `session_expired` response, discard the stored session_id and retry the request without it. The server will create a new session.

---

## Error Response Patterns

**Validation error (422)** — Pydantic rejects the request body:
```json
{"detail": [{"loc": ["body", "question"], "msg": "field required", "type": "value_error.missing"}]}
```

**Not found (404)** — session expired or unknown scope:
```json
{"detail": "session_expired"}
```

**Bad request (400)** — invalid scope name:
```json
{"detail": "Unknown scope: invalid_scope_name"}
```

**Service unavailable (503)** — backend dependency down (Valkey, DynamoDB, etc.):
```json
{"detail": "Session store unreachable"}
```

**Internal error (500)** — unhandled processing error:
```json
{"detail": "Processing error: ..."}
```

**All 500-level errors are reported to Sentry** with full stack traces, request context, and breadcrumbs. Use the `X-Request-Id` header value to correlate frontend errors with Sentry events.

### Error Handling Coverage by Endpoint

| Endpoint | 200 | 400 | 404 | 422 | 500 | 503 |
|----------|-----|-----|-----|-----|-----|-----|
| POST /chat | Normal + session_expired | — | — | Pydantic | Pipeline error | Backend down |
| POST /chat/stream | SSE events | — | — | Pydantic | SSE error event | SSE error event |
| POST /scope/select | — | Invalid scope | Session expired | Pydantic | Scope error | Backend down |
| GET /scope/options | — | — | Session expired (if ID given) | — | Scope options error | Backend down |
| GET /health | Always | — | — | — | — | — |
| GET /session/{id} | — | — | Session not found | — | — | Backend down |
| GET /history | — | — | — | Missing params | History retrieval error | Backend down |
| POST /train | — | — | — | — | Training failure | — |
| GET /pipelines/health/{scope} | Healthy or unhealthy | — | Unknown scope | — | — | — |

### Frontend Retry Strategy

| Error | Action |
|-------|--------|
| `session_expired` | Discard session_id, retry request without it (new session auto-created) |
| 503 | Retry with exponential backoff (1s, 2s, 4s), max 3 retries |
| 500 | Do NOT retry — show user-friendly error message, report X-Request-Id |
| 422 | Fix request payload — this is a client-side bug |
| Network error / timeout | Retry once after 2s, then show connectivity error |

---

## Multi-Tenant Routing

Every request includes `customer_key` which maps to a specific Aurora MySQL database. The `facility_ids` array further scopes SQL queries within that tenant's data. Your auth system determines which `customer_key` and `facility_ids` to send.

Customer-specific configuration (DB connections, LLM settings, branding, feature flags) is loaded from the `ChatbotCustomerConfiguration` DynamoDB table at runtime. Adding a new customer requires only a DynamoDB row insert — no redeployment needed.

---

## Frontend Implementation Checklist

- [ ] Persist `session_id` from first `/chat` response (localStorage or state)
- [ ] Handle all three `/chat` response shapes (normal, requires_scope, session_expired)
- [ ] Render scope options as selectable cards when `requires_scope == true`
- [ ] Implement SSE reader for `/chat/stream` (POST-based, not native EventSource)
- [ ] Listen for `session`, `status`, `result`, `error`, `done` SSE events
- [ ] Show typing/processing indicator on `status` events
- [ ] Handle `session_expired` by clearing session_id and re-initializing
- [ ] Call `POST /scope/select` when user picks a scope card
- [ ] Display `daily_activity` auto-execute results from scope select response
- [ ] Include `customer_key`, `user_id`, `facility_ids` from your auth context in every POST
- [ ] Handle 503 errors (backend down) with retry or user-friendly message
- [ ] Set `Content-Type: application/json` on all POST requests
