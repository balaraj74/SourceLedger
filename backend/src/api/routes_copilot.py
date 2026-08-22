"""API Endpoints for Catalog Copilot & Multi-Agent Data Chat (SourceLedger)."""

from typing import Any, Dict, Optional
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from ..services.copilot_service import copilot_engine
from ..utils.logging import get_logger

logger = get_logger("routes_copilot")

router = APIRouter(prefix="/api/copilot", tags=["Catalog Copilot"])


class CopilotChatRequest(BaseModel):
    prompt: str = Field(..., description="User natural language chat query")


@router.post("/chat")
async def copilot_chat(
    req: CopilotChatRequest,
    x_user_id: Optional[str] = Header(None, alias="x-user-id"),
) -> Dict[str, Any]:
    """Execute Copilot natural language data query with multi-agent tool execution."""
    try:
        if not req.prompt or not req.prompt.strip():
            raise HTTPException(status_code=400, detail="User prompt cannot be empty.")
        
        logger.info("Received Copilot query (user=%s): %s", x_user_id, req.prompt)
        res = await copilot_engine.chat(req.prompt, user_id=x_user_id)
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in Copilot chat endpoint: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Copilot query failed: {str(e)}")


@router.get("/suggestions")
async def copilot_suggestions() -> Dict[str, Any]:
    """Return quick-start query suggestions for Copilot interface."""
    try:
        suggestions = await copilot_engine.get_suggestions()
        return {"suggestions": suggestions}
    except Exception as e:
        logger.error("Error in Copilot suggestions endpoint: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch suggestions: {str(e)}")
