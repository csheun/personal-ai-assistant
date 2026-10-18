from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe. Deliberately does not call the LLM (that would cost money and add latency)."""
    return {"status": "ok"}
