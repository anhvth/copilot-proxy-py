"""Chat completions endpoint."""

import json
import time
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from sse_starlette.sse import EventSourceResponse

from ..dependencies import get_copilot_client
from ...core.rate_limiter import get_rate_limiter
from ...core.state import get_state
from ...schemas.openai import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionStreamChoice,
    ChatCompletionStreamResponse,
    ChatCompletionUsage,
    ChatCompletionChoiceDelta,
)
from ...services.copilot.client import CopilotClient
from ...utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


async def stream_chat_chunks(
    request: ChatCompletionRequest,
    client: CopilotClient,
) -> AsyncGenerator[str, None]:
    """Stream chat completion chunks in OpenAI format.

    Args:
        request: Chat completion request
        client: Copilot API client

    Yields:
        OpenAI-format SSE messages
    """
    try:
        # Convert messages to dicts if needed
        messages = [
            m.model_dump() if hasattr(m, "model_dump") else m for m in request.messages
        ]

        chunk_id = f"chatcmpl-{int(time.time())}"
        accumulated_content = ""
        finish_reason = None

        async for line in client.stream_chat_completion(
            messages=messages,
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        ):
            try:
                if line.startswith("data:"):
                    line = line[5:].strip()

                if not line or line == "[DONE]":
                    # Send final chunk with finish_reason
                    if finish_reason:
                        final_chunk = ChatCompletionStreamResponse(
                            id=chunk_id,
                            created=int(time.time()),
                            model=request.model,
                            choices=[
                                ChatCompletionStreamChoice(
                                    index=0,
                                    delta=ChatCompletionChoiceDelta(content=None),
                                    finish_reason=finish_reason,
                                )
                            ],
                        )
                        yield f"data: {final_chunk.model_dump_json()}\n\n"
                    yield "data: [DONE]\n\n"
                    break

                # Parse SSE line
                data = json.loads(line)

                # Extract content from Copilot response
                if "choices" in data and len(data["choices"]) > 0:
                    choice = data["choices"][0]

                    if "delta" in choice and "content" in choice["delta"]:
                        content = choice["delta"]["content"]
                        if content:
                            accumulated_content += content

                            # Create streaming response
                            chunk = ChatCompletionStreamResponse(
                                id=chunk_id,
                                created=int(time.time()),
                                model=request.model,
                                choices=[
                                    ChatCompletionStreamChoice(
                                        index=0,
                                        delta=ChatCompletionChoiceDelta(content=content),
                                        finish_reason=None,
                                    )
                                ],
                            )
                            yield f"data: {chunk.model_dump_json()}\n\n"

                    if "finish_reason" in choice and choice["finish_reason"]:
                        finish_reason = choice["finish_reason"]

            except json.JSONDecodeError:
                logger.debug(f"Failed to parse SSE line: {line}")
                continue
            except Exception as e:
                logger.error(f"Error processing streaming chunk: {e}")
                continue

    except Exception as e:
        logger.error(f"Error in stream_chat_chunks: {e}")
        raise


@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    client: CopilotClient = Depends(get_copilot_client),
):
    """Chat completions endpoint (OpenAI compatible).

    Args:
        request: Chat completion request
        client: Copilot API client

    Returns:
        Chat completion response (streaming or non-streaming)
    """
    try:
        # Log request payload
        payload_dict = request.model_dump()
        logger.info(f"Chat completion request - model: {request.model}, stream: {request.stream}")
        logger.debug(f"Request payload (last 400 chars): {str(payload_dict)[-400:]}")

        # Check rate limit
        state = get_state()
        rate_limiter = get_rate_limiter()

        if state.rate_limit_seconds:
            await rate_limiter.check_rate_limit(
                rate_limit_seconds=state.rate_limit_seconds,
                wait_mode=state.rate_limit_wait,
            )

        # Convert messages to dicts
        messages = [
            m.model_dump() if hasattr(m, "model_dump") else m for m in request.messages
        ]

        # Handle streaming
        if request.stream:
            logger.debug("Starting streaming response")
            return EventSourceResponse(stream_chat_chunks(request, client))

        # Non-streaming
        response = await client.create_chat_completion(
            messages=messages,
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stream=False,
        )

        # Transform to OpenAI format if needed
        if "choices" in response:
            choices = []
            for i, choice in enumerate(response["choices"]):
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

            # Get usage if available
            usage = None
            if "usage" in response:
                usage = ChatCompletionUsage(**response["usage"])

            result = ChatCompletionResponse(
                id=response.get("id", f"chatcmpl-{int(time.time())}"),
                created=response.get("created", int(time.time())),
                model=request.model,
                choices=choices,
                usage=usage,
            )

            logger.debug(f"Non-streaming response (last 400 chars): {str(result.model_dump())[-400:]}")
            return result

        raise HTTPException(status_code=500, detail="Invalid response format from Copilot API")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat completions error: {type(e).__name__}: {e}")
        logger.debug(f"Request details: model={request.model}, stream={request.stream}")
        raise HTTPException(status_code=500, detail=f"Chat completion failed: {str(e)}")
