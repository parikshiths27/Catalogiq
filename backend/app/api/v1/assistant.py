"""
CatalogIQ Assistant API Router.
Provides POST /api/v1/assistant/chat endpoint for in-product Help Center queries.
"""
import logging
from fastapi import APIRouter, HTTPException, status

from app.services.assistant import (
    AssistantChatRequest,
    AssistantChatResponse,
    AssistantService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant")


@router.post(
    "/chat",
    response_model=AssistantChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit question to CatalogIQ Assistant",
)
def assistant_chat(payload: AssistantChatRequest) -> AssistantChatResponse:
    """
    Handles user help center and CatalogIQ operational questions.
    Returns grounded markdown explanation and contextual suggested follow-ups.
    """
    if not payload.message or not payload.message.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Message cannot be empty.",
        )

    try:
        service = AssistantService()
        history_list = None
        if payload.history:
            history_list = [{"role": turn.role, "content": turn.content} for turn in payload.history]

        return service.answer_question(
            message=payload.message,
            history=history_list,
            context=payload.context,
        )
    except Exception as e:
        logger.error(f"Error in assistant chat endpoint: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request.",
        )
