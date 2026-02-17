"""Completions endpoint (legacy)."""

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_copilot_client
from ...schemas.openai import CompletionRequest, ChatCompletionMessage
from ...services.copilot.client import CopilotClient
from ...utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("/v1/completions")
@router.post("/completions")
async def completions(
    request: CompletionRequest,
    client: CopilotClient = Depends(get_copilot_client),
):
    """Legacy completions endpoint (converts to chat).

    Args:
        request: Completion request
        client: Copilot API client

    Returns:
        Completion response
    """
    try:
        # Convert to chat format
        if isinstance(request.prompt, str):
            prompt = request.prompt
        else:
            prompt = "\n".join(request.prompt)

        messages = [ChatCompletionMessage(role="user", content=prompt).model_dump()]

        response = await client.create_chat_completion(
            messages=messages,
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stream=request.stream,
        )

        return response

    except Exception as e:
        logger.error(f"Completions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
