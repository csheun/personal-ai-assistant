"""FastAPI entrypoint. Run with: `uvicorn app.main:app --reload` from `backend/`."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import chat, conversations, health, workflows
from app.config import Settings, get_settings
from app.llm.client import LLMClient, LLMUnavailable
from app.llm.provider import build_llm_client
from app.tools import build_default_registry
from app.tools.live import build_live_registry
from app.workflows.errors import AssistantUnavailable, NotFound, WorkflowConflict
from app.workflows.llm_planner import LLMPlanner, PlanningFailed
from app.workflows.planner import MockPlanner
from app.workflows.service import WorkflowService
from app.workflows.validation import PlanLimits

logger = logging.getLogger(__name__)


def build_workflow_service(
    settings: Settings, *, http: httpx.AsyncClient, llm: LLMClient | None = None
) -> WorkflowService:
    """Wires planner + tools for the configured mode. The runner, routes and SSE are the same in both."""
    if settings.mock_mode:
        tools = build_default_registry(
            timeout_seconds=settings.tool_timeout_seconds, mock_latency_scale=settings.mock_latency_scale
        )
        return WorkflowService(tools, MockPlanner(tools), mode="mock")

    llm = llm or build_llm_client(settings)  # raises LLMConfigError if the provider key is missing
    tools = build_live_registry(settings, http, llm)
    planner = LLMPlanner(
        llm,
        tools,
        max_attempts=settings.planner_max_attempts,
        limits=PlanLimits(max_tasks=settings.planner_max_tasks, max_depth=settings.planner_max_depth),
    )
    logger.info("Live mode: %s/%s, tools: %s", settings.llm_provider, settings.llm_model, ", ".join(tools.names))
    return WorkflowService(tools, planner, mode="live", llm_model=f"{settings.llm_provider}:{settings.llm_model}")


def create_app(
    settings: Settings | None = None,
    service: WorkflowService | None = None,
    llm: LLMClient | None = None,
    http_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """App factory. Tests can pass their own settings, a fake LLM, a fake HTTP transport or a service."""
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # One pooled HTTP client for every provider, closed on shutdown.
        async with httpx.AsyncClient(
            headers={"User-Agent": "personal-ai-assistant/0.1"}, transport=http_transport
        ) as http:
            app.state.settings = settings
            app.state.workflows = service or build_workflow_service(settings, http=http, llm=llm)
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
        (LLMUnavailable, status.HTTP_503_SERVICE_UNAVAILABLE),
        (PlanningFailed, status.HTTP_502_BAD_GATEWAY),
    ]:

        async def handler(_: Request, exc: Exception, code: int = code) -> JSONResponse:
            if isinstance(exc, PlanningFailed):
                logger.warning("Planning failed after validation: %s", exc.errors)
            return JSONResponse(status_code=code, content={"detail": str(exc)})

        app.add_exception_handler(error, handler)

    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api")
    app.include_router(conversations.router, prefix="/api")
    app.include_router(workflows.router, prefix="/api")
    return app


app = create_app()
