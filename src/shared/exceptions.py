"""
Custom exceptions for InmateCopilot.

Hierarchical exception classes for clean error handling
across different layers of the application.
"""


class InmateCopilotError(Exception):
    """Base exception for all InmateCopilot errors."""

    pass


class PipelineError(InmateCopilotError):
    """Error within a pipeline."""

    def __init__(self, message: str, pipeline: str, recoverable: bool = True):
        super().__init__(message)
        self.pipeline = pipeline
        self.recoverable = recoverable


class ValidationError(InmateCopilotError):
    """Input validation failed."""

    pass


class ScopeError(InmateCopilotError):
    """Scope-related error (invalid scope, no active scope, etc.)."""

    pass


class SessionError(InmateCopilotError):
    """Session not found or corrupted."""

    pass


class TenantError(InmateCopilotError):
    """Tenant not found or access denied."""

    pass


class DocumentError(PipelineError):
    """Document pipeline specific errors."""

    def __init__(self, message: str, doc_id: str | None = None):
        super().__init__(message, pipeline="document_qa")
        self.doc_id = doc_id


class SQLGenerationError(PipelineError):
    """SQL generation or execution failed."""

    def __init__(self, message: str, sql: str | None = None):
        super().__init__(message, pipeline="inmate_data")
        self.sql = sql


class RetrievalError(PipelineError):
    """Document retrieval failed."""

    def __init__(self, message: str, query: str | None = None):
        super().__init__(message, pipeline="document_qa")
        self.query = query
