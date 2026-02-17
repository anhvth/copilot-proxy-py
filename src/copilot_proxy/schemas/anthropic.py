"""Anthropic-compatible request/response schemas."""

from typing import Optional

from pydantic import BaseModel


class AnthropicMessage(BaseModel):
    """Anthropic API message."""

    role: str
    content: str | list[dict]


class AnthropicMessagesRequest(BaseModel):
    """Anthropic messages API request."""

    model: str
    max_tokens: int
    messages: list[AnthropicMessage]
    stream: bool = False
    temperature: Optional[float] = None
    system: Optional[str | list[dict]] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None


class AnthropicUsage(BaseModel):
    """Anthropic usage information."""

    input_tokens: int
    output_tokens: int


class AnthropicMessageResponse(BaseModel):
    """Anthropic message response."""

    id: str
    type: str
    role: str
    content: list[dict]
    model: str
    stop_reason: str
    stop_sequence: Optional[str] = None
    usage: AnthropicUsage


class AnthropicStreamEvent(BaseModel):
    """Base for Anthropic streaming events."""

    type: str


class AnthropicMessageStartEvent(BaseModel):
    """Message start event."""

    type: str = "message_start"
    message: AnthropicMessageResponse


class AnthropicContentBlockStartEvent(BaseModel):
    """Content block start event."""

    type: str = "content_block_start"
    index: int
    content_block: dict


class AnthropicContentBlockDeltaEvent(BaseModel):
    """Content block delta event."""

    type: str = "content_block_delta"
    index: int
    delta: dict


class AnthropicContentBlockStopEvent(BaseModel):
    """Content block stop event."""

    type: str = "content_block_stop"
    index: int


class AnthropicMessageDeltaEvent(BaseModel):
    """Message delta event."""

    type: str = "message_delta"
    delta: dict


class AnthropicMessageStopEvent(BaseModel):
    """Message stop event."""

    type: str = "message_stop"


class AnthropicCountTokensRequest(BaseModel):
    """Count tokens request."""

    model: str
    messages: list[AnthropicMessage]
    system: Optional[str] = None


class AnthropicCountTokensResponse(BaseModel):
    """Count tokens response."""

    input_tokens: int
