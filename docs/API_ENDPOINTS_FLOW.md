# API Endpoints Flow Guide (Backend Engineers)

This guide describes **which endpoint to call first**, how endpoints connect, and the processing contract for each endpoint.

---

## 0. Runtime Profiles (Why Swagger shows extra endpoints)

Swagger endpoint surface depends on which app you run:

| Runtime | App entrypoint | Endpoint surface |
|---|---|---|
| Production/API app | `src.api.handler:app` | Core endpoints only (`/chat`, `/chat/stream`, `/scope/*`, `/health`, `/session/{id}`, `/history`, `/train`, `/pipelines/health/{scope}`) |
| Local dev app | `python -m local.server` | Core endpoints **plus local-only** endpoints: `/session/init`, `/users` |

So if you are looking at local Swagger (`localhost:<port>/docs`), seeing `/session/init` and `/users` is expected.

---

## 1. Start Here (Call Order)

Use this order for normal chatbot consumption:

1. **`GET /scope/options`** (initial UI bootstrap; no session required)
2. **`POST /chat`** (first user message; server creates session when `session_id` absent)
3. **Persist returned `session_id`**
4. **`POST /scope/select`** when user chooses/switches a scope
5. Continue with **`POST /chat`** (or **`POST /chat/stream`** for SSE)
6. Optional support/debug endpoints: **`GET /session/{session_id}`**, **`GET /history`**

If client already has valid `session_id`, steps 1-2 can be skipped and chat can resume directly.

### Local UI bootstrap order (when using local.server)

1. **`GET /users`** to list available local mock users.
2. **`POST /session/init`** with selected `user_id` to create a seeded session + greeting.
3. Persist returned `session_id`.
4. Continue with normal flow (`/scope/options` -> `/scope/select` -> `/chat` or `/chat/stream`).

---

## 2. How Endpoints Connect (End-to-End)

```text
Client load
  -> GET /scope/options
  -> render available scopes

First user message
  -> POST /chat (without session_id)
  -> session created
  -> response returns session_id + scope guidance/result

Scope selected
  -> POST /scope/select (session_id + scope)
  -> active_scope set
  -> if scope supports auto_execute (daily_activity), response includes combined welcome + computed status

Conversation loop
  -> POST /chat OR POST /chat/stream (same session_id)
  -> orchestrator routes by active_scope / cross-scope handlers
  -> turn persisted to STM + LTM

Diagnostics/support (optional)
  -> GET /session/{session_id}
  -> GET /history?customer_key=...&user_id=...
```

---

## 3. Session & Expiry Contract (Critical)

For chat endpoints, request body fields are:
- `question` (required)
- `customer_key` (required)
- `user_id` (required)
- `session_id` (optional for new session)
- `facility_ids`, `role` (optional)

Behavior:
1. `session_id` missing -> create new session
2. `session_id` valid -> resume
3. `session_id` stale/missing in store -> **endpoint-specific error contract**

| Endpoint | Stale session behavior |
|---|---|
| `POST /chat` | HTTP `200`, payload includes `success=false`, `error="session_expired"` |
| `POST /chat/stream` | SSE `event:error` with `error="session_expired"`, then `event:done` |
| `POST /scope/select` | HTTP `404` with `{"detail":"session_expired"}` |
| `GET /scope/options?session_id=...` | HTTP `404` with `{"detail":"session_expired"}` |

---

## 4. Endpoint-by-Endpoint Processing

## `GET /scope/options`
**Purpose:** Fetch scope metadata for selection UI.  
**Input:** optional `session_id`, optional `customer_key`, optional `user_id`.  
**Processing:**
1. If `session_id` provided, load session.
2. If missing session -> `session_expired` (404).
3. If no session_id, create anonymous temporary session context.
4. Return options with `is_current` and `is_visited` flags.

---

## `POST /chat`
**Purpose:** Main non-stream conversation endpoint.  
**Processing flow:**
1. Register pipelines.
2. Resolve/create session.
3. Pass message to `ScopeStateMachine.handle_message`.
4. If no active scope, return scope-selection guidance.
5. If active scope, dispatch to pipeline or cross-scope handler.
6. Persist session in STM.
7. Return `ChatResponse`.

---

## `POST /chat/stream`
**Purpose:** SSE response path with same orchestrator logic as `/chat`.  
**SSE event order:**
1. `session`
2. zero or more `status`
3. `result` (final payload)
4. optional `error`
5. `done`

Uses same session resolution and scope routing contracts; only transport differs (SSE vs JSON).

---

## `POST /scope/select`
**Purpose:** Set or switch active scope for an existing session.  
**Input:** `session_id`, `scope` (required).  
**Processing:**
1. Load existing session.
2. Validate scope in registry.
3. Switch active scope and preserve prior scope context.
4. Return scope welcome summary.
5. If selected scope has `supports_auto_execute=True` (Daily Activity), auto-run and return combined output.

---

## `GET /session/{session_id}`
**Purpose:** Read session metadata for debugging/support.  
**Returns:** `active_scope`, `scope_history`, turn count, timestamps.

---

## `GET /history`
**Purpose:** Retrieve user-level historical turns from LTM.  
**Input:** `customer_key`, `user_id`, optional `limit`.  
**Returns:** `turns`, `total`.

---

## `GET /pipelines/health/{scope}`
**Purpose:** Pipeline-specific health status.  
**Valid scopes currently:** `daily_activity`, `inmate_data`, `document_qa`.  
**Unknown scope:** 404.

---

## `GET /health`
**Purpose:** Service health (`status`, `version`, `environment`).

---

## `POST /train`
**Purpose:** Reload default SQL/doc training data into training stores.

---

## `GET /users` (local.server only)
**Purpose:** Return local development user profiles from `local/users.json`.  
**Used by:** local dashboard login bootstrap.

---

## `POST /session/init` (local.server only)
**Purpose:** Create local session from selected local user profile and return greeting context.  
**Input:** `user_id` from local users list.  
**Returns:** `session_id`, `bot_name`, `greeting`, user metadata.

---

## 5. Integration Examples

### First chat turn (new session)
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "question":"hello",
    "customer_key":"demo",
    "user_id":"Richard.Bell"
  }'
```

### Select scope
```bash
curl -X POST http://localhost:8000/scope/select \
  -H "Content-Type: application/json" \
  -d '{
    "session_id":"<session-id>",
    "scope":"inmate_data"
  }'
```

### Stream mode
```bash
curl -N -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "question":"show fire watch notes",
    "session_id":"<session-id>",
    "customer_key":"demo",
    "user_id":"Richard.Bell"
  }'
```
