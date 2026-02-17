"""Health check endpoints."""

from fastapi import APIRouter

from ...core.state import get_state
from ...utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/")
@router.get("/health")
async def health_check():
    """Health check endpoint."""
    state = get_state()
    return {
        "status": "healthy",
        "version": "0.1.0",
        "has_token": state.copilot_token is not None,
        "token_expires_at": state.copilot_token_expires_at.isoformat()
        if state.copilot_token_expires_at
        else None,
    }
