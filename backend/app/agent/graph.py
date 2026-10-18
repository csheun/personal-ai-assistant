"""LangGraph agent: the LLM decides which tools to call; Python executes them.

    START -> llm --(tool calls?)--> tools --(budget left?)--> llm --> ... --> END

`llm` node:   calls the model with the tool schemas bound. The model replies with
              either a final answer or a list of tool calls (name + JSON args).
`tools` node: executes every requested call through the ToolRegistry (allow-list
              + validation), concurrently, and appends one ToolMessage per call
              so the model sees the results on its next turn.
"""

import asyncio
import json
import operator
from typing import Annotated, Literal, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph

from app.tools import ToolError, ToolRegistry, ToolResult


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    # Structured record of every tool execution, returned to the API caller.
    tool_results: Annotated[list[ToolResult], operator.add]
    # Number of LLM calls made so far.
    iterations: int
    # Set when the model still wanted tools after the iteration budget was spent.
    hit_iteration_limit: bool


def _tool_message(call_id: str, result: ToolResult) -> ToolMessage:
    payload = result.model_dump(mode="json", include={"ok", "output", "error", "mocked"}, exclude_none=True)
    return ToolMessage(
        content=json.dumps(payload),
        tool_call_id=call_id,
        name=result.tool_name,
        status="success" if result.ok else "error",
    )


def build_agent_graph(llm: BaseChatModel, registry: ToolRegistry, max_iterations: int) -> CompiledStateGraph:
    llm_with_tools = llm.bind_tools(registry.llm_schemas())

    async def call_llm(state: AgentState) -> dict:
        response = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response], "iterations": state["iterations"] + 1}

    async def run_tools(state: AgentState) -> dict:
        last = state["messages"][-1]
        assert isinstance(last, AIMessage)

        calls = last.tool_calls
        results: list[ToolResult] = list(
            await asyncio.gather(*(registry.execute(call["name"], call["args"]) for call in calls))
        )
        messages = [_tool_message(call["id"], result) for call, result in zip(calls, results, strict=True)]

        # Tool calls whose arguments weren't even valid JSON. Every call id needs a reply,
        # otherwise providers reject the next request; replying with an error lets the model retry.
        for bad in last.invalid_tool_calls:
            result = ToolResult(
                tool_name=bad.get("name") or "unknown",
                arguments={},
                ok=False,
                error=ToolError(code="invalid_arguments", message="Tool arguments were not valid JSON."),
            )
            results.append(result)
            messages.append(_tool_message(bad["id"], result))

        return {"messages": messages, "tool_results": results}

    def route_after_llm(state: AgentState) -> Literal["tools", "__end__"]:
        last = state["messages"][-1]
        wants_tools = isinstance(last, AIMessage) and (last.tool_calls or last.invalid_tool_calls)
        return "tools" if wants_tools else END

    def route_after_tools(state: AgentState) -> Literal["llm", "limit"]:
        return "llm" if state["iterations"] < max_iterations else "limit"

    def mark_limit(_: AgentState) -> dict:
        return {"hit_iteration_limit": True}

    graph = StateGraph(AgentState)
    graph.add_node("llm", call_llm)
    graph.add_node("tools", run_tools)
    graph.add_node("limit", mark_limit)
    graph.add_edge(START, "llm")
    graph.add_conditional_edges("llm", route_after_llm)
    graph.add_conditional_edges("tools", route_after_tools)
    graph.add_edge("limit", END)
    return graph.compile()
