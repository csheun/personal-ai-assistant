"""FastAPI entrypoint. Run with: `uvicorn app.main:app --reload` from `backend/`."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agent.service import AgentService, build_agent_service
from app.api.routes import chat, health
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None, agent: AgentService | None = None) -> FastAPI:
    """App factory. Tests pass a pre-built `agent` (with a fake LLM); production builds one from settings."""
    settings = settings or get_settings()
    logging.basicConfig(level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Built once at startup: fails fast on bad config instead of on the first user request.
        app.state.agent = agent or build_agent_service(settings)
        yield

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(chat.router, prefix="/api")
    return app


app = create_app()
