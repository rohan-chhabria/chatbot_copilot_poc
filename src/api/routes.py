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
from src.shared.config import ENVIRONMENT
from src.shared.exceptions import ScopeError
from src.shared.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

_session_store: SessionStore | None = None
_conversation_store: ConversationStore | None = None
_state_machine = None


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
    import src.pipelines.inmate_data  # noqa: F401
    import src.pipelines.document_qa  # noqa: F401


def _resolve_session(request: ChatRequest):
    """Resolve or create a session for the request."""
    from src.session.models import create_session

    store = _get_session_store()
    session = None

    if request.session_id:
        session = store.get(request.session_id)

    if session is None:
        session = create_session(
            customer_key=request.customer_key,
            user_id=request.user_id,
            facility_ids=request.facility_ids,
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

    _ensure_pipelines_registered()
    session = _resolve_session(request)
    logger.debug("Session resolved: %s (scope=%s)", session.session_id[:12], session.active_scope)

    state_machine = _get_state_machine()

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
            
    except Exception as e:
        logger.exception("Pipeline error for session=%s", session.session_id)
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")

    # Save session after processing
    _get_session_store().save(session)

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
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """SSE streaming endpoint using orchestrator layer."""
    logger.debug(
        "POST /chat/stream: question=%r, user=%s, session=%s",
        request.question[:80],
        request.user_id,
        request.session_id[:12] if request.session_id else "new",
    )

    _ensure_pipelines_registered()
    session = _resolve_session(request)
    logger.debug("Session resolved: %s (scope=%s)", session.session_id[:12], session.active_scope)

    state_machine = _get_state_machine()

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
        except Exception as e:
            logger.exception("Stream error for session=%s", session.session_id)
            yield {"event": "error", "data": str(e)}

        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


# ╔═══════════════════════════════════════════════════════════════════════════╗
# ║  SCOPE MANAGEMENT                                                         ║
# ╚═══════════════════════════════════════════════════════════════════════════╝


@router.post("/scope/select", response_model=ScopeSelectResponse)
async def select_scope(request: ScopeSelectRequest) -> ScopeSelectResponse:
    """Select a scope (user clicked option block)."""
    _ensure_pipelines_registered()

    store = _get_session_store()
    session = store.get(request.session_id)

    if not session:
        # Session not found - need customer_key and user_id to create one
        if not request.customer_key or not request.user_id:
            raise HTTPException(
                status_code=404,
                detail=f"Session {request.session_id} not found",
            )
        from src.session.models import create_session

        session = create_session(
            customer_key=request.customer_key,
            user_id=request.user_id,
        )

    state_machine = _get_state_machine()

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
    except Exception as e:
        logger.exception("Scope selection error")
        raise HTTPException(status_code=500, detail=str(e))

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
    _ensure_pipelines_registered()

    from src.session.models import create_session

    store = _get_session_store()
    session = None

    if session_id:
        session = store.get(session_id)

    if session is None:
        session = create_session(
            customer_key=customer_key or "demo",
            user_id=user_id or "anonymous",
        )

    state_machine = _get_state_machine()
    result = state_machine.get_scope_options(session)

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


@router.get("/session/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str) -> SessionResponse:
    store = _get_session_store()
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
    conv_store = _get_conversation_store()
    turns = conv_store.get_history(customer_key, user_id, limit=limit)
    return HistoryResponse(turns=turns, total=len(turns))


@router.post("/train", response_model=TrainResponse)
async def train() -> TrainResponse:
    from src.training.trainer import train_from_defaults_async

    result = await train_from_defaults_async()
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
