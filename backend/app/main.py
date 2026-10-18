"""FastAPI entrypoint. Run with: `uvicorn app.main:app --reload` from `backend/`."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import chat, conversations, health, workflows
from app.config import Settings, get_settings
from app.tools import build_default_registry
from app.workflows.errors import AssistantUnavailable, NotFound, WorkflowConflict
from app.workflows.planner import MockPlanner
from app.workflows.service import WorkflowService


def build_workflow_service(settings: Settings) -> WorkflowService:
    tools = build_default_registry(
        timeout_seconds=settings.tool_timeout_seconds, mock_latency_scale=settings.mock_latency_scale
    )
    return WorkflowService(tools, MockPlanner(tools))


def create_app(settings: Settings | None = None, service: WorkflowService | None = None) -> FastAPI:
    """App factory. Tests can pass their own settings or a pre-built service."""
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.workflows = service or build_workflow_service(settings)
        yield
        await app.state.workflows.shutdown()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Last-Event-ID"],
    )

    # Domain errors -> HTTP, in one place. Body shape matches FastAPI's own: {"detail": "..."}.
    for error, code in [
        (NotFound, status.HTTP_404_NOT_FOUND),
        (WorkflowConflict, status.HTTP_409_CONFLICT),
        (AssistantUnavailable, status.HTTP_503_SERVICE_UNAVAILABLE),
    ]:

        async def handler(_: Request, exc: Exception, code: int = code) -> JSONResponse:
            return JSONResponse(status_code=code, content={"detail": str(exc)})

        app.add_exception_handler(error, handler)

    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api")
    app.include_router(conversations.router, prefix="/api")
    app.include_router(workflows.router, prefix="/api")
    return app


app = create_app()
