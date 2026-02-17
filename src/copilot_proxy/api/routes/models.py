"""Models endpoint."""

from fastapi import APIRouter

from ..dependencies import get_copilot_client
from ...schemas.openai import ModelData, ModelsResponse
from ...utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/v1/models")
@router.get("/models")
async def list_models():
    """List available models."""
    try:
        client = get_copilot_client()
        models = await client.get_models()

        # Transform to OpenAI format
        model_data = [
            ModelData(
                id=m.get("id", m.get("name", "unknown")),
                created=0,
            )
            for m in models
        ]

        return ModelsResponse(data=model_data)

    except Exception as e:
        logger.error(f"Error listing models: {e}")
        # Return default models
        return ModelsResponse(
            data=[
                ModelData(id="gpt-4", created=0),
                ModelData(id="gpt-4o", created=0),
                ModelData(id="claude-3-5-sonnet-20241022", created=0),
            ]
        )
