"""
API Schemas — Pydantic models for request/response validation.

V2 Additions:
- ScopeSelectRequest: Select a scope
- ScopeOption: Scope option metadata
- ScopeOptionsResponse: Available scopes
- Enhanced ChatResponse with scope info
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(
        ..., min_length=1, max_length=1000, description="Natural language question"
    )
    session_id: str | None = Field(None, description="Resume existing session")
    customer_key: str = Field(..., description="Tenant identifier")
    user_id: str = Field(..., description="Officer username (firstname.lastname)")
    facility_ids: list[int] | None = Field(None, description="Facility scope filter")
    role: str = Field("officer", description="User role")


class ChatResponse(BaseModel):
    success: bool
    session_id: str
    summary: str = ""
    row_count: int = 0
    truncated: bool = False
    error: str = ""
    question: str = ""
    # V2 scope fields
    scope: str | None = None
    requires_scope: bool = False
    options: list[dict] | None = None


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "2.0.0"
    environment: str = ""


class SessionResponse(BaseModel):
    session_id: str
    customer_key: str
    user_id: str
    turn_count: int
    created_at: float
    last_active: float
    # V2 scope fields
    active_scope: str | None = None
    scope_history: list[str] = Field(default_factory=list)


class HistoryResponse(BaseModel):
    turns: list[dict] = Field(default_factory=list)
    total: int = 0


class TrainResponse(BaseModel):
    success: bool = True
    examples_trained: int = 0
    documentation_trained: int = 0


# ── V2 Scope Schemas ────────────────────────────────────────────────────


class ScopeSelectRequest(BaseModel):
    """Request to select/switch to a scope."""

    session_id: str = Field(..., description="Session to update")
    scope: str = Field(..., description="Scope ID to select (e.g., 'inmate_data', 'document_qa')")
    customer_key: str | None = Field(None, description="Tenant identifier (optional if session exists)")
    user_id: str | None = Field(None, description="User identifier (optional if session exists)")


class ScopeOption(BaseModel):
    """Metadata for a single scope option."""

    id: str
    label: str
    icon: str
    description: str
    category: str | None = None
    is_current: bool = False
    is_visited: bool = False


class ScopeOptionsResponse(BaseModel):
    """Available scope options."""

    options: list[ScopeOption] = Field(default_factory=list)
    current_scope: str | None = None


class ScopeSelectResponse(BaseModel):
    """Response after selecting a scope."""

    success: bool = True
    session_id: str
    summary: str = ""  # Welcome message
    scope: str
    previous_scope: str | None = None
    is_scope_change: bool = True


class PipelineHealthResponse(BaseModel):
    """Health status for a specific pipeline."""

    status: str
    pipeline: str
    details: dict[str, Any] = Field(default_factory=dict)
