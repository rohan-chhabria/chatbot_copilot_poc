"""
API Handler — Production entry point for ECS Fargate (uvicorn).

This file contains ONLY production code. No static files, no local
endpoints, no moto/mock wiring. For local development, use:
    python -m local.server

V2: Adds orchestrator-based multi-pipeline support with scope management.
"""

from __future__ import annotations

from fastapi import FastAPI

from src.api.middleware import CORSHeaders, RequestLoggingMiddleware
from src.api.routes import router
from src.shared.config import ENVIRONMENT, SENTRY_DSN

if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=ENVIRONMENT,
            integrations=[FastApiIntegration(transaction_style="endpoint")],
            traces_sample_rate=0.1,
            profiles_sample_rate=0.0,
            send_default_pii=False,
        )
    except ImportError:
        pass

app = FastAPI(
    title="InmateCopilot",
    description="Intelligent chatbot for correctional facility officers. V2 supports multiple pipelines (Inmate Data, Documents) with scope management.",
    version="2.0.0",
    docs_url="/docs" if ENVIRONMENT != "prod" else None,
    redoc_url=None,
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CORSHeaders)
app.include_router(router)
