"""Embeddings endpoint."""

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_copilot_client
from ...core.rate_limiter import get_rate_limiter
from ...core.state import get_state
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
        # Check rate limit
        state = get_state()
        rate_limiter = get_rate_limiter()

        if state.rate_limit_seconds:
            await rate_limiter.check_rate_limit(
                rate_limit_seconds=state.rate_limit_seconds,
                wait_mode=state.rate_limit_wait,
            )

        # Log request
        logger.info(f"Embeddings request - model: {request.model}")
        logger.debug(f"Request payload (last 400 chars): {str(request.model_dump())[-400:]}")

        response = await client.create_embeddings(
            input_text=request.input,
            model=request.model,
        )

        # Transform to OpenAI format with safe dict access
        embeddings_data = []
        data_list = response.get("data") if isinstance(response, dict) else None

        if isinstance(data_list, list):
            for i, embedding in enumerate(data_list):
                if not isinstance(embedding, dict):
                    continue

                embedding_vector = embedding.get("embedding")
                if not isinstance(embedding_vector, list):
                    continue

                embeddings_data.append(
                    EmbeddingData(
                        index=i,
                        embedding=embedding_vector,
                    )
                )

        usage_data = response.get("usage") if isinstance(response, dict) else None
        if not isinstance(usage_data, dict):
            usage_data = {}

        usage = ChatCompletionUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0) if isinstance(usage_data.get("prompt_tokens"), int) else 0,
            completion_tokens=0,
            total_tokens=usage_data.get("prompt_tokens", 0) if isinstance(usage_data.get("prompt_tokens"), int) else 0,
        )

        result = EmbeddingResponse(
            data=embeddings_data,
            model=request.model,
            usage=usage,
        )

        logger.debug(f"Response (last 400 chars): {str(result.model_dump())[-400:]}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Embeddings error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Embeddings failed: {str(e)}")
