from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.agent.service import AgentService, IterationLimitError, LLMUpstreamError
from app.api.dependencies import get_agent
from app.api.schemas import ChatRequest, ChatResponse

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, agent: Annotated[AgentService, Depends(get_agent)]) -> ChatResponse:
    try:
        run = await agent.run(body.message)
    except LLMUpstreamError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except IterationLimitError as exc:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return ChatResponse(answer=run.answer, tool_calls=run.tool_results, iterations=run.iterations, model=agent.model_name)
