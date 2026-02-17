"""Embeddings endpoint."""

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_copilot_client
from ...schemas.openai import EmbeddingInput, EmbeddingResponse, EmbeddingData, ChatCompletionUsage
from ...services.copilot.client import CopilotClient
from ...utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.post("/v1/embeddings")
@router.post("/embeddings")
async def create_embeddings(
    request: EmbeddingInput,
    client: CopilotClient = Depends(get_copilot_client),
):
    """Create embeddings endpoint.

    Args:
        request: Embedding request
        client: Copilot API client

    Returns:
        Embedding response
    """
    try:
        response = await client.create_embeddings(
            input_text=request.input,
            model=request.model,
        )

        # Transform to OpenAI format
        embeddings_data = []
        for i, embedding in enumerate(response.get("data", [])):
            embeddings_data.append(
                EmbeddingData(
                    index=i,
                    embedding=embedding.get("embedding", []),
                )
            )

        usage_data = response.get("usage", {})
        usage = ChatCompletionUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=0,
            total_tokens=usage_data.get("prompt_tokens", 0),
        )

        return EmbeddingResponse(
            data=embeddings_data,
            model=request.model,
            usage=usage,
        )

    except Exception as e:
        logger.error(f"Embeddings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
