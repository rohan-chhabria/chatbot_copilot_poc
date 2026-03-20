"""
API Middleware — Request lifecycle hooks for auth, tenant extraction, and logging.
"""

from __future__ import annotations

import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.shared.logger import get_logger

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = str(uuid.uuid4())[:8]
        request.state.request_id = request_id
        start = time.time()

        logger.info(
            "[%s] %s %s",
            request_id,
            request.method,
            request.url.path,
        )

        response = await call_next(request)

        elapsed_ms = (time.time() - start) * 1000
        logger.info(
            "[%s] %d in %.0fms",
            request_id,
            response.status_code,
            elapsed_ms,
        )

        response.headers["X-Request-Id"] = request_id
        return response


class CORSHeaders(BaseHTTPMiddleware):

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.method == "OPTIONS":
            response = Response(status_code=200)
        else:
            response = await call_next(request)

        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Customer-Key"
        return response
