"""AgentService: the single entry point the API layer uses to talk to the agent.

It hides LangGraph/LangChain details from FastAPI. Routes pass in a string and get
back a plain result object or a domain error, never a provider-specific exception.
"""

import logging
from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent.graph import build_agent_graph
from app.config import Settings
from app.llm.provider import build_chat_model
from app.tools import ToolRegistry, ToolResult, build_default_registry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a helpful personal assistant.
Use the provided tools when they help answer the user's question; otherwise answer directly.
Some tools return MOCKED data (their results include "mocked": true). When you use mocked data,
tell the user clearly that the information is simulated and not real.
If a tool returns an error, either retry with corrected arguments or explain the problem."""


class AgentError(RuntimeError):
    """Base class for errors surfaced to the API layer."""


class LLMUpstreamError(AgentError):
    """The LLM provider call failed (network, auth, rate limit, bad response...)."""


class IterationLimitError(AgentError):
    """The model kept requesting tools beyond the configured budget."""


@dataclass(frozen=True)
class AgentRun:
    answer: str
    tool_results: list[ToolResult]
    iterations: int


class AgentService:
    def __init__(self, llm: BaseChatModel, registry: ToolRegistry, max_iterations: int, model_name: str) -> None:
        self.model_name = model_name
        self._max_iterations = max_iterations
        self._graph = build_agent_graph(llm, registry, max_iterations)

    async def run(self, message: str) -> AgentRun:
        initial = {
            "messages": [SystemMessage(SYSTEM_PROMPT), HumanMessage(message)],
            "tool_results": [],
            "iterations": 0,
            "hit_iteration_limit": False,
        }
        try:
            state = await self._graph.ainvoke(initial)
        except Exception as exc:
            # Tool failures are already contained by the registry, so anything here is the LLM call.
            logger.exception("Agent run failed")
            raise LLMUpstreamError("The language model request failed.") from exc

        if state["hit_iteration_limit"]:
            raise IterationLimitError(f"Agent exceeded {self._max_iterations} LLM iterations without answering.")

        final = state["messages"][-1]
        assert isinstance(final, AIMessage)
        return AgentRun(answer=final.text, tool_results=state["tool_results"], iterations=state["iterations"])


def build_agent_service(settings: Settings) -> AgentService:
    return AgentService(
        llm=build_chat_model(settings),
        # Side-effecting tools (e.g. Telegram) need user approval, which only workflows provide.
        registry=build_default_registry(timeout_seconds=settings.tool_timeout_seconds).filtered(
            lambda tool: not tool.side_effects
        ),
        max_iterations=settings.agent_max_iterations,
        model_name=f"{settings.llm_provider}:{settings.llm_model}",
    )
