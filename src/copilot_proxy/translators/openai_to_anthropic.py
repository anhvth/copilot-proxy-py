"""OpenAI to Anthropic format translation."""

import time
from typing import Optional

from ..schemas.openai import ChatCompletionResponse, ChatCompletionUsage
from ..schemas.anthropic import (
    AnthropicMessageResponse,
    AnthropicUsage,
    AnthropicContentBlockDeltaEvent,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


def translate_openai_to_anthropic(
    response: ChatCompletionResponse,
) -> AnthropicMessageResponse:
    """Translate OpenAI chat completion response to Anthropic format.

    Args:
        response: OpenAI chat completion response

    Returns:
        Anthropic-compatible message response
    """
    # Extract content from choices
    content = []

    for choice in response.choices:
        msg_content = choice.message.content

        if isinstance(msg_content, str):
            if msg_content:
                content.append(
                    {
                        "type": "text",
                        "text": msg_content,
                    }
                )
        elif isinstance(msg_content, list):
            content.extend(msg_content)

    # Convert usage
    usage = AnthropicUsage(
        input_tokens=response.usage.prompt_tokens if response.usage else 0,
        output_tokens=response.usage.completion_tokens if response.usage else 0,
    )

    # Map stop reason
    stop_reason = "end_turn"
    if response.choices and response.choices[0].finish_reason:
        finish_reason = response.choices[0].finish_reason.lower()
        if finish_reason == "length":
            stop_reason = "max_tokens"
        elif finish_reason == "tool_calls":
            stop_reason = "tool_use"
        elif finish_reason == "stop":
            stop_reason = "end_turn"
        else:
            stop_reason = finish_reason

    return AnthropicMessageResponse(
        id=response.id,
        type="message",
        role="assistant",
        content=content or [{"type": "text", "text": ""}],
        model=response.model,
        stop_reason=stop_reason,
        usage=usage,
    )


async def stream_openai_to_anthropic(openai_stream):
    """Stream OpenAI chat completion in Anthropic event format.

    Args:
        openai_stream: OpenAI SSE stream

    Yields:
        Anthropic-formatted streaming events as JSON strings
    """
    import json

    content_block_index = 0
    current_text = ""

    # Send message_start event
    message_start = {
        "type": "message_start",
        "message": {
            "id": f"msg_{int(time.time())}",
            "type": "message",
            "role": "assistant",
            "content": [],
            "model": "claude-3-5-sonnet",
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 0, "output_tokens": 0},
        },
    }
    yield f"data: {json.dumps(message_start)}\n\n"

    # Send content_block_start
    content_block_start = {
        "type": "content_block_start",
        "index": content_block_index,
        "content_block": {"type": "text"},
    }
    yield f"data: {json.dumps(content_block_start)}\n\n"

    # Process OpenAI stream
    async for line in openai_stream:
        try:
            if line.startswith("data:"):
                line = line[5:].strip()

            if not line or line == "[DONE]":
                continue

            data = json.loads(line)

            # Extract content from OpenAI format
            if "choices" in data and len(data["choices"]) > 0:
                choice = data["choices"][0]

                if "delta" in choice and "content" in choice["delta"]:
                    content = choice["delta"]["content"]

                    if content:
                        current_text += content

                        # Send content_block_delta
                        delta_event = AnthropicContentBlockDeltaEvent(
                            type="content_block_delta",
                            index=content_block_index,
                            delta={"type": "text_delta", "text": content},
                        )
                        yield f"data: {delta_event.model_dump_json()}\n\n"

        except json.JSONDecodeError:
            continue
        except Exception as e:
            logger.debug(f"Error processing stream chunk: {e}")
            continue

    # Send content_block_stop
    content_block_stop = {
        "type": "content_block_stop",
        "index": content_block_index,
    }
    yield f"data: {json.dumps(content_block_stop)}\n\n"

    # Send message_delta
    message_delta = {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
        "usage": {"output_tokens": len(current_text.split())},
    }
    yield f"data: {json.dumps(message_delta)}\n\n"

    # Send message_stop
    message_stop = {"type": "message_stop"}
    yield f"data: {json.dumps(message_stop)}\n\n"
