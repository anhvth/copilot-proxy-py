"""Token and usage endpoints."""

from fastapi import APIRouter, HTTPException

from ...core.state import get_state
from ...core.token_manager import get_token_manager
from ...services.github.client import GitHubClient
from ...utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/token")
async def get_token_info():
    """Get current token information (debug endpoint).

    Requires --show-token flag to be set.
    """
    state = get_state()

    if not state.copilot_token:
        raise HTTPException(status_code=400, detail="No token available")

    # Only show token if explicitly enabled
    from ...config.settings import settings

    token_preview = "***" if not settings.show_token else state.copilot_token[:20] + "***"

    return {
        "has_token": True,
        "token_preview": token_preview,
        "expires_at": state.copilot_token_expires_at.isoformat()
        if state.copilot_token_expires_at
        else None,
        "account_type": state.account_type,
    }


@router.get("/usage")
async def get_usage():
    """Get Copilot usage information."""
    try:
        state = get_state()

        if not state.github_token:
            raise HTTPException(status_code=400, detail="GitHub token not available")

        github_client = GitHubClient()
        usage = await github_client.get_copilot_usage(state.github_token)

        return usage

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get usage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/v1/models/count_tokens", include_in_schema=False)
async def count_tokens():
    """Count tokens endpoint (not yet implemented)."""
    raise HTTPException(status_code=501, detail="Not implemented")
