"""Models endpoint."""

from fastapi import APIRouter, HTTPException

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

        # Transform to OpenAI format with safe dict access
        model_data = []
        if isinstance(models, list):
            for m in models:
                if not isinstance(m, dict):
                    continue

                model_id = m.get("id")
                if not isinstance(model_id, str) or not model_id:
                    model_id = m.get("name", "unknown")

                if not isinstance(model_id, str):
                    model_id = "unknown"

                model_data.append(
                    ModelData(
                        id=model_id,
                        created=0,
                    )
                )

        logger.debug(f"Returning {len(model_data)} models")
        return ModelsResponse(data=model_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Models endpoint error: {type(e).__name__}: {e}")
        # Return default models on error
        return ModelsResponse(
            data=[
                ModelData(id="gpt-4", created=0),
                ModelData(id="gpt-4o", created=0),
                ModelData(id="claude-3-5-sonnet-20241022", created=0),
            ]
        )
