from fastapi import APIRouter

from app.api.dependencies import Workflows
from app.workflows.models import SendMessageRequest, SendMessageResponse

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=SendMessageResponse)
async def send_message(body: SendMessageRequest, workflows: Workflows) -> SendMessageResponse:
    """Replies to a message. If the reply proposes a workflow, `run` is returned in status "planned"."""
    return await workflows.send_message(body)
