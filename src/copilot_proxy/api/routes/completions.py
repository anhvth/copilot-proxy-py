"""Completions endpoint (legacy)."""

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_copilot_client
from ...core.rate_limiter import get_rate_limiter
from ...core.state import get_state
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
        # Check rate limit
        state = get_state()
        rate_limiter = get_rate_limiter()

        if state.rate_limit_seconds:
            await rate_limiter.check_rate_limit(
                rate_limit_seconds=state.rate_limit_seconds,
                wait_mode=state.rate_limit_wait,
            )

        # Log request
        logger.info(f"Completions request - model: {request.model}")
        logger.debug(f"Request payload (last 400 chars): {str(request.model_dump())[-400:]}")

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

        logger.debug(f"Response (last 400 chars): {str(response)[-400:]}")
        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Completions error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Completions failed: {str(e)}")
