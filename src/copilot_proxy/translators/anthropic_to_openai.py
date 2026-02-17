"""Anthropic to OpenAI format translation."""

from typing import Optional

from ..schemas.anthropic import AnthropicMessage, AnthropicMessagesRequest
from ..schemas.openai import ChatCompletionMessage, ChatCompletionRequest
from ..utils.logger import get_logger

logger = get_logger(__name__)


def translate_anthropic_to_openai(
    request: AnthropicMessagesRequest,
) -> ChatCompletionRequest:
    """Translate Anthropic messages request to OpenAI format.

    Args:
        request: Anthropic messages request

    Returns:
        OpenAI-compatible chat completion request
    """
    messages = []

    # Add system message if present
    if request.system:
        if isinstance(request.system, str):
            system_content = request.system
        else:
            # Handle list of system parts
            system_content = " ".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in request.system
            )

        messages.append(
            ChatCompletionMessage(
                role="system",
                content=system_content,
            )
        )

    # Convert messages
    for msg in request.messages:
        content = msg.content

        # Handle content blocks
        if isinstance(content, list):
            converted_content = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        converted_content.append(
                            {
                                "type": "text",
                                "text": block.get("text", ""),
                            }
                        )
                    elif block.get("type") == "image":
                        # Handle image blocks
                        converted_content.append(block)
                    elif block.get("type") == "tool_use":
                        # Handle tool use blocks
                        converted_content.append(block)

            messages.append(
                ChatCompletionMessage(
                    role=msg.role,
                    content=converted_content if converted_content else "",
                )
            )
        else:
            messages.append(
                ChatCompletionMessage(
                    role=msg.role,
                    content=content,
                )
            )

    return ChatCompletionRequest(
        model=request.model,
        messages=messages,
        temperature=request.temperature,
        top_p=request.top_p,
        max_tokens=request.max_tokens,
        stream=request.stream,
    )
