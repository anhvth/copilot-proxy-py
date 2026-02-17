"""Copilot API schemas."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class ContentBlockDeltaEvent(BaseModel):
    """Delta event for streaming content."""

    type: str = "content_block_delta"
    index: int
    delta: dict


class MessageDeltaEvent(BaseModel):
    """Message delta event for streaming."""

    type: str = "message_delta"
    delta: dict


class CopilotChatMessage(BaseModel):
    """Copilot chat message."""

    role: str
    content: str | list[dict]


class CopilotChatCompletionRequest(BaseModel):
    """Copilot chat completion request."""

    model: str
    messages: list[CopilotChatMessage]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    stream: bool = False
    top_p: Optional[float] = None


class CopilotChatCompletionChoice(BaseModel):
    """Chat completion choice."""

    index: int
    message: CopilotChatMessage
    finish_reason: Optional[str] = None


class CopilotChatCompletionResponse(BaseModel):
    """Copilot chat completion response."""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[CopilotChatCompletionChoice]
    usage: Optional[dict] = None


class CopilotModel(BaseModel):
    """Copilot model information."""

    id: str
    name: str
    version: Optional[str] = None
    capabilities: Optional[dict] = None


class CopilotModelsResponse(BaseModel):
    """Response from /models endpoint."""

    data: list[CopilotModel]


class CopilotEmbeddingRequest(BaseModel):
    """Embedding request."""

    input: str | list[str]
    model: str = "text-embedding-ada-002"


class CopilotEmbedding(BaseModel):
    """Embedding vector."""

    object: str = "embedding"
    index: int
    embedding: list[float]


class CopilotEmbeddingResponse(BaseModel):
    """Embedding response."""

    object: str = "list"
    data: list[CopilotEmbedding]
    model: str
    usage: dict
