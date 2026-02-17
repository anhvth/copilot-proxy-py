"""Token debug endpoint."""

from fastapi import APIRouter, HTTPException

from ...core.rate_limiter import get_rate_limiter
from ...core.state import get_state
from ...utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/debug/token")
async def debug_token():
    """Debug endpoint to show token info."""
    try:
        # Check rate limit
        state = get_state()
        rate_limiter = get_rate_limiter()

        if state.rate_limit_seconds:
            await rate_limiter.check_rate_limit(
                rate_limit_seconds=state.rate_limit_seconds,
                wait_mode=state.rate_limit_wait,
            )

        # Safe access to state properties
        github_token = state.github_token if hasattr(state, 'github_token') else None
        copilot_token = state.copilot_token if hasattr(state, 'copilot_token') else None
        copilot_token_expires_at = state.copilot_token_expires_at if hasattr(state, 'copilot_token_expires_at') else None
        account_type = state.account_type if hasattr(state, 'account_type') else None

        result = {
            "has_github_token": github_token is not None,
            "github_token_len": len(github_token) if github_token else 0,
            "has_copilot_token": copilot_token is not None,
            "copilot_token_len": len(copilot_token) if copilot_token else 0,
            "copilot_token_expires_at": copilot_token_expires_at.isoformat()
            if copilot_token_expires_at
            else None,
            "account_type": account_type,
        }

        logger.debug(f"Debug token info retrieved")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Debug token error: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get debug token info: {str(e)}")
