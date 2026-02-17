"""Health check endpoints."""

from fastapi import APIRouter, HTTPException

from ...core.state import get_state
from ...utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/")
@router.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        state = get_state()

        # Safe access to state properties
        copilot_token = state.copilot_token if hasattr(state, 'copilot_token') else None
        copilot_token_expires_at = state.copilot_token_expires_at if hasattr(state, 'copilot_token_expires_at') else None

        result = {
            "status": "healthy",
            "version": "0.1.0",
            "has_token": copilot_token is not None,
            "token_expires_at": copilot_token_expires_at.isoformat() if copilot_token_expires_at else None,
        }

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")
