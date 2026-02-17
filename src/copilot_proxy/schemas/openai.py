"""OpenAI-compatible request/response schemas."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatCompletionMessage(BaseModel):
    """Chat completion message."""

    role: str
    content: str | list[dict] | None = None
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""

    model: str
    messages: list[ChatCompletionMessage]
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: bool = False
    stop: Optional[str | list[str]] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    user: Optional[str] = None


class ChatCompletionChoiceDelta(BaseModel):
    """Delta for streaming choice."""

    role: Optional[str] = None
    content: Optional[str] = None


class ChatCompletionStreamChoice(BaseModel):
    """Streaming choice."""

    index: int
    delta: ChatCompletionChoiceDelta
    finish_reason: Optional[str] = None


class ChatCompletionStreamResponse(BaseModel):
    """Streaming chat completion response."""

    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[ChatCompletionStreamChoice]


class ChatCompletionChoice(BaseModel):
    """Non-streaming choice."""

    index: int
    message: ChatCompletionMessage
    finish_reason: Optional[str] = None


class ChatCompletionUsage(BaseModel):
    """Token usage information."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""

    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: Optional[ChatCompletionUsage] = None


class EmbeddingInput(BaseModel):
    """Embedding input."""

    input: str | list[str]
    model: str = "text-embedding-ada-002"


class EmbeddingData(BaseModel):
    """Embedding data."""

    object: str = "embedding"
    index: int
    embedding: list[float]


class EmbeddingResponse(BaseModel):
    """Embedding response."""

    object: str = "list"
    data: list[EmbeddingData]
    model: str
    usage: ChatCompletionUsage


class ModelData(BaseModel):
    """Model data in models list."""

    id: str
    object: str = "model"
    created: int
    owned_by: str = "copilot"


class ModelsResponse(BaseModel):
    """Response from /models endpoint."""

    object: str = "list"
    data: list[ModelData]


class CompletionRequest(BaseModel):
    """Legacy completion request."""

    model: str
    prompt: str | list[str]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    top_p: Optional[float] = None
    stream: bool = False
