"""What the LLM planner must return. Validated by Pydantic first, then by `validation.py`.

Kept flat (a `mode` field plus optional fields) rather than a union of types: providers'
structured-output modes handle flat objects far more reliably than discriminated unions.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class DraftTask(BaseModel):
    id: str = Field(description='Short unique id, e.g. "t1".')
    title: str = Field(description='What this step does, written for the user, e.g. "Check Singapore weather".')
    tool: str = Field(description="Exactly one of the available tool names.")
    arguments: dict[str, Any] = Field(
        default_factory=dict, description="Arguments for the tool. Never include fields marked as filled automatically."
    )
    depends_on: list[str] = Field(
        default_factory=list, description="Ids of tasks whose results this task needs. Empty if it needs none."
    )


class PlannerOutput(BaseModel):
    """Either answer directly (no tools needed) or propose a workflow of tool calls."""

    mode: Literal["answer", "workflow"] = Field(
        description='"answer" if you can fully answer from general knowledge; "workflow" if live data or actions are needed.'
    )
    answer: str | None = Field(default=None, description='mode="answer" only: the complete reply to the user.')
    reply: str | None = Field(
        default=None, description='mode="workflow" only: one or two sentences telling the user what you will do.'
    )
    goal: str | None = Field(default=None, description='mode="workflow" only: a short summary of the plan.')
    tasks: list[DraftTask] = Field(default_factory=list, description='mode="workflow" only: the steps.')
