from fastapi import APIRouter

from app.api.dependencies import Workflows
from app.workflows.models import ChatMessage, Conversation, UsageStats

router = APIRouter(tags=["conversations"])


@router.get("/conversations", response_model=list[Conversation])
async def list_conversations(workflows: Workflows) -> list[Conversation]:
    return workflows.list_conversations()


@router.get("/conversations/{conversation_id}/messages", response_model=list[ChatMessage])
async def list_messages(conversation_id: str, workflows: Workflows) -> list[ChatMessage]:
    return workflows.list_messages(conversation_id)


@router.get("/stats", response_model=UsageStats)
async def stats(workflows: Workflows) -> UsageStats:
    return workflows.stats()
