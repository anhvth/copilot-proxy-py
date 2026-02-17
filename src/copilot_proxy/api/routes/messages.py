"""Anthropic messages endpoint."""

import json
import time
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from ..dependencies import get_copilot_client
from ...core.rate_limiter import get_rate_limiter
from ...core.state import get_state
from ...schemas.anthropic import (
    AnthropicMessagesRequest,
    AnthropicCountTokensRequest,
    AnthropicCountTokensResponse,
)
from ...schemas.openai import ChatCompletionRequest
from ...services.copilot.client import CopilotClient
from ...translators.anthropic_to_openai import translate_anthropic_to_openai
from ...translators.openai_to_anthropic import (
    translate_openai_to_anthropic,
    stream_openai_to_anthropic,
)
from ...utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


async def stream_anthropic_messages(
    request: AnthropicMessagesRequest,
    client: CopilotClient,
) -> AsyncGenerator[str, None]:
    """Stream Anthropic-format messages using OpenAI backend.

    Args:
        request: Anthropic messages request
        client: Copilot API client

    Yields:
        Anthropic-format SSE events
    """
    try:
        # Translate to OpenAI format
        openai_request = translate_anthropic_to_openai(request)

        # Convert messages
        messages = [
            m.model_dump() if hasattr(m, "model_dump") else m for m in openai_request.messages
        ]

        # Stream from OpenAI backend
        async for line in stream_openai_to_anthropic(
            client.stream_chat_completion(
                messages=messages,
                model=request.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )
        ):
            yield line

    except Exception as e:
        logger.error(f"Error in stream_anthropic_messages: {e}")
        raise


@router.post("/v1/messages")
@router.post("/messages")
async def create_messages(
    request: AnthropicMessagesRequest,
    client: CopilotClient = Depends(get_copilot_client),
):
    """Anthropic messages endpoint.

    Args:
        request: Anthropic messages request
        client: Copilot API client

    Returns:
        Anthropic message response (streaming or non-streaming)
    """
    try:
        # Log request payload
        payload_dict = request.model_dump()
        logger.info(f"Anthropic messages request - model: {request.model}, stream: {request.stream}")
        logger.debug(f"Request payload (last 400 chars): {str(payload_dict)[-400:]}")

        # Check rate limit
        state = get_state()
        rate_limiter = get_rate_limiter()

        if state.rate_limit_seconds:
            await rate_limiter.check_rate_limit(
                rate_limit_seconds=state.rate_limit_seconds,
                wait_mode=state.rate_limit_wait,
            )

        # Handle streaming
        if request.stream:
            logger.debug("Starting Anthropic streaming response")
            return EventSourceResponse(stream_anthropic_messages(request, client))

        # Translate to OpenAI format
        openai_request = translate_anthropic_to_openai(request)

        # Convert messages
        messages = [
            m.model_dump() if hasattr(m, "model_dump") else m for m in openai_request.messages
        ]

        # Get response from OpenAI backend
        response = await client.create_chat_completion(
            messages=messages,
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stream=False,
        )

        # Transform to Anthropic format
        openai_response_obj = _dict_to_response(response, request.model)
        anthropic_response = translate_openai_to_anthropic(openai_response_obj)

        logger.debug(f"Anthropic response (last 400 chars): {str(anthropic_response.model_dump())[-400:]}")
        return anthropic_response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Messages error: {type(e).__name__}: {e}")
        logger.debug(f"Request details: model={request.model}, stream={request.stream}")
        raise HTTPException(status_code=500, detail=f"Message creation failed: {str(e)}")


@router.post("/v1/messages/count_tokens")
@router.post("/messages/count_tokens")
async def count_tokens(request: AnthropicCountTokensRequest):
    """Count tokens endpoint (Anthropic format).

    Args:
        request: Count tokens request

    Returns:
        Token count response
    """
    # Simple token counting (rough estimate)
    total_tokens = 0

    if request.system:
        system_text = (
            request.system if isinstance(request.system, str) else json.dumps(request.system)
        )
        total_tokens += len(system_text.split())

    for msg in request.messages:
        if isinstance(msg.content, str):
            total_tokens += len(msg.content.split())
        elif isinstance(msg.content, list):
            total_tokens += sum(
                len(block.get("text", "").split())
                if isinstance(block, dict)
                else len(str(block).split())
                for block in msg.content
            )

    return AnthropicCountTokensResponse(input_tokens=total_tokens)


def _dict_to_response(data: dict, model: str):
    """Convert dict response to OpenAI response object.

    Args:
        data: Response dictionary
        model: Model name

    Returns:
        ChatCompletionResponse
    """
    from ...schemas.openai import (
        ChatCompletionResponse,
        ChatCompletionChoice,
        ChatCompletionMessage,
        ChatCompletionUsage,
    )

    choices = []
    if "choices" in data:
        for i, choice in enumerate(data["choices"]):
            msg_content = choice.get("message", {}).get("content", "")

            if isinstance(msg_content, list):
                msg_content = "".join(
                    item.get("text", "") for item in msg_content if isinstance(item, dict)
                )

            choices.append(
                ChatCompletionChoice(
                    index=i,
                    message=ChatCompletionMessage(role="assistant", content=msg_content),
                    finish_reason=choice.get("finish_reason", "stop"),
                )
            )

    usage = None
    if "usage" in data:
        usage = ChatCompletionUsage(**data["usage"])

    return ChatCompletionResponse(
        id=data.get("id", f"msg_{int(time.time())}"),
        created=data.get("created", int(time.time())),
        model=model,
        choices=choices,
        usage=usage,
    )
