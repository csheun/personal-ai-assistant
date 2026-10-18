from typing import Annotated

from fastapi import Depends, Request

from app.workflows.service import WorkflowService


def get_workflows(request: Request) -> WorkflowService:
    """Built once at startup (see app.main) and shared by every request."""
    return request.app.state.workflows


Workflows = Annotated[WorkflowService, Depends(get_workflows)]
