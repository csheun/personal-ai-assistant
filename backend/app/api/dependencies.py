from fastapi import Request

from app.agent.service import AgentService


def get_agent(request: Request) -> AgentService:
    """The agent is built once at startup (see app.main) and shared across requests."""
    return request.app.state.agent
