"""
Local Development Server — Entry point for local E2E testing.

Boots moto DynamoDB + in-memory sessions, mounts the dashboard UI,
adds local-only endpoints (/users, /session/init), and starts uvicorn.

Usage:
    python -m local.server
    # Dashboard: http://localhost:8000
    # API docs:  http://localhost:8000/docs
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from local.bootstrap import LocalStores, bootstrap_local, load_local_users, shutdown_local
# Import daily_activity FIRST to ensure it appears first in scope menu
import src.pipelines.daily_activity  # noqa: F401
from src.pipelines.inmate_data.vanna_agent import AgentPipeline
from src.api.middleware import CORSHeaders, RequestLoggingMiddleware
from src.api.routes import router as production_router
from src.session.session_manager import create_session
from src.shared.config import BOT_GREETING, BOT_NAME
from src.shared.logger import get_logger

logger = get_logger(__name__)

_stores: LocalStores | None = None

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(application: FastAPI):
    global _stores
    _stores = bootstrap_local()
    _inject_stores_into_routes(_stores)
    logger.info("Local server ready — http://localhost:8000")
    yield
    shutdown_local()

app = FastAPI(
    title="InmateCopilot — Local Dev",
    description="Local development server with moto DynamoDB + in-memory sessions",
    version="1.0.0-local",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CORSHeaders)


def _inject_stores_into_routes(stores: LocalStores) -> None:
    """Override the lazy singletons in production routes with local stores."""
    from src.api import routes
    routes._session_store = stores.session_store
    routes._conversation_store = stores.conversation_store
    routes._pipeline = AgentPipeline(
        session_store=stores.session_store,
        conversation_store=stores.conversation_store,
    )


# ── Mount production routes ───────────────────────────────────────────────

app.include_router(production_router)


# ── Local-only endpoints ──────────────────────────────────────────────────

class SessionInitRequest(BaseModel):
    user_id: str = Field(..., description="user_id from local/users.json")


class SessionInitResponse(BaseModel):
    session_id: str
    bot_name: str
    greeting: str
    user: dict = Field(default_factory=dict)


@app.post("/session/init", response_model=SessionInitResponse)
async def init_session(request: SessionInitRequest):
    """Create a new session from local/users.json and return bot greeting."""
    users_data = load_local_users()
    user_cfg = next(
        (u for u in users_data.get("users", []) if u["user_id"] == request.user_id),
        None,
    )
    if not user_cfg:
        raise HTTPException(status_code=404, detail=f"User '{request.user_id}' not in local/users.json")

    assert _stores is not None
    session = create_session(
        customer_key=user_cfg["customer_key"],
        user_id=user_cfg["user_id"],
        facility_ids=user_cfg.get("facility_ids", []),
        role=user_cfg.get("role", "officer"),
        display_name=user_cfg.get("display_name", user_cfg["user_id"]),
    )
    _stores.session_store.save(session)

    display_name = user_cfg.get("display_name", user_cfg["user_id"])
    role = user_cfg.get("role", "officer")

    prior_topics = []
    assert _stores is not None
    try:
        history = _stores.conversation_store.get_history(
            user_cfg["customer_key"], user_cfg["user_id"], limit=10,
        )
        for item in history:
            if item.get("role") == "user" and item.get("content"):
                prior_topics.append(item["content"])
    except Exception:
        pass

    if prior_topics:
        topics_str = ", ".join(f'"{t}"' for t in prior_topics[:3])
        greeting = (
            f"Welcome back, {display_name}! "
            f"Last time you asked about {topics_str}. "
            f"What would you like to look into today?"
        )
    else:
        greeting = (
            f"Hello {role.title()} {display_name}, I'm Smart Access to Records, Analysis, and Help - {BOT_NAME} — your Inmate Intelligence assistant. "
            f"I can help you search notes, track inmates, check compliance, and more. "
            f"What can I help you with?"
        )

    logger.info("Local session init: %s user=%s", session.session_id, request.user_id)

    return SessionInitResponse(
        session_id=session.session_id,
        bot_name=BOT_NAME,
        greeting=BOT_GREETING if BOT_GREETING else greeting,
        user={
            "user_id": user_cfg["user_id"],
            "display_name": display_name,
            "role": role,
            "avatar": user_cfg.get("avatar", "??"),
            "facility_ids": user_cfg.get("facility_ids", []),
        },
    )


@app.get("/users")
async def list_users():
    """List available local dev users."""
    data = load_local_users()
    return {
        "users": [
            {
                "user_id": u["user_id"],
                "display_name": u.get("display_name", u["user_id"]),
                "role": u.get("role", "officer"),
                "avatar": u.get("avatar", "??"),
            }
            for u in data.get("users", [])
        ],
        "bot_name": BOT_NAME,
    }


# ── Static files (dashboard UI) ──────────────────────────────────────────

_static_dir = Path(__file__).resolve().parents[1] / "static"
if _static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")


# ── Direct run ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "local.server:app",
        host="0.0.0.0",
        port=8065,
        reload=False,
        log_level="info",
    )
