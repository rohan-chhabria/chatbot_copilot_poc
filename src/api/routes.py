"""
API Routes — V2 endpoint definitions for the InmateCopilot chatbot.

Endpoints:
  POST /chat          — Chat endpoint (scope-aware, orchestrator-based)
  POST /chat/stream   — SSE streaming endpoint
  POST /scope/select  — Select/switch scope
  GET  /scope/options — Get available scopes
  GET  /health        — Health check
  GET  /session/{id}  — Session details
  GET  /history       — Conversation history for a user
  POST /train         — Trigger training data load
  GET  /pipelines/health/{scope} — Pipeline health check

Local-only endpoints (/users, /session/init) live in local/server.py.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    HistoryResponse,
    PipelineHealthResponse,
    ScopeOptionsResponse,
    ScopeSelectRequest,
    ScopeSelectResponse,
    SessionResponse,
    TrainResponse,
)
from src.memory.conversation_store import ConversationStore, create_conversation_store
from src.session.session_manager import SessionStore, create_session_store
from src.shared.config import ENVIRONMENT, SESSION_BACKEND
from src.shared.exceptions import ScopeError
from src.shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

_session_store: SessionStore | None = None
_conversation_store: ConversationStore | None = None
_state_machine = None


class SessionExpiredError(Exception):
    """Raised when a provided session_id cannot be resumed."""


def _get_session_store() -> SessionStore:
    global _session_store
    if _session_store is None:
        _session_store = create_session_store()
    return _session_store


def _get_conversation_store() -> ConversationStore:
    global _conversation_store
    if _conversation_store is None:
        _conversation_store = create_conversation_store()
    return _conversation_store


def _get_state_machine():
    """Get orchestrator state machine."""
    global _state_machine
    if _state_machine is None:
        from src.orchestrator.state_machine import ScopeStateMachine

        _state_machine = ScopeStateMachine(_get_conversation_store())
    return _state_machine


def _ensure_pipelines_registered():
    """Ensure pipelines are imported and registered."""
    import src.pipelines.daily_activity  # noqa: F401 - First for menu ordering
    import src.pipelines.document_qa  # noqa: F401
    import src.pipelines.inmate_data  # noqa: F401


def _resolve_session(request: ChatRequest):
    """Resolve or create a session for the request."""
    from src.session.models import create_session
    from src.shared.config import TENANT_DB_MAP

    store = _get_session_store()
    session = None

    if request.session_id:
        session = store.get(request.session_id)
        if session is None:
            raise SessionExpiredError(request.session_id)

    if session is None:
        facility_ids = request.facility_ids
        if not facility_ids:
            tenant_config = TENANT_DB_MAP.get(request.customer_key.strip().lower(), {})
            facility_ids = tenant_config.get("default_facility_ids")
        session = create_session(
            customer_key=request.customer_key,
            user_id=request.user_id,
            facility_ids=facility_ids,
            role=request.role,
        )
        logger.info("New session: %s user=%s", session.session_id, request.user_id)

    return session


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  MAIN ENDPOINTS                                                           ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Main chat endpoint using orchestrator layer."""
    logger.debug(
        "POST /chat: question=%r, user=%s, session=%s",
        request.question[:80],
        request.user_id,
        request.session_id[:12] if request.session_id else "new",
    )

    try:
        _ensure_pipelines_registered()
        session = _resolve_session(request)
    except SessionExpiredError:
        return ChatResponse(
            success=False,
            session_id=request.session_id or "",
            summary="Your previous session expired. Please start a new chat session.",
            error="session_expired",
            question=request.question,
            row_count=0,
        )
    except RuntimeError as e:
        logger.error("Session backend unavailable: %s", str(e))
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    logger.debug("Session resolved: %s (scope=%s)", session.session_id[:12], session.active_scope)

    try:
        state_machine = _get_state_machine()
    except RuntimeError as e:
        logger.error("State machine unavailable: %s", str(e))
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        logger.debug("Calling state_machine.handle_message...")
        result = await state_machine.handle_message(
            message=request.question,
            session=session,
        )
        logger.debug(
            "handle_message returned: row_count=%s, has_error=%s",
            result.get("row_count"),
            "error" in result,
        )

        # Handle auto-execute for pipelines that support it (e.g., Daily Activity)
        # This handles the case where user selects scope by typing its name
        if result.get("auto_execute"):
            auto_result = await state_machine.handle_message("", session)
            combined_summary = result.get("summary", "") + "\n\n" + auto_result.get("summary", "")
            result["summary"] = combined_summary
            result["row_count"] = auto_result.get("row_count", 0)

    except Exception:
        logger.exception("Pipeline error for session=%s", session.session_id)
        raise HTTPException(status_code=500, detail="An error occurred processing your request")

    # Save session after processing
    _get_session_store().save(session)

    # Build scope-specific data dict (exclude common fields)
    common_keys = {
        "summary", "row_count", "truncated", "error", "scope",
        "requires_scope", "options", "auto_execute"
    }
    scope_data = {k: v for k, v in result.items() if k not in common_keys}

    return ChatResponse(
        success="error" not in result,
        session_id=session.session_id,
        summary=result.get("summary", ""),
        row_count=result.get("row_count", 0),
        truncated=result.get("truncated", False),
        error=result.get("error", ""),
        question=request.question,
        scope=result.get("scope"),
        requires_scope=result.get("requires_scope", False),
        options=result.get("options"),
        data=scope_data if scope_data else None,
    )


def _make_error_stream(error_type: str, message: str):
    """Helper to create SSE error stream (M6 fix - deduplicate)."""
    async def generator():
        yield {"event": "error", "data": json.dumps({"error": error_type, "message": message})}
        yield {"event": "done", "data": ""}
    return EventSourceResponse(generator())


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE streaming endpoint using orchestrator layer."""
    logger.debug(
        "POST /chat/stream: question=%r, user=%s, session=%s",
        request.question[:80],
        request.user_id,
        request.session_id[:12] if request.session_id else "new",
    )

    try:
        _ensure_pipelines_registered()
        session = _resolve_session(request)
    except SessionExpiredError:
        return _make_error_stream(
            "session_expired",
            "Your previous session expired. Please start a new chat session.",
        )
    except RuntimeError as e:
        logger.error("Backend unavailable for stream: %s", str(e))
        return _make_error_stream("backend_unavailable", "Service temporarily unavailable")

    logger.debug("Session resolved: %s (scope=%s)", session.session_id[:12], session.active_scope)

    try:
        state_machine = _get_state_machine()
    except RuntimeError as e:
        logger.error("State machine unavailable for stream: %s", str(e))
        return _make_error_stream("backend_unavailable", "Service temporarily unavailable")

    async def event_generator():
        yield {
            "event": "session",
            "data": json.dumps({"session_id": session.session_id}),
        }

        try:
            # If no active scope, handle with state machine (non-streaming)
            if session.active_scope is None:
                logger.debug("No active scope, using non-streaming handler")
                result = await state_machine.handle_message(
                    message=request.question,
                    session=session,
                )

                # Handle auto-execute for pipelines that support it (e.g., Daily Activity)
                if result.get("auto_execute"):
                    auto_result = await state_machine.handle_message("", session)
                    combined_summary = result.get("summary", "") + "\n\n" + auto_result.get("summary", "")
                    result["summary"] = combined_summary
                    result["row_count"] = auto_result.get("row_count", 0)

                _get_session_store().save(session)
                yield {"event": "result", "data": json.dumps(result)}
            else:
                # Stream from active pipeline
                logger.debug("Streaming from scope: %s", session.active_scope)
                event_count = 0
                async for event in state_machine.dispatch_stream(
                    message=request.question,
                    session=session,
                ):
                    event_count += 1
                    evt_name = event.get("event", "message")
                    payload = event.get("data", "")
                    if isinstance(payload, dict):
                        payload = json.dumps(payload)
                    yield {"event": evt_name, "data": payload}
                logger.debug("Stream complete: %d events", event_count)
                _get_session_store().save(session)
        except Exception:
            logger.exception("Stream error for session=%s", session.session_id)
            # M5 fix: Save session state on error
            try:
                _get_session_store().save(session)
            except Exception:
                logger.warning("Failed to save session on stream error")
            yield {"event": "error", "data": json.dumps({"error": "processing_error", "message": "An error occurred"})}

        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  SCOPE MANAGEMENT                                                         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


@router.post("/scope/select", response_model=ScopeSelectResponse)
async def select_scope(request: ScopeSelectRequest) -> ScopeSelectResponse:
    """Select a scope (user clicked option block)."""
    try:
        _ensure_pipelines_registered()
        store = _get_session_store()
    except RuntimeError as e:
        logger.error("Backend unavailable for scope select: %s", str(e))
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    session = store.get(request.session_id)

    if not session:
        raise HTTPException(
            status_code=404,
            detail="session_expired",
        )

    try:
        state_machine = _get_state_machine()
    except RuntimeError as e:
        logger.error("State machine unavailable for scope select: %s", str(e))
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        result = state_machine.select_scope(request.scope, session)

        # Handle auto-execute for pipelines that support it (e.g., Daily Activity)
        if result.get("auto_execute"):
            # Trigger the pipeline through the normal async path with empty message
            auto_result = await state_machine.handle_message("", session)

            # Combine welcome message with auto-execute result
            combined_summary = result.get("summary", "") + "\n\n" + auto_result.get("summary", "")
            result["summary"] = combined_summary
            result["row_count"] = auto_result.get("row_count", 0)

    except ScopeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Scope selection error")
        raise HTTPException(status_code=500, detail="An error occurred during scope selection")

    store.save(session)

    return ScopeSelectResponse(
        success=True,
        session_id=session.session_id,
        summary=result.get("summary", ""),
        scope=result.get("scope", request.scope),
        previous_scope=result.get("previous_scope"),
        is_scope_change=True,
    )


@router.get("/scope/options", response_model=ScopeOptionsResponse)
async def get_scope_options(
    session_id: str | None = Query(None),
    customer_key: str | None = Query(None),
    user_id: str | None = Query(None),
) -> ScopeOptionsResponse:
    """Get available scope options."""
    try:
        _ensure_pipelines_registered()
    except RuntimeError as e:
        logger.error("Pipeline registration failed: %s", str(e))
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    from src.session.models import create_session

    try:
        store = _get_session_store()
    except RuntimeError as e:
        logger.error("Session store unavailable: %s", str(e))
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    session = None

    if session_id:
        session = store.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session_expired")

    if session is None:
        session = create_session(
            customer_key=customer_key or "demo",
            user_id=user_id or "anonymous",
        )

    try:
        state_machine = _get_state_machine()
    except RuntimeError as e:
        logger.error("State machine unavailable: %s", str(e))
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        result = state_machine.get_scope_options(session)
    except Exception:
        logger.exception("Failed to get scope options")
        raise HTTPException(status_code=500, detail="Failed to load scope options")

    return ScopeOptionsResponse(
        options=[
            {
                "id": opt["id"],
                "label": opt["label"],
                "icon": opt["icon"],
                "description": opt["description"],
                "category": opt.get("category"),
                "is_current": opt.get("is_current", False),
                "is_visited": opt.get("is_visited", False),
            }
            for opt in result.get("options", [])
        ],
        current_scope=result.get("current_scope"),
    )


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  UTILITY ENDPOINTS                                                        ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(environment=ENVIRONMENT)


@router.get("/health/deep")
async def health_deep() -> dict:
    """Deep health check for all dependencies (A1 fix).

    Checks:
      - Redis/Valkey (session store)
      - Conversation store (SQLite/DynamoDB)
      - Database connectivity (Aurora MySQL)
    """
    checks = {}
    overall_healthy = True

    # Check session store (Redis/Valkey)
    try:
        store = _get_session_store()
        if hasattr(store, "_client"):
            store._client.ping()
            checks["session_store"] = {"status": "healthy", "backend": SESSION_BACKEND}
        elif hasattr(store, "_store") and hasattr(store._store, "_client"):
            store._store._client.ping()
            checks["session_store"] = {"status": "healthy", "backend": "valkey"}
        else:
            checks["session_store"] = {"status": "healthy", "backend": "unknown"}
    except Exception as e:
        checks["session_store"] = {"status": "unhealthy", "error": str(e)}
        overall_healthy = False

    # Check conversation store
    try:
        conv_store = _get_conversation_store()
        if hasattr(conv_store, "health_check"):
            conv_store.health_check()
        checks["conversation_store"] = {"status": "healthy"}
    except Exception as e:
        checks["conversation_store"] = {"status": "unhealthy", "error": str(e)}
        overall_healthy = False

    # Check database connectivity for default tenant
    try:
        from src.tenant.db_registry import get_connection
        from src.tenant.tenant_router import resolve_tenant

        demo_tenant = resolve_tenant("demo")
        with get_connection(demo_tenant) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
        checks["database"] = {"status": "healthy", "tenant": "demo"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}
        overall_healthy = False

    return {
        "status": "healthy" if overall_healthy else "degraded",
        "environment": ENVIRONMENT,
        "checks": checks,
    }


@router.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str) -> SessionResponse:
    try:
        store = _get_session_store()
    except RuntimeError as e:
        logger.error("Session store unavailable: %s", str(e))
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    session = store.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired.")

    return SessionResponse(
        session_id=session.session_id,
        customer_key=session.customer_key,
        user_id=session.user_id,
        turn_count=len(session.turns),
        created_at=session.created_at,
        last_active=session.last_active,
        active_scope=session.active_scope,
        scope_history=session.scope_history,
    )


@router.get("/history", response_model=HistoryResponse)
async def get_history(
    customer_key: str, user_id: str, limit: int = 50
) -> HistoryResponse:
    try:
        conv_store = _get_conversation_store()
    except RuntimeError as e:
        logger.error("Conversation store unavailable: %s", str(e))
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        turns = conv_store.get_history(customer_key, user_id, limit=limit)
    except Exception:
        logger.exception("Failed to get history for user=%s", user_id)
        raise HTTPException(status_code=500, detail="Failed to retrieve history")

    return HistoryResponse(turns=turns, total=len(turns))


@router.post("/train", response_model=TrainResponse)
async def train() -> TrainResponse:
    from src.training.trainer import train_from_defaults_async

    try:
        result = await train_from_defaults_async()
    except Exception:
        logger.exception("Training failed")
        raise HTTPException(status_code=500, detail="Training failed")

    return TrainResponse(
        examples_trained=result.get("examples", 0),
        documentation_trained=result.get("documentation", 0),
    )


@router.get("/pipelines/health/{scope}", response_model=PipelineHealthResponse)
async def pipeline_health(scope: str) -> PipelineHealthResponse:
    """Health check for a specific pipeline."""
    _ensure_pipelines_registered()

    from src.orchestrator.scope_registry import ScopeRegistry

    if not ScopeRegistry.is_valid_scope(scope):
        raise HTTPException(status_code=404, detail=f"Unknown scope: {scope}")

    try:
        pipeline = ScopeRegistry.get(scope)
        health_result = await pipeline.health()
    except Exception as e:
        logger.exception("Pipeline health check failed for %s", scope)
        return PipelineHealthResponse(
            status="unhealthy",
            pipeline=scope,
            details={"error": str(e)},
        )

    return PipelineHealthResponse(
        status=health_result.get("status", "unknown"),
        pipeline=scope,
        details=health_result,
    )
