"""Token debug endpoint."""

from fastapi import APIRouter

from ...core.state import get_state
from ...utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/debug/token")
async def debug_token():
    """Debug endpoint to show token info."""
    state = get_state()

    return {
        "has_github_token": state.github_token is not None,
        "github_token_len": len(state.github_token) if state.github_token else 0,
        "has_copilot_token": state.copilot_token is not None,
        "copilot_token_len": len(state.copilot_token) if state.copilot_token else 0,
        "copilot_token_expires_at": state.copilot_token_expires_at.isoformat()
        if state.copilot_token_expires_at
        else None,
        "account_type": state.account_type,
    }
