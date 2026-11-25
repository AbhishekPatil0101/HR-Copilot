"""
routers/chat.py
---------------
AI Assistant Chat Endpoint:
- POST /chat
Takes the user's message, optional conversation history or confirmation action,
and authenticates via the logged-in user's JWT token.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Employee
from app.security import get_current_user
from app.services.ai_service import run_chat


router = APIRouter(tags=["AI Assistant"])


class ChatTurn(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    message: str = Field("", description="User's chat message")
    history: Optional[List[ChatTurn]] = Field(None, description="Optional prior conversation turns")
    confirm_action: Optional[Dict[str, Any]] = Field(
        None,
        description="Pending action payload confirmed by the user (e.g., apply_leave confirmation button)",
    )


class ChatResponse(BaseModel):
    reply: str
    tools_called: List[str] = []
    citations: List[str] = []
    requires_confirmation: bool = False
    pending_action: Optional[Dict[str, Any]] = None
    injection_detected: bool = False


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Chat with HR Copilot AI",
    description="Sends a message to the Gemini-powered HR Assistant with tool calling and RAG.",
)
def chat_with_assistant(
    payload: ChatRequest,
    current_user: Employee = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.message.strip() and not payload.confirm_action:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either 'message' or 'confirm_action' must be provided.",
        )

    history_dicts = (
        [{"role": t.role, "content": t.content} for t in payload.history]
        if payload.history
        else None
    )

    try:
        return run_chat(
            message=payload.message,
            db=db,
            current_user=current_user,
            history=history_dicts,
            confirm_action=payload.confirm_action,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI service error: {exc}",
        )
