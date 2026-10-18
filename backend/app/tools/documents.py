"""MOCKED document search (stand-in for RAG). Returns a fixed passage; no index is queried."""

from typing import Literal

from pydantic import BaseModel, Field

from app.tools.base import Tool, ToolInput


class DocumentInput(ToolInput):
    query: str = Field(min_length=1, max_length=300)


class Passage(BaseModel):
    document: str
    excerpt: str


class DocumentOutput(BaseModel):
    query: str
    passages: list[Passage]
    mocked: Literal[True] = True


async def _search(args: DocumentInput) -> DocumentOutput:
    return DocumentOutput(
        query=args.query,
        passages=[Passage(document="Notes/Q4 goals.md", excerpt="Ship the assistant MVP before December.")],
    )


document_tool = Tool(
    name="document_search",
    description="Search the user's documents.",
    input_model=DocumentInput,
    output_model=DocumentOutput,
    handler=_search,
    mocked=True,
)
